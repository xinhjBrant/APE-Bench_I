# Copyright (2025) Bytedance Ltd. and/or its affiliates.

"""
Evaluation metrics calculation module, refactored based on temp_fix.py
"""

import os
import json
import numpy as np
from typing import Dict, List, Any, Tuple, Set
from collections import defaultdict
import pandas as pd
import matplotlib.pyplot as plt
from glob import glob
from ...utils import *
from ..inference.utils import UNSUPPORT_TEMPERATURE_MODELS
from ...utils.colors import ColorPicker

def pass_at_k(n: int, c: int, k: int) -> float:
    """
    Calculate pass@k metric
    
    Args:
        n: Total number of generations
        c: Number of generations that passed verification/evaluation
        k: k value to evaluate
    
    Returns:
        pass@k metric value
    """
    if n == 0:
        return 0.0
    if n - c < k:
        return 1.0
    return 1.0 - np.prod(1.0 - k / np.arange(n - c + 1, n + 1))

def extract_verification_data(merged_file: str) -> Dict[str, Dict[str, Dict[str, Dict[Tuple, List[str]]]]]:
    """
    Extract verification data from merged file, organized by model, temperature and configuration
    
    Args:
        merged_file: Path to merged results file
    
    Returns:
        Nested dictionary: {model: {temperature: {setting: {(commit_hash, gold_diff, content_before): [verified_codes]}}}}
    """
    # Load merged data
    merged_data = load_results(merged_file)
    
    # Organize results
    verified_results = {}
    # Process verification data
    for _, item in merged_data.iterrows():
        # Collect verified code
        key = (item.get('commit_hash', ''), item.get('gold_diff', ''), item.get('content_before', ''))
        for response in item.get('responses', []):
            if response is None:
                continue
            
            model_name = response['model']
            temperature = response['inference_params']['temperature']
            n_responses = response['inference_params']['n_responses']

            if model_name not in verified_results:
                verified_results[model_name] = {}
            
            if f"{temperature},{n_responses}" not in verified_results[model_name]:
                verified_results[model_name][f"{temperature},{n_responses}"] = defaultdict(list)
            
            if response.get('verification_result', {}).get('complete', False):
                if response is not None and (code := response.get('best_gen_content')):
                    verified_results[model_name][f"{temperature},{n_responses}"][key].append(code)
    
    return verified_results

def extract_judgement_data(judgement_file: str) -> Dict[str, Dict[str, Dict[str, Dict[str, float]]]]:
    """
    Extract judgment data from judgment file, organized by model, temperature and configuration
    """
    judgement_data = load_results(judgement_file)
    # Organize results
    verified_results = {}
    for _, item in judgement_data.iterrows():
        key = (item.get('commit_hash', ''), item.get('gold_diff', ''), item.get('content_before', ''))
        model_name = item['model']
        temperature = item['inference_params']['temperature']
        n_responses = item['inference_params']['n_responses']
        if model_name not in verified_results:
            verified_results[model_name] = {}
        if f"{temperature},{n_responses}" not in verified_results[model_name]:
            verified_results[model_name][f"{temperature},{n_responses}"] = defaultdict(list)
        verified_results[model_name][f"{temperature},{n_responses}"][key].append(item['best_gen_patch'] if 'best_gen_patch' in item else item['gen_patch'])
    return verified_results
            

def calculate_metrics(results: Dict, config: Any) -> Dict[str, Dict[str, Dict[str, Dict[str, float]]]]:
    """
    Calculate verification metrics
    
    Args:
        results: Verification results from extract_verification_data
        config: Configuration object or dictionary
    
    Returns:
        Calculated metrics
    """
    input_data = load_results(config.input_file)
    total_data_count = len(input_data)
    k_ratio = getattr(config.evaluation, 'k_ratio', 0.8)
    
    metrics = {}
    for model_config in config.generation.models:
        model_name = model_config["name"]
        metrics[model_name] = {}
        for config in model_config["configs"]:
            temperature = config["temperature"]
            n_responses = config["n_responses"]
            metrics[model_name][f"{temperature},{n_responses}"] = {}
            for k in range(1, max(1, int(n_responses * k_ratio)) + 1):
                metrics[model_name][f"{temperature},{n_responses}"][f"pass@{k}_of_{n_responses}"] = 0.0
    
    for model in results:
        for key in results[model]:
            n_responses = int(key.split(',')[1])
            # Get pass count
            complete_count = [
                len(codes) for codes in results[model][key].values()
            ]
            
            # If samples are fewer than total data count, fill to total data count
            complete_count += [0] * (total_data_count - len(complete_count))
            # Calculate pass@k for each n value
            for k in range(1, max(1, int(n_responses * k_ratio)) + 1):
                # Calculate pass@k
                metrics[model][key][f"pass@{k}_of_{n_responses}"] = np.mean([
                    pass_at_k(n_responses, c, k) for c in complete_count
                ])
    
    return metrics

def plot_metrics(metrics: Dict[str, Dict[str, Dict[str, Dict[str, float]]]], output_dir: str, name: str) -> None:
    """
    Plot verification metrics charts
    
    Args:
        metrics: Calculated metrics
        output_dir: Output directory
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Create completion rate chart
    plt.figure(figsize=(12, 8))
    
    # Import color utilities
    import re
    from ...utils.colors import ColorPicker
    
    # Create color picker
    color_picker = ColorPicker()
    
    # Get count of all model and configuration combinations
    model_configs = []
    for model in metrics:
        for key in metrics[model]:
            model_configs.append((model, key))
    
    k_regex = re.compile(r'pass@(\d+)_of_(\d+)')
    for model in metrics:
        for key in metrics[model]:
            temperature, _ = key.split(',')
            k_rates = []
            for k in metrics[model][key]:
                match = k_regex.match(k)
                if match:
                    k_rates.append((int(match.group(1)), metrics[model][key][k]))
            k_rates.sort(key=lambda x: x[0])
            k_list = [x[0] for x in k_rates]
            pass_list = [x[1] for x in k_rates]
            label = f'{model}(T={temperature})' if not model in UNSUPPORT_TEMPERATURE_MODELS else f'{model}'
            
            # Get color using ColorPicker
            color = color_picker.get_color()
            
            if len(k_rates) == 1:
                plt.scatter(k_list, pass_list, label=label, s=20, marker='o', color=color)
            else:
                plt.plot(k_list, pass_list, label=label, 
                        linestyle='-', linewidth=2.5, color=color)
    
    # Set chart parameters
    plt.xlabel('k', fontsize=14)
    plt.ylabel('pass@k', fontsize=14)
    plt.grid(True, linestyle='--', alpha=0.3)
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=10)
    
    # Remove top and right borders
    ax = plt.gca()
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_linewidth(1.5)
    ax.spines['left'].set_linewidth(1.5)
    
    plt.tight_layout()
    
    # Save image
    plt.savefig(os.path.join(output_dir, f'{name}_metrics.pdf'), dpi=300, bbox_inches='tight')
    plt.close()

def plot_combined_metrics(verification_metrics: Dict, judgement_metrics: Dict, output_dir: str, timestamp: str) -> None:
    """
    Plot verification and judgement metrics side by side with a shared legend
    
    Args:
        verification_metrics: Calculated verification metrics
        judgement_metrics: Calculated judgement metrics
        output_dir: Output directory
        timestamp: Timestamp for the output file name
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Create a figure with two subplots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 6))
    
    # Import regex
    import re
    
    # Dictionary to track colors for each model
    model_colors = {}
    
    # Regular expression to extract k values
    k_regex = re.compile(r'pass@(\d+)_of_(\d+)')
    
    # Plot handles for legend
    plot_handles = []
    plot_labels = []
    
    # First pass: assign colors to all models
    all_models = set()
    for metrics in [verification_metrics, judgement_metrics]:
        for model in metrics:
            for key in metrics[model]:
                temperature, _ = key.split(',')
                label = f'{model}(T={temperature})' if model not in UNSUPPORT_TEMPERATURE_MODELS else f'{model}'
                all_models.add(label)
    
    # Assign colors to all models first
    # Create color picker
    color_picker = ColorPicker()
    for model in all_models:
        if 'T=0.0' in model:
            model_colors[model] = color_picker.get_color()

    color_picker = ColorPicker()
    for model in all_models:
        if 'T=0.0' not in model:
            model_colors[model] = color_picker.get_color()
    
    # First determine the y-axis range from verification metrics
    verification_values = []
    for model in verification_metrics:
        for key in verification_metrics[model]:
            for k in verification_metrics[model][key]:
                match = k_regex.match(k)
                if match:
                    verification_values.append(verification_metrics[model][key][k])
    
    y_min = 0
    y_max = 1.0
    if verification_values:
        y_max = min(1.0, max(verification_values) * 1.1)  # Add some padding above
    
    # Function to plot metrics on a given axes
    def plot_metric_on_axes(ax, metrics, title):
        for model in metrics:
            for key in metrics[model]:
                temperature, _ = key.split(',')
                k_rates = []
                for k in metrics[model][key]:
                    match = k_regex.match(k)
                    if match:
                        k_rates.append((int(match.group(1)), metrics[model][key][k]))
                
                if not k_rates:
                    continue
                    
                k_rates.sort(key=lambda x: x[0])
                k_list = [x[0] for x in k_rates]
                pass_list = [x[1] for x in k_rates]
                
                label = f'{model}(T={temperature})' if model not in UNSUPPORT_TEMPERATURE_MODELS else f'{model}'
                color = model_colors[label]
                
                if len(k_rates) == 1:
                    line = ax.scatter(k_list, pass_list, s=10, marker='o', color=color)
                else:
                    line = ax.plot(k_list, pass_list, linestyle='-', linewidth=2, color=color)[0]
                
                # Only add to legend once
                if label not in plot_labels:
                    plot_handles.append(line)
                    plot_labels.append(label)
        
        # Configure axes
        ax.set_title(title, fontsize=16)
        ax.set_xlabel('k', fontsize=14)
        ax.set_ylabel('pass@k', fontsize=14)
        ax.grid(True, linestyle='--', alpha=0.3)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_linewidth(1.5)
        ax.spines['left'].set_linewidth(1.5)
        ax.set_ylim(y_min, y_max)  # Set y-axis limits based on verification metrics
    
    # Plot verification metrics (left subplot)
    plot_metric_on_axes(ax1, verification_metrics, 'Lean Compile')
    
    # Plot judgement metrics (right subplot)
    plot_metric_on_axes(ax2, judgement_metrics, 'LLM Judge')
    
    # Add shared legend at the bottom
    legend = fig.legend(
        handles=plot_handles,
        labels=plot_labels,
        loc='lower center', 
        ncol=min(3, len(plot_labels)),  # Adjust columns based on number of models
        bbox_to_anchor=(0.5, -0.05),
        fontsize=10,
        frameon=False  # Remove legend border
    )
    
    plt.tight_layout()
    # Adjust layout to make room for the legend
    plt.subplots_adjust(bottom=0.2)
    
    # Save image
    plt.savefig(os.path.join(output_dir, f'combined_metrics_{timestamp}.pdf'), dpi=300, bbox_inches='tight')
    plt.close()

if __name__ == "__main__":
    from ..config.config_manager import ConfigManager
    from ..utils import ProgressTracker
    # Load configuration
    config_file = './configs/combined_config.yaml'
    config = ConfigManager(config_file).get_config()
    
    progress_tracker = ProgressTracker(config.progress_log)

    timestamp = '20250406_223837'
    timestamp = 'combined'
    # merged_results_file = f'./outputs/merged_results_{timestamp}.jsonl'
    # verified_results = extract_verification_data(merged_results_file)
    # metrics = calculate_metrics(verified_results, config)
    plots_dir = getattr(config.evaluation, 'plots_dir', './verification_plots')
    os.makedirs(plots_dir, exist_ok=True)
    verification_status = progress_tracker.get_verification_status()
    verification_metrics = verification_status.get("metrics", {})
    plot_metrics(verification_metrics, plots_dir, f'verification_combined_{timestamp}')

    # filtered_judgement_file = f'./outputs/filtered_judgement_{timestamp}.jsonl'
    # judgement_data = extract_judgement_data(filtered_judgement_file)
    # metrics = calculate_metrics(judgement_data, config)
    judgement_status = progress_tracker.get_evaluation_status()
    judgement_metrics = judgement_status.get("metrics", {})
    plot_metrics(judgement_metrics, plots_dir, f'judgement_combined_{timestamp}')
    
    # Call new function to create combined chart
    plot_combined_metrics(verification_metrics, judgement_metrics, plots_dir, timestamp)