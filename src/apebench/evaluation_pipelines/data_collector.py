# Copyright (2025) Bytedance Ltd. and/or its affiliates.
"""
Data Collection Management Module, responsible for executing the dataset creation workflow
"""

import os
import subprocess
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def collect_data(config_file: str) -> Dict[str, Any]:
    """
    Run data collection tasks according to configuration
    
    Args:
        config_file: Configuration file path
        
    Returns:
        Key file path information generated during the collection process
    """
    # Import here instead of at the top to avoid circular imports
    from ..config.config_manager import ConfigManager
    
    # Load configuration
    config_manager = ConfigManager(config_file)
    config = config_manager.get_config()
    
    # Use data_collection section of the configuration
    data_config = config.data_collection
    
    # Create output directory
    os.makedirs(data_config.dataset_dir, exist_ok=True)
    
    # Get data collection timestamp
    data_collection_date = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Set key path variables
    repo_path = data_config.repo_path
    repo_name = os.path.basename(repo_path)
    max_diff_lines = data_config.max_diff_lines
    
    # Build base filename
    base_filename = f"{repo_name}_commits_data_{data_collection_date}_{max_diff_lines}"
    
    # Record all generated files
    output_files = {}
    
    # Step 1: Clone repository
    if not os.path.exists(repo_path):
        logger.info(f"Cloning {data_config.repo_url} to {repo_path}")
        subprocess.run(["git", "clone", data_config.repo_url, repo_path], check=True)
    else:
        logger.info(f"Repository {repo_path} already exists, skipping clone")
    
    # Step 2: Collect commit data
    raw_data_path = os.path.join(data_config.dataset_dir, f"{base_filename}.parquet")
    logger.info(f"Collecting commit data to {raw_data_path}")
    
    collect_cmd = [
        "python", "src/apebench/data/collect_commit_data.py",
        "--repo_path", repo_path,
        "--output_path", raw_data_path,
        "--max_diff_lines", str(max_diff_lines)
    ]
    subprocess.run(collect_cmd, check=True)
    output_files["raw_data"] = raw_data_path
    
    # Step 3: Filter commit data
    filtered_data_path = os.path.join(data_config.dataset_dir, f"filtered_{base_filename}.parquet")
    length_plot_path = os.path.join(data_config.dataset_dir, f"filtered_{base_filename}_filtered_length_distribution.png")
    
    logger.info(f"Filtering data to {filtered_data_path}")
    filter_cmd = [
        "python", "src/apebench/data/filter_commit_data.py",
        "--file_path", raw_data_path,
        "--output_path", filtered_data_path,
        "--length_distribution_plot_path", length_plot_path
    ]
    subprocess.run(filter_cmd, check=True)
    output_files["filtered_data"] = filtered_data_path
    output_files["length_plot"] = length_plot_path
    
    # Step 4: Build database
    logger.info("Building database")
    build_cmd = [
        "python", "-m", "src.eleanstic.main",
        "--input_file", filtered_data_path,
        "build"
    ]
    subprocess.run(build_cmd, check=True)
    
    # Step 5: Verify filtered data
    verify_result_dir = os.path.join(data_config.dataset_dir, "verify_results", f"filtered_{base_filename}")
    os.makedirs(os.path.dirname(verify_result_dir), exist_ok=True)
    
    logger.info(f"Verifying filtered data, saving results to {verify_result_dir}")
    verify_cmd = [
        "python", "-m", "src.eleanstic.main",
        "--input_file", filtered_data_path,
        "verify",
        "--code_key", "content_after",
        "--results_dir", verify_result_dir
    ]
    subprocess.run(verify_cmd, check=True)
    output_files["verify_results"] = verify_result_dir
    
    # Step 6: Filter verification data
    verified_data_path = os.path.join(data_config.dataset_dir, f"filtered_{base_filename}_verified.parquet")
    
    logger.info(f"Filtering verification data to {verified_data_path}")
    filter_results_cmd = [
        "python", "src/apebench/data/filter_results.py",
        "--pipeline", "verification",
        "--input_files", f"{verify_result_dir}/*.jsonl",
        "--output_file", verified_data_path,
        "--reset_index_by_date"
    ]
    subprocess.run(filter_results_cmd, check=True)
    output_files["verified_data"] = verified_data_path
    
    # Step 7: Extract latest data
    latest_num_data = data_config.latest_num_data
    latest_data_path = os.path.join(data_config.dataset_dir, f"filtered_{base_filename}_verified_latest_{latest_num_data}.jsonl")
    
    logger.info(f"Extracting latest {latest_num_data} records to {latest_data_path}")
    # Use pandas to read and save data, instead of executing Python commands
    df = pd.read_parquet(verified_data_path)
    df.sort_values(by='date', ascending=False, inplace=True)
    df = df.head(latest_num_data)
    df.to_json(latest_data_path, orient='records', lines=True)
    output_files["latest_data"] = latest_data_path
    
    # Ensure output directories exist
    os.makedirs(config.output_dir, exist_ok=True)
    os.makedirs(os.path.join(config.output_dir, "instruction"), exist_ok=True)
    os.makedirs(os.path.join(config.output_dir, "judgement"), exist_ok=True)
    
    # Step 8: Generate instruction data
    instruction_model_name = data_config.instruction_model
    instruction_output_path = os.path.join(
        config.output_dir, 
        "instruction", 
        f"filtered_{base_filename}_verified_latest_{latest_num_data}_instruction_{instruction_model_name}.jsonl"
    )
    
    logger.info(f"Generating instruction data to {instruction_output_path}")
    instruction_cmd = [
        "python", "src/apebench/inference/run_inference.py",
        "--pipeline", "instruction",
        "--input_file", latest_data_path,
        "--output_file", instruction_output_path,
        "--model_name", instruction_model_name,
        "--max_workers", str(data_config.max_workers),
        "--n_responses", "1",
        "--temperature", "0",
        "--max_tokens", str(data_config.max_tokens),
        "--thinking_budget_tokens", str(data_config.thinking_budget_tokens)
    ]
    subprocess.run(instruction_cmd, check=True)
    output_files["instruction_output"] = instruction_output_path
    
    # Create instruction data directory
    os.makedirs(os.path.join(data_config.dataset_dir, "instruction"), exist_ok=True)
    
    instruction_data_path = os.path.join(
        data_config.dataset_dir,
        "instruction",
        f"filtered_{base_filename}_verified_latest_{latest_num_data}_instruction_{instruction_model_name}.jsonl"
    )
    
    logger.info(f"Filtering instruction data to {instruction_data_path}")
    filter_instruction_cmd = [
        "python", "src/apebench/data/filter_results.py",
        "--pipeline", "instruction",
        "--input_files", instruction_output_path,
        "--output_file", instruction_data_path,
        "--extract_exercise_info"
    ]
    subprocess.run(filter_instruction_cmd, check=True)
    output_files["instruction_data"] = instruction_data_path
    
    # Step 9: Verify through judgement of golden differences
    judgement_model_name = data_config.judgement_model
    judgement_output_path = os.path.join(
        config.output_dir,
        "judgement",
        f"filtered_{base_filename}_verified_latest_{latest_num_data}_judgement_{judgement_model_name}.jsonl"
    )
    
    logger.info(f"Executing judgement verification to {judgement_output_path}")
    judgement_cmd = [
        "python", "src/apebench/inference/run_inference.py",
        "--pipeline", "judgement",
        "--input_file", instruction_data_path,
        "--output_file", judgement_output_path,
        "--model_name", judgement_model_name,
        "--max_workers", str(data_config.max_workers),
        "--n_responses", "1",
        "--temperature", "0",
        "--max_tokens", str(data_config.max_tokens),
        "--thinking_budget_tokens", str(data_config.thinking_budget_tokens),
        "--patch_key", "gold_diff"
    ]
    subprocess.run(judgement_cmd, check=True)
    output_files["judgement_output"] = judgement_output_path
    
    # Create judgement data directory
    os.makedirs(os.path.join(data_config.dataset_dir, "judgement"), exist_ok=True)
    
    judgement_data_path = os.path.join(
        data_config.dataset_dir,
        "judgement",
        f"filtered_{base_filename}_verified_latest_{latest_num_data}_judgement_{judgement_model_name}.jsonl"
    )
    
    logger.info(f"Filtering judgement data to {judgement_data_path}")
    filter_judgement_cmd = [
        "python", "src/apebench/data/filter_results.py",
        "--pipeline", "judgement",
        "--input_files", judgement_output_path,
        "--output_file", judgement_data_path
    ]
    subprocess.run(filter_judgement_cmd, check=True)
    output_files["judgement_data"] = judgement_data_path
    
    logger.info(f"Data collection complete! Final data path: {judgement_data_path}")
    
    return output_files 