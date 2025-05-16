# Copyright (2025) Bytedance Ltd. and/or its affiliates.

#!/usr/bin/env python3
"""
Data collection script that runs the dataset creation process according to configuration.
"""

import argparse
import os
import sys
import subprocess
import multiprocessing
from datetime import datetime
from typing import Dict, Any
import pandas as pd

def main():
    """Script entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Collect and process dataset")
    parser.add_argument("--config", type=str, default="config.yaml", help="Configuration file")
    parser.add_argument("--repo_path", type=str, default="mathlib4", help="Math library repository path")
    parser.add_argument("--dataset_dir", type=str, default="datasets", help="Dataset output directory")
    parser.add_argument("--max_diff_lines", type=int, default=100, help="Maximum diff lines")
    parser.add_argument("--workers", type=int, default=multiprocessing.cpu_count(), help="Number of parallel worker processes")
    parser.add_argument("--latest_num_data", type=int, default=2000, help="Number of latest data points to extract")
    parser.add_argument("--instruction_model_name", type=str, default="aws_sdk_claude37_sonnet@thinking", help="Model for instruction generation")
    parser.add_argument("--judgement_model_name", type=str, default="aws_sdk_claude37_sonnet@thinking", help="Model for judgement generation")
    args = parser.parse_args()
    
    # Create output directory
    os.makedirs(args.dataset_dir, exist_ok=True)
    
    # Set timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Repository path
    repo_path = args.repo_path
    
    # Check if repository exists, clone if it doesn't
    if not os.path.exists(repo_path):
        print(f"Cloning Mathlib4 to {repo_path}")
        subprocess.run(["git", "clone", "https://github.com/leanprover-community/mathlib4.git", repo_path], check=True)
    else:
        print(f"Repository {repo_path} already exists, skipping clone")
    
    # Set file paths
    mathlib_name = os.path.basename(repo_path)
    data_collection_path = os.path.join(
        args.dataset_dir, 
        f"{mathlib_name}_commits_data_{timestamp}_{args.max_diff_lines}.parquet"
    )
    
    # Collect commit data
    print(f"Collecting commit data to {data_collection_path}")
    collect_cmd = [
        "python", "-m", "src.apebench.data.collect_commit_data",
        "--repo_path", repo_path,
        "--output_path", data_collection_path,
        "--workers", str(args.workers),
        "--max_diff_lines", str(args.max_diff_lines)
    ]
    subprocess.run(collect_cmd, check=True)
    
    # Filter data
    filtered_data_path = os.path.join(
        args.dataset_dir, 
        f"filtered_{mathlib_name}_commits_data_{timestamp}_{args.max_diff_lines}.parquet"
    )
    length_distribution_path = os.path.join(
        args.dataset_dir, 
        f"filtered_{mathlib_name}_commits_data_{timestamp}_{args.max_diff_lines}_length_distribution.png"
    )
    waterfall_chart_path = os.path.join(
        args.dataset_dir, 
        f"filtered_{mathlib_name}_commits_data_{timestamp}_{args.max_diff_lines}_waterfall.pdf"
    )
    
    print(f"Filtering data to {filtered_data_path}")
    filter_cmd = [
        "python", "-m", "src.apebench.data.filter_commit_data",
        "--file_path", data_collection_path,
        "--output_path", filtered_data_path,
        "--length_distribution_plot_path", length_distribution_path,
        "--waterfall_chart_path", waterfall_chart_path
    ]
    subprocess.run(filter_cmd, check=True)
    
    # Build database (using eleanstic)
    print("Building database")
    build_cmd = [
        "python", "-m", "src.eleanstic.main",
        "--max-workers", str(args.workers),
        "--input-file", filtered_data_path,
        "build"
    ]
    subprocess.run(build_cmd, check=True)
    
    # Verify filtered data
    verify_result_dir = os.path.join(
        args.dataset_dir, 
        f"verify_results/filtered_{mathlib_name}_commits_data_{timestamp}_{args.max_diff_lines}"
    )
    os.makedirs(verify_result_dir, exist_ok=True)
    
    print("Verifying filtered data")
    verify_cmd = [
        "python", "-m", "src.eleanstic.main",
        "--max-workers", str(args.workers),
        "--input-file", filtered_data_path,
        "verify",
        "--code-key", "content_after",
        "--results-dir", verify_result_dir
    ]
    subprocess.run(verify_cmd, check=True)
    
    # Filter verified data
    verified_data_path = os.path.join(
        args.dataset_dir, 
        f"filtered_{mathlib_name}_commits_data_{timestamp}_{args.max_diff_lines}_verified.jsonl"
    )
    
    print("Filtering verified data")
    filter_verified_cmd = [
        "python", "-m", "src.apebench.evaluation_pipelines.gather_results",
        "--pipeline", "verification",
        "--input_files", f"{verify_result_dir}/*.jsonl",
        "--output_file", verified_data_path,
        "--reset_index_by_date",
        "--output_format", "jsonl"
    ]
    subprocess.run(filter_verified_cmd, check=True)
    
    # Extract the latest N data points
    latest_data_path = os.path.join(
        args.dataset_dir,
        f"filtered_{mathlib_name}_commits_data_{timestamp}_{args.max_diff_lines}_verified_latest_{args.latest_num_data}.jsonl"
    )
    
    print(f"Extracting the latest {args.latest_num_data} data points")
    df = pd.read_parquet(verified_data_path)
    df.sort_values(by='date', ascending=False, inplace=True)
    df = df.head(args.latest_num_data)
    df.to_json(latest_data_path, orient='records', lines=True)
    
    # Create directories for outputs
    gen_output_dir = "outputs"
    instruction_output_dir = os.path.join(gen_output_dir, "instruction")
    judgement_output_dir = os.path.join(gen_output_dir, "judgement")
    os.makedirs(instruction_output_dir, exist_ok=True)
    os.makedirs(judgement_output_dir, exist_ok=True)
    os.makedirs(os.path.join(args.dataset_dir, "instruction"), exist_ok=True)
    os.makedirs(os.path.join(args.dataset_dir, "judgement"), exist_ok=True)
    
    # Generate instruction data
    instruction_output_path = os.path.join(
        instruction_output_dir,
        f"filtered_{mathlib_name}_commits_data_{timestamp}_{args.max_diff_lines}_verified_latest_{args.latest_num_data}_instruction_{args.instruction_model_name}.jsonl"
    )
    
    print("Generating instruction data")
    instruction_cmd = [
        "python", "-m", "src.apebench.inference.run_inference",
        "--pipeline", "instruction",
        "--input_file", latest_data_path,
        "--output_file", instruction_output_path,
        "--model_name", args.instruction_model_name,
        "--max_workers", str(args.workers),
        "--n_responses", "1",
        "--temperature", "0",
        "--max_tokens", "20000",
        "--thinking_budget_tokens", "16000"
    ]
    subprocess.run(instruction_cmd, check=True)
    
    # Filter instruction results
    instruction_data_path = os.path.join(
        args.dataset_dir,
        "instruction",
        f"filtered_{mathlib_name}_commits_data_{timestamp}_{args.max_diff_lines}_verified_latest_{args.latest_num_data}_instruction_{args.instruction_model_name}.jsonl"
    )
    
    print("Filtering instruction results")
    filter_instruction_cmd = [
        "python", "-m", "src.apebench.collect.filter_results",
        "--pipeline", "instruction",
        "--input_files", instruction_output_path,
        "--output_file", instruction_data_path,
        "--extract_exercise_info"
    ]
    subprocess.run(filter_instruction_cmd, check=True)
    
    # Generate judgement data
    judgement_output_path = os.path.join(
        judgement_output_dir,
        f"filtered_{mathlib_name}_commits_data_{timestamp}_{args.max_diff_lines}_verified_latest_{args.latest_num_data}_judgement_{args.judgement_model_name}.jsonl"
    )
    
    print("Verifying through judgement of gold diff")
    judgement_cmd = [
        "python", "-m", "src.apebench.inference.run_inference",
        "--pipeline", "judgement",
        "--input_file", instruction_data_path,
        "--output_file", judgement_output_path,
        "--model_name", args.judgement_model_name,
        "--max_workers", str(args.workers),
        "--n_responses", "1",
        "--temperature", "0",
        "--max_tokens", "20000",
        "--thinking_budget_tokens", "16000",
        "--patch_key", "gold_diff"
    ]
    subprocess.run(judgement_cmd, check=True)
    
    # Filter judgement results
    judgement_data_path = os.path.join(
        args.dataset_dir,
        "judgement",
        f"filtered_{mathlib_name}_commits_data_{timestamp}_{args.max_diff_lines}_verified_latest_{args.latest_num_data}_judgement_{args.judgement_model_name}.jsonl"
    )
    
    print("Filtering judgement results")
    filter_judgement_cmd = [
        "python", "-m", "src.apebench.collect.filter_results",
        "--pipeline", "judgement",
        "--input_files", judgement_output_path,
        "--output_file", judgement_data_path
    ]
    subprocess.run(filter_judgement_cmd, check=True)
    
    # Print results
    print(f"\nData collection complete!")
    print(f"Generated the following key files:")
    print(f"- Raw commit data: {data_collection_path}")
    print(f"- Filtered data: {filtered_data_path}")
    print(f"- Length distribution plot: {length_distribution_path}")
    print(f"- Waterfall chart: {waterfall_chart_path}")
    print(f"- Verification results directory: {verify_result_dir}")
    print(f"- Verified data: {verified_data_path}")
    print(f"- Latest data: {latest_data_path}")
    print(f"- Instruction data: {instruction_data_path}")
    print(f"- Judgement data: {judgement_data_path}")
    print(f"- Final data path: {judgement_data_path}")

if __name__ == "__main__":
    main()