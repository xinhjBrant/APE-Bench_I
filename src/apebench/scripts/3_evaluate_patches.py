# Copyright (2025) Bytedance Ltd. and/or its affiliates.

#!/usr/bin/env python3
"""
Patch evaluation script, runs the patch evaluation process according to configuration.
"""

import argparse
import os
import sys
import json
from typing import Dict, Any, Optional

def main():
    """Script entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Evaluate verified patches")
    parser.add_argument("--config", type=str, default="config.yaml", help="Configuration file")
    parser.add_argument("--merged_file", type=str, help="Optional merged results file from verification")
    args = parser.parse_args()
    
    # Ensure src can be imported
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
    
    # Import modules
    from ..evaluation_pipelines.evaluation_manager import evaluate_patches
    
    # Execute evaluation
    verification_metrics, metrics = evaluate_patches(args.config, args.merged_file)
    
    # Print result summary
    print("\nEvaluation completed successfully!")
    print("Metrics summary:")
    
    # Print verification metrics - using Markdown table format
    print("\n## Verification metrics")
    for model, model_metrics in verification_metrics.items():
        print(f"\n### Model: {model}")
        for key in model_metrics:
            temp, n_responses = key.split(',')
            print(f"\nTemperature {temp}, n_responses {n_responses}")
            
            # Create table header
            print("\n| Metric | Value |")
            print("|--------|-------|")
            
            # Create table body
            for metric_name, value in model_metrics[key].items():
                print(f"| {metric_name} | {value * 100:.2f}% |")
    
    # Print judgment metrics - using Markdown table format
    print("\n## Judgement metrics")
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
                print(f"| {metric_name} | {value * 100:.2f}% |")
    
if __name__ == "__main__":
    main()