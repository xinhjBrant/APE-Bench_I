"""
Evaluation management module responsible for executing the patch evaluation process
"""

import os
import subprocess
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from ...utils import load_results, save_jsonl, load_jsonl
from ..utils import ProgressTracker, calculate_metrics, plot_metrics, extract_judgement_data

def filter_verified_data(merged_file: str) -> List[Dict[str, Any]]:
    """
    Filter data that passed verification from the merged file
    
    Args:
        merged_file: Path to the merged results file
        
    Returns:
        List of verified data
    """
    # Load merged data
    with open(merged_file, 'r') as f:
        merged_data = [json.loads(line) for line in f if line.strip()]
    
    # Filter items that passed verification
    verified_data = []
    
    for item in merged_data:
        verified_responses = []
        
        for response in item.get('responses', []):
            # Check verification result
            if response.get('verification_result', {}).get('complete', False):
                verified_responses.append(response)
        
        if verified_responses:
            # Create new item containing only verified responses
            verified_item = item.copy()
            verified_item['responses'] = verified_responses
            verified_data.append(verified_item)
    
    return verified_data

def flatten_results(results):
    """
    Flatten verification results
    """
    flattened_results = []
    for result in results:
        for response in result.get('responses', []):
            if response is not None and response.get('verification_result', {}).get('complete', False):
                if not 'best_gen_patch' in response:
                    best_gen_patch = response['gen_patch']
                    if 'gen_patch_after_exact_repair' in response:
                        best_gen_patch = response['gen_patch_after_exact_repair']
                    if 'gen_patch_after_robust_repair' in response:
                        best_gen_patch = response['gen_patch_after_robust_repair']
                    response['best_gen_patch'] = best_gen_patch
                else:
                    best_gen_patch = response['best_gen_patch']
                flattened_result = result.copy()
                flattened_result['best_gen_patch'] = best_gen_patch
                # flattened_result['patch_generation_responses'] = flattened_result.pop('responses')
                flattened_result.update({k : response[k] for k in ('model', 'usage', 'inference_params', 'verification_result', 'best_gen_content')})
                flattened_result['raw_patch_generation_responses'] = response['raw_response']
                flattened_results.append(flattened_result)
    return flattened_results

def evaluate_patches(config_file: str, merged_results_file: Optional[str] = None) -> Dict[str, Any]:
    """
    Evaluate the quality of verified patches
    
    Args:
        config_file: Path to configuration file
        merged_results_file: Optional path to merged results file
        
    Returns:
        Evaluation metrics
    """
    # Import here instead of at the top to avoid circular imports
    from ..config.config_manager import ConfigManager
    
    # Load configuration
    config = ConfigManager(config_file).get_config()
    
    # Initialize progress tracker
    progress_tracker = ProgressTracker(config.progress_log)
    
    print(f"Running patch evaluation with configuration from: {config_file}")
    
    # Check if evaluation is already completed
    evaluation_status = progress_tracker.get_evaluation_status()
    if evaluation_status.get("completed", False):
        print("Evaluation already completed")
        verification_status = progress_tracker.get_verification_status()
        verification_metrics = verification_status.get("metrics", {})
        judgement_status = progress_tracker.get_judgement_status()
        judgement_metrics = judgement_status.get("metrics", {})
        return verification_metrics, judgement_metrics
    
    # If no merged results file is provided, get it from the progress record
    if not merged_results_file:
        verification_status = progress_tracker.get_verification_status()
        if verification_status.get("completed", False):
            merged_results_file = verification_status.get("merged_results", "")
        else:
            raise ValueError("Verification has not been completed. Run verify_patches first.")
    
    if not merged_results_file or not os.path.exists(merged_results_file):
        raise ValueError(f"Merged results file not found: {merged_results_file}")
    
    print(f"Using merged results file: {merged_results_file}")
    
    # Create temporary and output directories
    os.makedirs(config.temp_dir, exist_ok=True)
    os.makedirs(config.output_dir, exist_ok=True)
    
    # Create timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # 1. Flatten verification results
    print("Flattening verification results...")
    merged_results = load_jsonl(merged_results_file)
    flattened_results = flatten_results(merged_results)
    flattened_results_file = f"{config.temp_dir}/flattened_verification_{timestamp}.jsonl"
    save_jsonl(flattened_results, flattened_results_file)
    print(f"Flattened {len(flattened_results)} results saved to: {flattened_results_file}")

    # 2. Run judgment generation pipeline
    print("Running judgement generation...")
    judgement_output_file = f"{config.output_dir}/judgement_{timestamp}.jsonl"
    
    judgement_cmd = [
        "python", "-m", "src.apebench.inference.run_inference",
        "--pipeline", "judgement",
        "--input_file", flattened_results_file,
        "--output_file", judgement_output_file,
        "--model_name", config.judgement.model_name,
        "--temperature", str(config.judgement.temperature),
        "--n_responses", str(config.judgement.n_responses),
        "--max_workers", str(config.judgement.max_workers)
    ]

    if "max_tokens" in config.judgement and config.judgement["max_tokens"]:
        judgement_cmd.append("--max_tokens")
        judgement_cmd.append(str(config.judgement["max_tokens"]))

    if "thinking_budget_tokens" in config.judgement and config.judgement["thinking_budget_tokens"]:
        judgement_cmd.append("--thinking_budget_tokens")
        judgement_cmd.append(str(config.judgement["thinking_budget_tokens"]))
    
    print(f"Executing: {' '.join(judgement_cmd)}")
    subprocess.run(judgement_cmd, check=True)
    
    # 3. Collect and filter judgment results
    print("Filtering judgement results...")
    filtered_judgement_file = f"{config.output_dir}/filtered_judgement_{timestamp}.jsonl"
    
    filter_cmd = [
        "python", "-m", "src.apebench.evaluation_pipelines.gather_results",
        "--pipeline", "judgement",
        "--input_files", judgement_output_file,
        "--output_file", filtered_judgement_file,
    ]
    
    print(f"Executing: {' '.join(filter_cmd)}")
    subprocess.run(filter_cmd, check=True)
    
    # 4. Calculate final evaluation metrics (using modified gather_results implementation)
    print("Calculating final evaluation metrics...")
    judgement_data = extract_judgement_data(filtered_judgement_file)
    metrics = calculate_metrics(judgement_data, config)

    # 5. Generate visualizations
    if hasattr(config.evaluation, 'generate_plots') and config.evaluation.generate_plots:
        print("Generating judgement metric plots...")
        plots_dir = getattr(config.evaluation, 'plots_dir', './judgement_plots')
        os.makedirs(plots_dir, exist_ok=True)
        plot_metrics(metrics, plots_dir, f'judgement_{timestamp}')

    # 6. Save metrics
    metrics_file = f"{config.output_dir}/judgement_metrics_{timestamp}.json"
    with open(metrics_file, 'w') as f:
        json.dump(metrics, f, indent=2)

    # 7. Update progress tracking
    evaluation_status = {
        "completed": True,
        "timestamp": timestamp,
        "judgement_output": judgement_output_file,
        "filtered_judgement": filtered_judgement_file,
        "metrics_file": metrics_file,
        "metrics": metrics
    }
    
    progress_tracker.update_evaluation_status(evaluation_status)
    
    print(f"Evaluation completed. Results saved to: {metrics_file}")
    
    # 9. Reload verification metrics
    verification_status = progress_tracker.get_verification_status()
    verification_metrics = verification_status.get("metrics", {})

    return verification_metrics, metrics