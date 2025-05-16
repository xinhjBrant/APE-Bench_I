# Copyright (2025) Bytedance Ltd. and/or its affiliates.

"""
Patch verification script, runs the patch verification process according to configuration.
"""

import argparse
import os
import sys
from typing import List, Optional

def main():
    """Script entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Verify generated patches")
    parser.add_argument("--config", type=str, default="config.yaml", help="Configuration file")
    parser.add_argument("--input_files", type=str, nargs="*", help="Optional list of generation output files")
    args = parser.parse_args()
    
    # Ensure src can be imported
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
    
    # Import modules
    from ..evaluation_pipelines.verification_manager import verify_patches
    
    # Execute verification
    metrics = verify_patches(args.config, args.input_files)
    
    print(f"\nVerification completed successfully!")
    
    # Print verification metrics - using Markdown table format
    print("\n## Verification metrics")
    for model, model_metrics in metrics.items():
        print(f"\n### Model: {model}")
        for key in model_metrics:
            temp, n_responses = key.split(',')
            print(f"\nTemperature {temp}, n_responses {n_responses}")
            
            # Create table header
            print("\n| Metric | Value |")
            print("|--------|-------|")
            
            # Create table body
            for metric_name, value in model_metrics[key].items():
                print(f"| {metric_name} | {value:.4f} |")
    
    print(f"\nNext step: Run the evaluation script with the same config file.")

if __name__ == "__main__":
    main()