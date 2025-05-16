# Copyright (2025) Bytedance Ltd. and/or its affiliates.
"""
Patch Generation Management Module, responsible for executing the patch generation workflow
"""

import os
import subprocess
import concurrent.futures
from datetime import datetime
from typing import Dict, List, Any, Optional
import time
import re

from ..utils import ProgressTracker

def generate_patches(config_file: str) -> List[str]:
    """
    Run patch generation tasks according to configuration
    
    Args:
        config_file: Configuration file path
        
    Returns:
        List of generated output file paths
    """
    # Import here instead of at the top to avoid circular imports
    from ..config.config_manager import ConfigManager
    
    # Load configuration
    config = ConfigManager(config_file).get_config()
    
    # Initialize progress tracker
    progress_tracker = ProgressTracker(config.progress_log)
    
    print(f"Running patch generation with configuration from: {config_file}")
    
    # Create output directory
    os.makedirs(config.generation.base_output_dir, exist_ok=True)
    
    # Prepare tasks for each model
    model_tasks = []
    for model_config in config.generation.models:
        model_name = model_config["name"]
        model_tasks.append({
            "model_name": model_name,
            "configs": model_config["configs"],
            "input_file": config.input_file,
            "output_dir": config.generation.base_output_dir,
            "progress_file": config.progress_log  # Pass progress file path instead of progress_tracker object
        })
    
    print(f"Prepared {len(model_tasks)} model tasks")
    
    # Execute model tasks (parallel or sequential)
    if config.generation.parallel_models:
        print(f"Running models in parallel with {config.generation.max_model_workers} workers")
        with concurrent.futures.ProcessPoolExecutor(max_workers=config.generation.max_model_workers) as executor:
            futures = {executor.submit(process_model_task, task): task["model_name"] for task in model_tasks}
            
            for future in concurrent.futures.as_completed(futures):
                model_name = futures[future]
                try:
                    results = future.result()
                    print(f"Completed all configurations for model: {model_name}")
                except Exception as e:
                    print(f"Error processing model {model_name}: {e}")
    else:
        print("Running models sequentially")
        for task in model_tasks:
            try:
                results = process_model_task(task)
                print(f"Completed all configurations for model: {task['model_name']}")
            except Exception as e:
                print(f"Error processing model {task['model_name']}: {e}")
    
    # Summarize generation results
    all_output_files = progress_tracker.get_all_output_files()
    print(f"Generated {len(all_output_files)} patch files in total")
    
    return all_output_files

def parse_config_from_filename(output_file: str) -> Dict[str, Any]:
    """
    Parse configuration information from output filename
    
    Args:
        output_file: Output file path
        
    Returns:
        Parsed configuration information
    """
    # Filename format: timestamp__input_basename__model_name__temperature.jsonl
    try:
        filename = os.path.basename(output_file)
        # Remove extension
        filename_no_ext = os.path.splitext(filename)[0]
        # Split by __
        parts = filename_no_ext.split('__')
        if len(parts) >= 4:
            # Extract temperature value
            temp = float(parts[3])
            # Extract model name
            model_name = parts[2]
            # Extract input filename
            input_basename = parts[1]
            return {
                "temperature": temp,
                "model_name": model_name,
                "input_basename": input_basename
            }
    except Exception as e:
        print(f"Error parsing config from filename {output_file}: {e}")
    return {}

def find_matching_output_file(output_files: List[str], model_name: str, 
                              input_basename: str, temperature: float) -> Optional[str]:
    """
    Find output file matching specific configuration
    
    Args:
        output_files: List of output files
        model_name: Model name
        input_basename: Input file base name
        temperature: Temperature value
        
    Returns:
        Matching file path, or None if not found
    """
    for file_path in output_files:
        config = parse_config_from_filename(file_path)
        if (config.get("model_name") == model_name and 
            config.get("input_basename") == input_basename and 
            config.get("temperature") == temperature):
            return file_path
    return None

def process_model_task(model_task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process all configuration tasks for a single model (sequentially)
    
    Args:
        model_task: Model task information
        
    Returns:
        Processing results
    """
    model_name = model_task["model_name"]
    configs = model_task["configs"]
    input_file = model_task["input_file"]
    output_dir = model_task["output_dir"]
    progress_file = model_task["progress_file"]
    
    # Create an independent progress_tracker instance in each process
    progress_tracker = ProgressTracker(progress_file)
    status = progress_tracker.get_model_status(model_name)
    
    print(f"Processing model: {model_name} with {len(configs)} configurations")
    
    results = {
        "completed": False,
        "last_completed_config": -1,
        "output_files": status.get("output_files", [])
    }
    
    # Restore completed configurations
    if status.get("completed", False):
        print(f"Model {model_name} already completed, skipping")
        return status
    
    # Restore partially completed progress
    last_completed = status.get("last_completed_config", -1)
    output_files = results["output_files"]
    
    if last_completed >= 0:
        print(f"Resuming from configuration {last_completed + 1} for model {model_name}")
        results["last_completed_config"] = last_completed
    
    # Get the base name of the input file (without extension)
    input_basename = os.path.basename(input_file).split('.')[0]
    
    # Process each configuration
    for config_idx, config in enumerate(configs):
        if config_idx <= last_completed:
            print(f"Skipping already completed config {config_idx} for model {model_name}")
            continue
        
        temp = config["temperature"]
        n_resp = config["n_responses"]
        inference_max_workers = config["max_workers"]

        # Check if there's already an output file with the same configuration
        matching_file = find_matching_output_file(output_files, model_name, input_basename, temp)
        
        if matching_file:
            print(f"Found existing output file for model {model_name}, temp={temp}: {matching_file}")
            output_file = matching_file
        else:
            # Generate new output filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"{output_dir}/{timestamp}__{input_basename}__{model_name}__{temp}.jsonl"
            # Add to output file list
            output_files.append(output_file)
            # Update status in advance
            results["last_completed_config"] = config_idx - 1
            progress_tracker.update_model_status(model_name, results)
            print(f"Pre-registering output file: {output_file}")
        
        print(f"Running configuration for model {model_name}: temperature={temp}, n_responses={n_resp}")
        
        # Build run_inference.py command
        cmd = [
            "python", "-m", "src.apebench.inference.run_inference",
            "--pipeline", "patch",
            "--input_file", input_file,
            "--output_file", output_file,  # Use determined output file path
            "--model_name", model_name,
            "--temperature", str(temp),
            "--n_responses", str(n_resp),
            "--max_workers", str(inference_max_workers)
        ]
        
        # Add optional parameters
        if "force_complete_prompt" in config and config["force_complete_prompt"]:
            cmd.append("--force_complete_prompt")
        
        if "force_reasoning_prompt" in config and config["force_reasoning_prompt"]:
            cmd.append("--force_reasoning_prompt")

        if "max_tokens" in config and config["max_tokens"]:
            cmd.append("--max_tokens")
            cmd.append(str(config["max_tokens"]))
        
        if "thinking_budget_tokens" in config and config["thinking_budget_tokens"]:
            cmd.append("--thinking_budget_tokens")
            cmd.append(str(config["thinking_budget_tokens"]))
        
        # Execute command
        try:
            print(f"Executing: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
            
            # Update results
            if output_file not in results["output_files"]:
                results["output_files"].append(output_file)
            results["last_completed_config"] = config_idx
            
            # Update progress status in real-time
            progress_tracker.update_model_status(model_name, results)
            
            print(f"Successfully completed configuration {config_idx} for model {model_name}")
            
        except subprocess.CalledProcessError as e:
            print(f"Error executing command for model {model_name}, config {config_idx}: {e}")
            # Still update progress with last successful configuration
            progress_tracker.update_model_status(model_name, results)
    
    # Set completed flag when all configurations are processed
    results["completed"] = True
    progress_tracker.update_model_status(model_name, results)
    
    print(f"Completed all {len(configs)} configurations for model {model_name}")
    return results