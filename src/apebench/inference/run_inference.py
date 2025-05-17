# Copyright (2025) Bytedance Ltd. and/or its affiliates.

#!/usr/bin/env python3
"""
Unified entry point for the ApeBench pipeline system.

This script provides a command-line interface to run different data processing
pipelines for the ApeBench system, including instruction generation, patch 
generation, and judgment generation.
"""

import argparse
import os
import sys
from datetime import datetime

# Import pipeline classes
from .inference_pipelines import GenerateInstructionPipeline, GeneratePatchPipeline, GenerateJudgementPipeline

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="ApeBench Unified Pipeline Entry Point")
    
    # General arguments for all pipelines
    parser.add_argument("--pipeline", type=str, required=True, 
                      choices=["instruction", "patch", "judgement"],
                      help="Pipeline type to run")
    parser.add_argument("--input_file", type=str, required=True, help="Path to the input file")
    parser.add_argument("--output_dir", type=str, default="./outputs", 
                      help="Directory to save output files")
    parser.add_argument("--output_file", type=str, 
                      help="Path to the output file (if not specified, will be auto-generated)")
    parser.add_argument("--log_dir", type=str, default="./logs", 
                      help="Directory to save log files")
    parser.add_argument("--timestamp", type=str, 
                      help="Timestamp to use for filenames (default: current time)")
    parser.add_argument("--max_workers", type=int, default=1, 
                      help="Maximum number of parallel workers")
    parser.add_argument("--max_retries", type=int, default=10, 
                      help="Maximum number of retries for failed rows")
    parser.add_argument("--model_name", type=str, required=True, 
                      help="Name of the model to use for inference")
    parser.add_argument("--n_responses", type=int, default=1, 
                      help="Number of responses to generate for each input")
    parser.add_argument("--temperature", type=float, default=0.0, 
                      help="Temperature for the model")
    parser.add_argument("--max_tokens", type=int, default=8000, 
                      help="Maximum number of tokens to generate")
    parser.add_argument("--thinking_budget_tokens", type=int, default=6000, 
                      help="Budget tokens for thinking")
    
    # Arguments specific to the instruction pipeline
    parser.add_argument("--gold_diff_key", type=str, default="gold_diff", 
                      help="Key in the input data for the gold diff (for instruction pipeline)")
    
    # Arguments specific to the judgment pipeline
    parser.add_argument("--patch_key", type=str, default="best_gen_patch_comment_free", 
                      help="Key in the input data for the patch to judge (for judgment pipeline)")
    
    # Arguments specific to the patch pipeline
    parser.add_argument("--force_complete_prompt", action="store_true", 
                      help="Force complete prompt")
    parser.add_argument("--force_reasoning_prompt", action="store_true", 
                      help="Force consise prompt")
    
    return parser.parse_args()

def select_pipeline(args):
    """Select the appropriate pipeline based on arguments"""
    if args.pipeline == "instruction":
        return GenerateInstructionPipeline(args)
    elif args.pipeline == "patch":
        return GeneratePatchPipeline(args)
    elif args.pipeline == "judgement":
        return GenerateJudgementPipeline(args)
    else:
        raise ValueError(f"Unknown pipeline type: {args.pipeline}")

def main():
    """Main entry point"""
    # Parse command line arguments
    args = parse_arguments()
    
    # Set default timestamp if not provided
    if args.timestamp is None:
        args.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Create log directory if it doesn't exist
    os.makedirs(args.log_dir, exist_ok=True)
    
    # Print banner
    print("\n" + "="*80)
    print(f" ApeBench Pipeline: {args.pipeline.upper()}")
    print("="*80 + "\n")
    
    # Select and initialize the appropriate pipeline
    pipeline = select_pipeline(args)
    
    # Run the pipeline
    print(f"Starting {args.pipeline} pipeline with model {args.model_name}...\n")
    total_processed, total_errors, failed_indices = pipeline.process_data()
    
    # Print summary
    print("\n" + "="*80)
    print(f" SUMMARY: {args.pipeline.upper()} PIPELINE")
    print("="*80)
    print(f"Total processed: {total_processed}")
    print(f"Total errors: {total_errors}")
    print(f"Failed indices: {len(failed_indices)}")
    print(f"Success rate: {(total_processed / (total_processed + total_errors) if total_processed + total_errors > 0 else 0) * 100:.2f}%")
    print("="*80 + "\n")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())