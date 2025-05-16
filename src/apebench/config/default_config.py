# Copyright (2025) Bytedance Ltd. and/or its affiliates.
"""
Default configuration definition module
"""

DEFAULT_CONFIG = {
    # Global settings
    "project_dir": "./",
    "output_dir": "./outputs",
    "temp_dir": "./temp",
    "progress_log": "./logs/progress.json",
    
    # Data settings
    "input_file": "./datasets/ape_bench1_valid_test.parquet",
    
    # Data collection configuration
    "data_collection": {
        "dataset_dir": "datasets",
        "repo_url": "https://github.com/leanprover-community/mathlib4.git",
        "repo_path": "mathlib4",
        "max_diff_lines": 100,
        "latest_num_data": 2000,
        "instruction_model": "aws_sdk_claude37_sonnet@thinking",
        "judgement_model": "aws_sdk_claude37_sonnet@thinking",
        "max_workers": 8,
        "max_tokens": 20000,
        "thinking_budget_tokens": 16000
    },
    
    # Patch generation configuration
    "generation": {
        "base_output_dir": "./outputs/patch",
        "parallel_models": True,     # Different models executed in parallel
        "parallel_configs": False,   # Same model with different configs executed serially
        "max_model_workers": 4,      # Number of models to execute in parallel
        "models": [
            {
                "name": "deepseek-v3-250324",
                "configs": [
                    {"temperature": 0.0, "n_responses": 1, "max_workers": 48},
                    {"temperature": 0.6, "n_responses": 20, "max_workers": 48}
                ]
            }
        ]
    },
    
    # Verification configuration
    "verification": {
        "eleanstic_config": "./src/eleanstic/config.yaml",
        "max_workers": 128,
        "results_dir": "./verify_results"
    },
    
    # Judgment generation configuration
    "judgement": {
        "model_name": "aws_sdk_claude37_sonnet@thinking",
        "temperature": 0.0,
        "n_responses": 1,
        "max_workers": 8
    },
    
    # Evaluation configuration
    "evaluation": {
        "k_ratio": 0.8,
        "generate_plots": True,
        "plots_dir": "./plots"
    }
}