# Copyright (2025) Bytedance Ltd. and/or its affiliates.
"""
Filter high-quality data entries from ApeBench pipeline results.

This script processes result files from different pipelines (instruction, patch, judgement)
and applies pipeline-specific filtering criteria to identify high-quality data points.
"""

import argparse
import os
import json
import glob
import pandas as pd
from tqdm import tqdm
from datetime import datetime
from ...utils import load_results, save_jsonl
import numpy as np
from collections import Counter
import re

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Filter high-quality entries from ApeBench pipeline results")
    
    # General arguments
    parser.add_argument("--pipeline", type=str, required=True,
                        choices=["instruction", "patch", "judgement", "verification", "merge"],
                        help="Pipeline type to filter results from")
    parser.add_argument("--input_files", type=str, nargs="*",
                        help="File pattern containing result files")
    parser.add_argument("--output_dir", type=str, default="./outputs",
                        help="Directory to save filtered results")
    parser.add_argument("--output_file", type=str, default=None,
                        help="Output file name")
    parser.add_argument("--timestamp", type=str,
                        default=datetime.now().strftime('%Y%m%d_%H%M%S'),
                        help="Timestamp to use for output filenames")
    parser.add_argument("--reset_index_by_date", action="store_true",
                        help="Reset index of filtered data by date")
    
    # New arguments for merge pipeline
    parser.add_argument("--original_files", type=str, nargs="*",
                        help="Original generation files to merge (comma-separated)")
    parser.add_argument("--verification_file", type=str,
                        help="Verification result file")
    
    # New arguments for evaluate pipeline
    parser.add_argument("--judgement_file", type=str,
                        help="Judgement result file")
    parser.add_argument("--k_ratio", type=str, default="0.8",
                        help="K/N ratio for pass@k calculation")
    
    # Filtering criteria for instruction pipeline
    parser.add_argument("--extract_exercise_info", action="store_true",
                        help="Extract exercise info from the input file")
    
    # Filtering criteria for judgement pipeline
    parser.add_argument("--completeness_levels", type=str, nargs='+',
                        default=["perfect", "minor issues"],
                        help="Acceptable completeness levels (for judgement)")
    parser.add_argument("--accuracy_levels", type=str, nargs='+',
                        default=["perfect"],
                        help="Acceptable accuracy levels (for judgement)")
    parser.add_argument("--scope_levels", type=str, nargs='+',
                        default=["perfect", "minor issues"],
                        help="Acceptable scope levels (for judgement)")
    parser.add_argument("--coding_style_levels", type=str, nargs='+',
                        default=["perfect", "minor issues"],
                        help="Acceptable coding style levels (for judgement)")
    
    # Filtering criteria for verification pipeline
    parser.add_argument("--verification_result", type=str, default="verification_result",
                        help="Verification result to filter on")
    parser.add_argument("--verification_result_threshold", type=str, default="complete",
                        help="Verification result threshold to filter on")
    
    # Output options
    parser.add_argument("--output_format", type=str, choices=["jsonl", "parquet", None],
                        default=None, help="Output file format")
    
    return parser.parse_args()


def filter_instruction_results(data, args):
    """
    Filter instruction generation results based on criteria.
    
    Args:
        data (pd.DataFrame): DataFrame containing instruction generation results
        args (argparse.Namespace): Command line arguments with filtering criteria
    
    Returns:
        pd.DataFrame: Filtered data
    """
    print(f"\nFiltering instruction results with {len(data)} entries...")
    
    # Function to check if a row meets the exercise criteria
    def meets_exercise_criteria(row):
        return (row['majority_difficulty'] is not None and 
                row['majority_task_nature'] is not None and
                row['majority_difficulty'] != 'very easy' and 
                row['majority_task_nature'] != 'superficial')
    
    if args.extract_exercise_info:
        data['exercises'] = data['responses'].apply(lambda x: x[0]['exercises'] if not x[0] is None and x[0].get('exercises') else None)
    data.drop(columns=['responses'], inplace=True)

    # Apply filtering
    filtered_data = data[data.apply(meets_exercise_criteria, axis=1)]   
    
    print(f"Instruction filtering results:")
    print(f"  Original entries: {len(data)}")
    print(f"  Filtered entries: {len(filtered_data)}")
    print(f"  Kept {len(filtered_data)/len(data)*100:.2f}% of entries")
    
    return filtered_data

def filter_circular_reference_patch(row, response):
    after_file = row['file_path_after'].replace('.lean', '').replace('/', '.')
    regex = re.compile(r'import\s+' + after_file + r'(\s|$)')
    return not regex.search(response['best_gen_content'])

def filter_patch_results(data, args):
    """
    Filter patch generation results based on criteria.
    
    Args:
        data (pd.DataFrame): DataFrame containing patch generation results
        args (argparse.Namespace): Command line arguments with filtering criteria
    
    Returns:
        pd.DataFrame: Filtered data
    """
    print(f"\nFiltering patch results with {len(data)} entries...")
    
    items_for_verification = set()

    for _, item in data.iterrows():
        commit_hash = item['commit_hash']
        for response in item['responses']:
            if response is not None and response.get('best_gen_content') and filter_circular_reference_patch(item, response):
                items_for_verification.add((commit_hash, response['best_gen_content']))

    gathered_df = pd.DataFrame(items_for_verification, columns=['commit_hash', 'code'])
    
    print(f"Patch filtering results:")
    print(f"  Original entries: {len(data)}")
    print(f"  Code for verification: {len(gathered_df)}")
    print(f"  Code per entry: {len(gathered_df)/len(data)}")
    
    return gathered_df

def filter_verification_results(data, args):
    """
    Filter verification results based on criteria.
    """
    print(f"\nFiltering verification results with {len(data)} entries...")
    
    filtered_data = data[data.apply(lambda row: row[args.verification_result][args.verification_result_threshold], axis=1)]

    print(f"Verification filtering results:")
    print(f"  Original entries: {len(data)}")
    print(f"  Filtered entries: {len(filtered_data)}")
    print(f"  Kept {len(filtered_data)/len(data)*100:.2f}% of entries")
    
    return filtered_data


def filter_judgement_results(data, args):
    """
    Filter judgement results based on criteria.
    
    Args:
        data (pd.DataFrame): DataFrame containing judgement results
        args (argparse.Namespace): Command line arguments with filtering criteria
    
    Returns:
        pd.DataFrame: Filtered data
    """
    print(f"\nFiltering judgement results with {len(data)} entries...")
    
    # Function to check if a row meets the quality criteria
    def meets_quality_criteria(row):
        counter = Counter()
        for response in row['responses']:
            if response is None:
                continue
            for task_evaluation in response['TaskEvaluations'].values():
                value = task_evaluation.lower()
                if value in ['good', 'excellent']:
                    counter['positive'] += 1
                elif value in ['poor', 'unacceptable']:
                    counter['negative'] += 1
        return counter['positive'] > counter['negative']
        # return (row['majority_judgement'] is not None and 
        #         row['majority_judgement'] in ('good', 'excellent'))
    
    # Apply filtering
    filtered_data = data[data.apply(meets_quality_criteria, axis=1)]
    
    print(f"Judgement filtering results:")
    print(f"  Original entries: {len(data)}")
    print(f"  Filtered entries: {len(filtered_data)}")
    print(f"  Kept {len(filtered_data)/len(data)*100:.2f}% of entries")
    
    return filtered_data


def save_filtered_data(data, output_path, output_format=None):
    """
    Save filtered data to the specified output path.
    
    Args:
        data (pd.DataFrame): Filtered data to save
        output_path (str): Path to save the data (without extension)
        output_format (str): Format to save the data in ('jsonl' or 'parquet')
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    if output_format == 'jsonl' or output_path.endswith('.jsonl'):
        # Save as JSONL
        full_path = f"{output_path}.jsonl" if output_format else output_path
        save_jsonl(data, full_path)
        print(f"Saved {len(data)} entries to {full_path}")
    elif output_format == 'parquet' or output_path.endswith('.parquet'):
        # Save as Parquet
        full_path = f"{output_path}.parquet" if output_format else output_path
        data.to_parquet(full_path, index=False)
        print(f"Saved {len(data)} entries to {full_path}")
    else:
        raise ValueError(f"Unsupported output format: {output_format}")


def process_pipeline(pipeline_type, args):
    """
    Process results for a specific pipeline type.
    
    Args:
        pipeline_type (str): Type of pipeline
        args (argparse.Namespace): Command line arguments
    """
    if args.pipeline == "instruction":
        filter_func = filter_instruction_results
    elif args.pipeline == "patch":
        filter_func = filter_patch_results
    elif args.pipeline == "judgement":
        filter_func = filter_judgement_results
    elif args.pipeline == "verification":
        filter_func = filter_verification_results
    elif args.pipeline == "merge":
        filter_func = merge_original_and_verification
    else:
        raise NotImplementedError("Evaluation pipeline is not implemented yet")
    
    # Special handling for specific pipeline types
    if args.pipeline in ["merge"]:
        # These pipelines don't need to load standard input files
        filtered_data = filter_func(args)
    else:
        # Standard pipelines load input files and process them
        data = load_results(args.input_files)
        
        if len(data) == 0:
            print(f"No data found for {pipeline_type} pipeline. Skipping.")
            return
        
        if args.reset_index_by_date:
            data = data.sort_values(by='date', ascending=False).reset_index(drop=True)
            data['index'] = data.index
        
        # Filter data
        filtered_data = filter_func(data, args)
    
    # Output processing
    if args.output_file is None:
        output_path = os.path.join(
            args.output_dir,
            f"filtered_{pipeline_type}_{args.timestamp}"
        )
    else:
        output_path = args.output_file
    
    save_filtered_data(filtered_data, output_path, args.output_format)

def merge_original_and_verification(args):
    """
    Merge original generation data with verification results
    
    Args:
        args (argparse.Namespace): Command-line arguments
    
    Returns:
        pd.DataFrame: Merged data
    """
    print(f"\nMerging original generation data with verification results...")
    
    # Load verification results
    verification_data = load_results(args.verification_file)
    verification_dict = {}
    for _, item in verification_data.iterrows():
        key = (item['commit_hash'], item['code'])
        verification_dict[key] = item['verification_result']
    
    print(f"Loaded {len(verification_dict)} verification results")
    
    # Load original generation data
    all_original_data = []
    for file_pattern in args.original_files:
        for file in glob.glob(file_pattern):
            file_data = load_results(file)
            file_records = file_data.to_dict('records')
            all_original_data.extend(file_records)
    
    print(f"Loaded {len(all_original_data)} original data entries")
    
    # Extract model information
    merged_data = []
    for item in all_original_data:
        commit_hash = item['commit_hash']
        
        # Get responses and add verification results
        has_verified_response = False
        for response in item.get('responses', []):
            # Try to get generated code
            if response is not None:
                if (code := response.get('best_gen_content')):
                    key = (commit_hash, code)
                    if key in verification_dict:
                        response['verification_result'] = verification_dict[key]
                        has_verified_response = True
                        continue
                response['verification_result'] = {"complete": False}
        
        if has_verified_response:
            merged_data.append(item)
    
    print(f"Created {len(merged_data)} merged entries with verification results")
    
    return pd.DataFrame(merged_data)

def evaluate_full_pipeline(args):
    """
    Calculate full evaluation metrics
    
    Args:
        args (argparse.Namespace): Command-line arguments
    
    Returns:
        pd.DataFrame: Evaluation metrics
    """
    print(f"\nCalculating full pipeline evaluation metrics...")
    
    # Load verification data
    verification_data = load_results(args.verification_file)
    
    # Load judgment data
    judgement_data = load_results(args.judgement_file)
    
    # Extract evaluation results
    verified_results = {}  # model -> temperature -> settings -> (commit, diff, code_before) -> code list
    judged_results = {}    # model -> temperature -> settings -> (commit, diff, code_before) -> code list
    
    # Process verification data
    for _, item in verification_data.iterrows():
        # Collect code that passed verification
        key = (item.get('commit_hash', ''), item.get('gold_diff', ''), item.get('content_before', ''))
        for response in item.get('responses', []):
            if response is None:
                continue

            model_name = response['model']
            temperature = response['inference_params']['temperature']

            if model_name not in verified_results:
                verified_results[model_name] = {}
            
            if temperature not in verified_results[model_name]:
                verified_results[model_name][temperature] = {}
            
            if response.get('verification_result', {}).get('complete', False):
                if response is not None and (code := response.get('best_gen_content')):
                    if key not in verified_results[model_name][temperature]:
                        verified_results[model_name][temperature][key] = []
                    verified_results[model_name][temperature][key].append(code)
    
    # Process judgment data - similar processing but with additional quality score checks
    for _, item in judgement_data.iterrows():
        # Find matching items from original verification data
        commit_hash = item.get('commit_hash', '')
        gold_diff = item.get('gold_diff', '')
        content_before = item.get('content_before', '')
        
        # Look in verification results
        for model_name in verified_results:
            for temperature in verified_results[model_name]:
                key = (commit_hash, gold_diff, content_before)
                if key in verified_results[model_name][temperature]:
                    # Initialize judgment results structure
                    if model_name not in judged_results:
                        judged_results[model_name] = {}
                    
                    if temperature not in judged_results[model_name]:
                        judged_results[model_name][temperature] = {}
                    
                    if key not in judged_results[model_name][temperature]:
                        judged_results[model_name][temperature][key] = []
                    
                    # Check if this is a high-quality judgment
                    if item.get('majority_judgement') in ('good', 'excellent'):
                        for code in verified_results[model_name][temperature][key]:
                            judged_results[model_name][temperature][key].append(code)
    
    # Calculate metrics
    n_values = [int(n) for n in args.n_values.split(',')] if args.n_values else [16]
    k_ratio = float(args.k_ratio) if args.k_ratio else 0.8
    total_data_count = int(args.total_data_count) if args.total_data_count else 100
    
    metrics = {
        "verification": calculate_metrics(verified_results, n_values, k_ratio, total_data_count),
        "judgement": calculate_metrics(judged_results, n_values, k_ratio, total_data_count)
    }
    
    # Save metrics
    with open(args.output_file, 'w') as f:
        json.dump(metrics, f, indent=2)
    
    print(f"Evaluation metrics saved to: {args.output_file}")
    
    # Return empty DataFrame to comply with function signature
    return pd.DataFrame()

def calculate_metrics(results, n_values, k_ratio, total_data_count):
    """
    Calculate pass@k metrics
    
    Args:
        results: Processed results dictionary
        n_values: List of n values
        k_ratio: k/n ratio
        total_data_count: Total data count
    
    Returns:
        Calculated metrics
    """
    metrics = {}
    
    for model in results:
        metrics[model] = {}
        for temperature in results[model]:
            metrics[model][temperature] = {}
            
            # Calculate pass@k for each n value
            for n in n_values:
                k = int(n * k_ratio)
                
                # Get completion counts
                complete_count = [
                    len(codes) for codes in results[model][temperature].values()
                ]
                
                # Pad to total data count
                complete_count += [0] * (total_data_count - len(complete_count))
                
                # Calculate pass@k
                metrics[model][temperature][f"pass@{k}_of_{n}"] = np.mean([
                    pass_at_k(n, c, k) for c in complete_count
                ])
    
    return metrics

def pass_at_k(n, c, k):
    """
    Calculate pass@k metrics
    
    Args:
        n: Total generated
        c: Completed verification/evaluation
        k: k value to evaluate
    
    Returns:
        pass@k metrics
    """
    if n == 0:
        return 0.0
    if n - c < k:
        return 1.0
    return 1.0 - np.prod(1.0 - k / np.arange(n - c + 1, n + 1))

def main():
    """Main entry point"""
    # Parse command line arguments
    args = parse_arguments()
    
    print("\n" + "="*80)
    print(f" ApeBench Results Filter")
    print("="*80)
    
    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Process specified pipelines
    process_pipeline(args.pipeline, args)
    
    print("\n" + "="*80)
    print(" Filtering completed")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()