# Copyright (2025) Bytedance Ltd. and/or its affiliates.

"""
Commit Status Management Module

Implements commit status storage through the file system, each commit's status is saved in a separate file.
"""

import os
import json
from datetime import datetime
import traceback

STATUS_PENDING = 'pending'
STATUS_BUILDING = 'building'
STATUS_COLLAPSED = 'collapsed'
STATUS_READY = 'ready'
STATUS_FAILED = 'failed'
STATUS_FAILED_VERIFY = 'failed_verify'

class CommitStatus:
    """
    Commit Status Management Class, implemented using the file system
    
    Each commit's status is saved in a separate file.
    Supports the following statuses:
    - 'pending': Waiting to start build
    - 'building': Currently building
    - 'ready': Build successful, not compressed
    - 'collapsed': Build successful, compressed
    - 'failed': Build failed
    - 'failed_verify': Built but verification failed
    """
    
    def __init__(self, status_dir: str = "commit_status"):
        """
        Initialize CommitStatus instance
        
        Args:
            status_dir: Directory to save status files
        """
        self.status_dir = status_dir
        os.makedirs(self.status_dir, exist_ok=True)
    
    def _get_status_file(self, commit_id: str) -> str:
        """Get status file path for specified commit"""
        return os.path.join(self.status_dir, f"{commit_id}.json")
    
    def is_commit_processed(self, commit_id: str) -> bool:
        """
        Determine if a commit has been successfully built
        
        Args:
            commit_id: Git commit ID
            
        Returns:
            bool: Returns True if status is 'ready' or 'collapsed', otherwise False
        """
        status_file = self._get_status_file(commit_id)
        if not os.path.exists(status_file):
            return False
        
        try:
            with open(status_file, 'r') as f:
                status_data = json.load(f)
                return status_data.get('status') in [STATUS_READY, STATUS_COLLAPSED]
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error reading commit status file ({commit_id}): {e}")
            return False
    
    def get_commit_status(self, commit_id: str):
        """
        Get complete status information for a commit
        
        Args:
            commit_id: Git commit ID
            
        Returns:
            Dict: Dictionary containing status, message and timestamp; if not exists returns default dictionary with 'pending' status
        """
        status_file = self._get_status_file(commit_id)
        if not os.path.exists(status_file):
            return {
                'commit_id': commit_id,
                'status': STATUS_PENDING,
                'message': None,
                'updated_at': datetime.now().isoformat()
            }
        
        try:
            with open(status_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error reading commit status file ({commit_id}): {e}")
            return {
                'commit_id': commit_id,
                'status': STATUS_PENDING,
                'message': f"Status file read error: {traceback.format_exc()}",
                'updated_at': datetime.now().isoformat()
            }
    
    def update_commit_status(self, commit_id: str, status: str, message = None, additional_data = None) -> bool:
        """
        Update commit status, preserving previous status data
        
        Args:
            commit_id: Git commit ID
            status: New status ('pending', 'building', 'ready', 'collapsed', or 'failed')
            message: Optional status message
            additional_data: Optional dictionary with additional data to update
            
        Returns:
            bool: Returns True on successful update, False on failure
        """
        # Get existing status data if available
        existing_data = self.get_commit_status(commit_id)
        
        # Update with new values
        existing_data['status'] = status
        if message is not None:
            existing_data['message'] = message
        existing_data['updated_at'] = datetime.now().isoformat()
        
        # Merge additional data if provided
        if additional_data:
            for key, value in additional_data.items():
                existing_data[key] = value
        
        status_file = self._get_status_file(commit_id)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(status_file), exist_ok=True)
        
        try:
            with open(status_file, 'w') as f:
                json.dump(existing_data, f, indent=2, ensure_ascii=False)
            return True
        except IOError as e:
            print(f"Failed to update commit status file ({commit_id}): {e}")
            return False
    
    def get_all_commits_status(self):
        """
        Get status information for all commits
        
        Returns:
            List[Dict]: List of commit status information
        """
        result = []
        try:
            for filename in os.listdir(self.status_dir):
                if filename.endswith('.json'):
                    commit_id = filename[:-5]  # Remove .json suffix
                    status = self.get_commit_status(commit_id)
                    result.append(status)
            return result
        except OSError as e:
            print(f"Failed to read status directory: {e}")
            return []
    
    def get_commits_by_status(self, status: str):
        """
        Get all commits with a specified status
        
        Args:
            status: Status to filter by
            
        Returns:
            List[Dict]: List of commit status information matching the status
        """
        all_statuses = self.get_all_commits_status()
        return [item for item in all_statuses if item.get('status') == status]