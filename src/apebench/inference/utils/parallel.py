# Copyright (2025) Bytedance Ltd. and/or its affiliates.

import pandas as pd
import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
import os
import random
import time

def process_rows_parallel(data: pd.DataFrame, 
                        process_func: callable, 
                        output_file: str,
                        max_workers: int = 2,
                        config_info: dict = None):
    """Process rows in parallel using ThreadPoolExecutor.
    
    Args:
        data: DataFrame containing rows to process
        process_func: Function to process each row
        output_file: Path to output JSON file
        max_workers: Number of parallel workers
        config_info: Dictionary containing configuration information for logging
        
    Returns:
        Tuple of (processed_count, error_count)
    """
    processed_count = 0
    error_count = 0
    total_items = len(data)
    start_time = time.time()
    
    # Prepare configuration information display
    config_str = ""
    if config_info:
        config_items = []
        if 'model_name' in config_info:
            config_items.append(f"Model: {config_info['model_name']}")
        if 'temperature' in config_info:
            config_items.append(f"Temp: {config_info['temperature']}")
        if 'n_responses' in config_info:
            config_items.append(f"Responses: {config_info['n_responses']}")
        config_str = " | ".join(config_items)
        if config_str:
            config_str = f"[{config_str}] "
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_func, row) : i for i, row in data.iterrows()}
        for future in as_completed(futures):
            try:
                result = future.result()
                if result is not None:
                    result_json = json.dumps(result, ensure_ascii=False)
                    with open(output_file, 'a') as f:
                        f.write(result_json + '\n')
                    processed_count += 1
                else:
                    error_count += 1
            except TimeoutError:
                error_count += 1
                logging.error(f"{config_str}Timeout occurred while processing row")
            except Exception as e:
                error_count += 1
                logging.error(f"{config_str}Unexpected error while processing result: {str(e)}")
            finally:
                current_item = processed_count + error_count
                current_time = time.time()
                elapsed_time = current_time - start_time
                progress_percent = (current_item / total_items) * 100
                
                # Calculate estimated remaining time
                if current_item > 0 and progress_percent < 100:
                    time_per_item = elapsed_time / current_item
                    remaining_items = total_items - current_item
                    estimated_remaining_time = time_per_item * remaining_items
                    
                    print(
                        f"{config_str}Progress: {progress_percent:.2f}% ({current_item}/{total_items}) | "
                        f"Completed: {processed_count} | Errors: {error_count} | "
                        f"Elapsed time: {elapsed_time / 3600:.2f} hours | "
                        f"Est. remaining: {estimated_remaining_time / 3600:.2f} hours"
                    )
                else:
                    print(
                        f"{config_str}Progress: {progress_percent:.2f}% ({current_item}/{total_items}) | "
                        f"Completed: {processed_count} | Errors: {error_count} | "
                        f"Elapsed time: {elapsed_time / 3600:.2f} hours"
                    )
    
    return processed_count, error_count

def check_missing_rows(data: pd.DataFrame, output_file: str):
    """Check which rows from the original data are missing in the output file.
    
    Args:
        data: Original DataFrame with row indices
        output_file: Path to the output JSON file
        
    Returns:
        List of missing row indices
    """
    processed_indices = set()
    
    if os.path.exists(output_file):
        with open(output_file, 'r') as f:
            for line in f:
                try:
                    result = json.loads(line)
                    if 'local_index' in result:
                        processed_indices.add(result['local_index'])
                except json.JSONDecodeError:
                    logging.error(f"Error decoding JSON line: {line}")
    
    all_indices = set(data.index.tolist())
    missing_indices = list(all_indices - processed_indices)
    
    return missing_indices

def process_with_retries(data: pd.DataFrame,
                        process_func: callable,
                        output_file: str,
                        max_workers: int = 2,
                        max_retries: int = 3,
                        config_info: dict = None):
    """Process rows with automatic retries for failed rows.
    
    Args:
        data: DataFrame containing rows to process
        process_func: Function to process each row
        output_file: Path to output JSON file
        max_workers: Number of parallel workers
        max_retries: Maximum number of retry attempts for each batch of failures
        config_info: Dictionary containing configuration information for logging
        
    Returns:
        Tuple of (total_processed_count, total_error_count, final_missing_indices)
    """
    total_processed = 0
    total_errors = 0
    retry_count = 0
    
    # Initial processing
    logging.info("Starting initial processing...")
    
    # Retry loop
    missing_indices = check_missing_rows(data, output_file)
    random.shuffle(missing_indices)

    config_str = ""
    if config_info:
        config_items = []
        if 'model_name' in config_info:
            config_items.append(f"Model: {config_info['model_name']}")
        if 'temperature' in config_info:
            config_items.append(f"Temp: {config_info['temperature']}")
        if 'n_responses' in config_info:
            config_items.append(f"Responses: {config_info['n_responses']}")
        config_str = " | ".join(config_items)
        if config_str:
            config_str = f"[{config_str}] "
    
    while missing_indices and retry_count < max_retries:
        retry_count += 1
                
        print(f"{config_str}Retry attempt {retry_count}: Found {len(missing_indices)} missing rows")
        
        retry_data = data.loc[missing_indices]
        retry_processed, retry_errors = process_rows_parallel(
            retry_data, process_func, output_file, max_workers, config_info=config_info
        )
        
        total_processed += retry_processed
        total_errors += retry_errors
        
        missing_indices = check_missing_rows(data, output_file)
        if not missing_indices:
            print(f"{config_str}All rows successfully processed")
            break
            
        if retry_count == max_retries:
            print(f"{config_str}Reached maximum retry attempts ({max_retries})")
    
    return total_processed, total_errors, missing_indices

