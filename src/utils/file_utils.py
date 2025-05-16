# Copyright (2025) Bytedance Ltd. and/or its affiliates.

import os
import glob
import json
import pandas as pd
from tqdm import tqdm
import numpy as np

def convert_to_serializable(obj):
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    elif isinstance(obj, (set, frozenset)):
        return list(obj)
    elif isinstance(obj, dict):
        return {key: convert_to_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_to_serializable(item) for item in obj]
    elif hasattr(obj, 'isoformat'):
        return obj.isoformat()
    elif isinstance(obj, np.ndarray):
        return [convert_to_serializable(item) for item in obj]
    else:
        try:
            return str(obj)
        except:
            return None

def load_results(file_paths):
    """
    Load results from files matching the pattern.
    
    Args:
        file_paths (str): Directory containing result files
        file_pattern (str): Pattern to match result files
    
    Returns:
        pd.DataFrame: Combined DataFrame from all matching files
    """
    if isinstance(file_paths, list):
        file_paths = [file_path for file_path_pattern in file_paths for file_path in glob.glob(file_path_pattern)]
    if isinstance(file_paths, str):
        file_paths = glob.glob(file_paths)
    
    if not file_paths:
        print(f"Warning: No files found matching {file_paths}")
        return pd.DataFrame()
    
    print(f"Found {len(file_paths)} files matching {file_paths}")
    
    all_data = []
    for file_path in tqdm(file_paths, desc="Loading files"):
        try:
            if file_path.endswith('.parquet'):
                df = pd.read_parquet(file_path)
            elif file_path.endswith('.jsonl') or file_path.endswith('.json'):
                # Read JSONL files
                records = load_jsonl(file_path)
                df = pd.DataFrame(records)
            else:
                print(f"Warning: Unsupported file format for {file_path}")
                continue
                
            all_data.append(df)
        except Exception as e:
            print(f"Error loading {file_path}: {str(e)}")
    
    if not all_data:
        print(f"Warning: Could not load any data from files matching {file_path}")
        return pd.DataFrame()
    
    combined_data = pd.concat(all_data, ignore_index=True)
    print(f"Loaded {len(combined_data)} entries from {len(all_data)} files")
    
    return combined_data

def load_jsonl(input_path):
    with open(input_path, 'r') as f:
        data = [json.loads(line.strip()) for line in f]
    return data

def save_jsonl(data, output_path):
    with open(output_path, 'w') as f:
        if isinstance(data, pd.DataFrame):
            for _, row in data.iterrows():
                f.write(json.dumps(row.to_dict(), ensure_ascii=False) + '\n')
        else:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
