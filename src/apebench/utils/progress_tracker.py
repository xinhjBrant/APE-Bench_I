# Copyright (2025) Bytedance Ltd. and/or its affiliates.

"""
Progress tracking manager, used to record and manage the execution progress of the evaluation process
"""

import os
import json
import fcntl
from datetime import datetime
from typing import Dict, Any, List, Optional

class ProgressTracker:
    """Track and manage evaluation process progress"""
    
    def __init__(self, progress_file: str):
        """
        Initialize progress tracker
        
        Args:
            progress_file: Path to progress data file
        """
        self.progress_file = progress_file
        self.data = self._load_progress()
    
    def _load_progress(self) -> Dict[str, Any]:
        """Load progress data, using file locks to ensure multi-process safety"""
        os.makedirs(os.path.dirname(self.progress_file), exist_ok=True)
        
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r') as f:
                    # Get shared lock (read lock)
                    fcntl.flock(f, fcntl.LOCK_SH)
                    try:
                        data = json.load(f)
                    finally:
                        # Release lock
                        fcntl.flock(f, fcntl.LOCK_UN)
                    return data
            except Exception as e:
                print(f"Error loading progress file: {e}")
                # If loading fails, backup old file and create new one
                backup_file = f"{self.progress_file}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
                os.rename(self.progress_file, backup_file)
                print(f"Backed up problematic progress file to {backup_file}")
        
        # Initialize empty progress data
        return {
            "models": {},
            "verification": {"completed": False},
            "evaluation": {"completed": False},
            "last_updated": None
        }
    
    def _save_progress(self, limited_update_keys: Optional[List[str]] = None) -> None:
        """Save progress data, using lock files to ensure multi-process safety"""
        self.data["last_updated"] = datetime.now().isoformat()
        os.makedirs(os.path.dirname(self.progress_file), exist_ok=True)
        
        # Create lock file path
        lock_file = f"{self.progress_file}.lock"
        
        try:
            # Open or create lock file
            with open(lock_file, 'w') as lock_f:
                # Get exclusive lock (write lock)
                fcntl.flock(lock_f, fcntl.LOCK_EX)
                try:
                    # Read current data (if exists)
                    current_data = self.data
                    if os.path.exists(self.progress_file) and os.path.getsize(self.progress_file) > 0:
                        try:
                            with open(self.progress_file, 'r') as f:
                                current_data = json.load(f)
                                # Merge model data, preserve other parts unchanged
                                current_data.update({k : v for k, v in self.data.items() if limited_update_keys is None or k in limited_update_keys})
                                current_data["last_updated"] = self.data["last_updated"]
                        except (json.JSONDecodeError, ValueError):
                            # If file is empty or format is wrong, use current data
                            current_data = self.data
                    
                    # Update data in memory
                    self.data = current_data
                    
                    # Write directly to original file
                    with open(self.progress_file, 'w') as f:
                        json.dump(self.data, f, indent=2)
                finally:
                    # Release lock
                    fcntl.flock(lock_f, fcntl.LOCK_UN)
        except Exception as e:
            print(f"Error saving progress file: {e}")
    
    def get_model_status(self, model_name: str) -> Dict[str, Any]:
        """
        Get status of a specific model, forcibly reload latest data before getting
        
        Args:
            model_name: Model name
            
        Returns:
            Dictionary containing model status
        """
        # Reload to get latest status
        self.data = self._load_progress()
        
        if model_name not in self.data["models"]:
            self.data["models"][model_name] = {
                "completed": False,
                "last_completed_config": -1,
                "output_files": []
            }
        return self.data["models"][model_name]
    
    def update_model_status(self, model_name: str, status: Dict[str, Any]) -> None:
        """
        Update model status
        
        Args:
            model_name: Model name
            status: New status dictionary
        """
        self.data["models"][model_name] = status
        self._save_progress()
    
    def get_verification_status(self) -> Dict[str, Any]:
        """
        Get verification phase status
        
        Returns:
            Verification status dictionary
        """
        # Reload to get latest status
        self.data = self._load_progress()
        return self.data["verification"]
    
    def update_verification_status(self, status: Dict[str, Any]) -> None:
        """
        Update verification phase status
        
        Args:
            status: New verification status dictionary
        """
        self.data["verification"] = status
        self._save_progress()
    
    def get_evaluation_status(self) -> Dict[str, Any]:
        """
        Get evaluation phase status
        
        Returns:
            Evaluation status dictionary
        """
        # Reload to get latest status
        self.data = self._load_progress()
        return self.data["evaluation"]
    
    def update_evaluation_status(self, status: Dict[str, Any]) -> None:
        """
        Update evaluation phase status
        
        Args:
            status: New evaluation status dictionary
        """
        self.data["evaluation"] = status
        self._save_progress()
    
    def get_all_output_files(self) -> List[str]:
        """
        Get output files for all completed models
        
        Returns:
            List of output file paths
        """
        # Reload to get latest status
        self.data = self._load_progress()
        
        all_files = []
        for model_name, model_status in self.data["models"].items():
            if model_status.get("completed", False):
                all_files.extend(model_status.get("output_files", []))
        return all_files
    
    def reset_progress(self, section: Optional[str] = None) -> None:
        """
        Reset progress data
        
        Args:
            section: Section to reset, such as 'models', 'verification', 'evaluation',
                     if None, reset all data
        """
        if section is None:
            self.data = {
                "models": {},
                "verification": {"completed": False},
                "evaluation": {"completed": False},
                "last_updated": None
            }
        elif section == 'models':
            self.data["models"] = {}
        elif section in self.data:
            self.data[section] = {"completed": False}
        
        self._save_progress()