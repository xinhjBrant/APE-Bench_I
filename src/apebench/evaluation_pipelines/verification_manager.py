# Copyright (2025) Bytedance Ltd. and/or its affiliates.
"""
Verification management module responsible for executing the patch verification process
"""

import os
import subprocess
import glob
from datetime import datetime
from typing import Dict, List, Any, Optional, Union

from ..utils import ProgressTracker, extract_verification_data, calculate_metrics, plot_metrics

def get_latest_results_dir(base_dir: str) -> str:
    """
    Get the latest results directory
    
    Args:
        base_dir: Base directory
        
    Returns:
        Path to the latest results directory
    """
    result_dirs = glob.glob(f"{base_dir}*")
    if not result_dirs:
        raise ValueError(f"No result directories found in {base_dir}")
    
    # Sort by timestamp
    latest_dir = max(result_dirs, key=os.path.getctime)
    return latest_dir

def verify_patches(config_file: str, generation_output_files: Optional[List[str]] = None) -> str:
    """
    Verify generated patches
    
    Args:
        config_file: Path to configuration file
        generation_output_files: Optional list of generation output files
        
    Returns:
        Path to the merged results file
    """
    # Import here instead of at the top to avoid circular imports
    from ..config.config_manager import ConfigManager
    
    # Load configuration
    config = ConfigManager(config_file).get_config()
    
    # Initialize progress tracker
    progress_tracker = ProgressTracker(config.progress_log)
    
    print(f"Running patch verification with configuration from: {config_file}")
    
    # Check if verification is already completed
    verification_status = progress_tracker.get_verification_status()
    if verification_status.get("completed", False):
        print("Verification already completed")
        verification_status = progress_tracker.get_verification_status()
        verification_metrics = verification_status.get("metrics", {})
        return verification_metrics
    
    # If no output files are provided, get them from the progress record
    if not generation_output_files:
        generation_output_files = progress_tracker.get_all_output_files()
        
    if not generation_output_files:
        raise ValueError("No generation output files found. Run patch generation first.")
    
    print(f"Found {len(generation_output_files)} generation output files")
    
    # Create temporary directory
    os.makedirs(config.temp_dir, exist_ok=True)
    
    # Create timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # 1. Use gather_results.py to collect patch data
    print("Collecting patches for verification...")
    patch_collection_file = f"{config.temp_dir}/patches_for_verification_{timestamp}.jsonl"
    
    # Build gather_results.py command to collect patches
    collect_cmd = [
        "python", "-m", "src.apebench.evaluation_pipelines.gather_results",
        "--pipeline", "patch",
        "--input_files", *generation_output_files,
        "--output_file", patch_collection_file,
    ]
    
    print(f"Executing: {' '.join(collect_cmd)}")
    subprocess.run(collect_cmd, check=True)
    
    # 2. Call eleanstic to perform verification
    print("Running Eleanstic verification...")
    verify_results_dir = os.path.join(config.verification.results_dir, f"results_{timestamp}")
    # Ensure results directory exists
    os.makedirs(verify_results_dir, exist_ok=True)
    
    verify_cmd = [
        "python", "-m", "src.eleanstic.main",
        "--input_file", patch_collection_file,
        "--commit_id_key", "commit_hash",
        "--max_workers", str(config.verification.max_workers),
        "verify",
        "--code_key", "code",
        "--results_dir", verify_results_dir
    ]
    
    print(f"Executing: {' '.join(verify_cmd)}")
    subprocess.run(verify_cmd, check=True)
    
    # 3. Use gather_results.py to collect verification results
    print("Collecting verification results...")
    verification_output_file = f"{config.temp_dir}/verification_results_{timestamp}.jsonl"
    
    verify_collect_cmd = [
        "python", "-m", "src.apebench.evaluation_pipelines.gather_results",
        "--pipeline", "verification",
        "--input_files", f"{verify_results_dir}/*.jsonl",
        "--output_file", verification_output_file,
    ]
    
    print(f"Executing: {' '.join(verify_collect_cmd)}")
    subprocess.run(verify_collect_cmd, check=True)
    
    # 4. Merge verification results with original generation data
    print("Merging verification results with original data...")
    merged_results_file = f"{config.output_dir}/merged_results_{timestamp}.jsonl"
    os.makedirs(os.path.dirname(merged_results_file), exist_ok=True)
    
    # Call gather_results.py merge functionality
    merge_cmd = [
        "python", "-m", "src.apebench.evaluation_pipelines.gather_results",
        "--pipeline", "merge",  # New pipeline type
        "--original_files", *generation_output_files,
        "--verification_file", verification_output_file,
        "--output_file", merged_results_file,
    ]
    
    print(f"Executing: {' '.join(merge_cmd)}")
    subprocess.run(merge_cmd, check=True)
    
    # 5. Calculate pass@k metrics for each model
    print("Calculating verification metrics...")
    verified_results = extract_verification_data(merged_results_file)
    metrics = calculate_metrics(verified_results, config)
    
    # 6. Generate visualizations
    if hasattr(config.evaluation, 'generate_plots') and config.evaluation.generate_plots:
        print("Generating verification metric plots...")
        plots_dir = getattr(config.evaluation, 'plots_dir', './verification_plots')
        os.makedirs(plots_dir, exist_ok=True)
        plot_metrics(metrics, plots_dir, f'verification_{timestamp}')
        print(f"Verification metric plots saved to: {plots_dir}")
    
    # 7. Save metrics
    metrics_file = f"{config.output_dir}/verification_metrics_{timestamp}.json"
    
    import json
    print('Saving verification metrics to: ', metrics_file)
    print('Metrics: ', metrics)
    with open(metrics_file, 'w') as f:
        json.dump(metrics, f, indent=2)
    
    # 8. Update progress tracking
    verification_status = {
        "completed": True,
        "timestamp": timestamp,
        "verification_output": verification_output_file,
        "merged_results": merged_results_file,
        "metrics_file": metrics_file,
        "metrics": metrics
    }
    
    progress_tracker.update_verification_status(verification_status)
    
    print(f"Verification completed. Results saved to: {merged_results_file}")
    
    return metrics