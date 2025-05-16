# Copyright (2025) Bytedance Ltd. and/or its affiliates.

import os
import json
from datetime import datetime
import logging
from typing import Dict, Any, Optional
import fcntl
import threading
from filelock import FileLock
import uuid

class ChatLogger:
    def __init__(self, log_dir: str = "chat_logs"):
        """
        Initialize the ChatLogger.
        
        Args:
            log_dir (str): Directory where log files will be stored
        """
        self.log_dir = log_dir
        self._setup_logging()
        self._lock = threading.Lock()
        
    def _setup_logging(self):
        """Set up the logging directory and basic configuration."""
        # Create log directory if it doesn't exist
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Set up basic logging with thread safety
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
    def _get_log_filename(self) -> str:
        """Generate a filename for the current day's log."""
        current_date = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self.log_dir, f"chat_log_{current_date}.jsonl")
        
    def log_chat(self, 
                 prompt: str, 
                 completion: Dict[str, Any], 
                 model_name: str,
                 system_prompt: Optional[str] = None) -> None:
        """
        Log a chat interaction to a JSONL file in a thread-safe manner.
        
        Args:
            prompt (str): The user prompt
            completion (Dict): The completion response
            model_name (str): Name of the model used
            system_prompt (Optional[str]): System prompt if used
        """
        log_entry = {
            "id": str(uuid.uuid4()),  # Add unique identifier for each log entry
            "timestamp": datetime.now().isoformat(),
            "model_name": model_name,
            "system_prompt": system_prompt,
            "prompt": prompt,
            "completion": completion,
            "thread_id": threading.get_ident()
        }
        
        log_file = self._get_log_filename()
        lock_file = f"{log_file}.lock"
        
        # Use FileLock for cross-process locking
        with FileLock(lock_file):
            try:
                with open(log_file, "a", encoding="utf-8") as f:
                    # Use fcntl for file-level locking (UNIX systems only)
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                    try:
                        json.dump(log_entry, f, ensure_ascii=False)
                        f.write("\n")
                        f.flush()  # Ensure the write is committed to disk
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                self.logger.info(f"Successfully logged chat interaction (ID: {log_entry['id']}) to {log_file}")
            except Exception as e:
                self.logger.error(f"Failed to log chat interaction: {str(e)}")
            
    def get_chat_history(self, 
                        date_str: Optional[str] = None,
                        thread_id: Optional[int] = None) -> list:
        """
        Retrieve chat history for a specific date or current date if not specified.
        
        Args:
            date_str (Optional[str]): Date in format 'YYYY-MM-DD'
            thread_id (Optional[int]): Filter logs by specific thread ID
            
        Returns:
            list: List of chat interactions for the specified date
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
            
        log_file = os.path.join(self.log_dir, f"chat_log_{date_str}.jsonl")
        lock_file = f"{log_file}.lock"
        
        if not os.path.exists(log_file):
            return []
            
        try:
            with FileLock(lock_file):
                with open(log_file, "r", encoding="utf-8") as f:
                    # Use fcntl for file-level locking
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                    try:
                        logs = [json.loads(line) for line in f]
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        
            # Filter by thread_id if specified
            if thread_id is not None:
                logs = [log for log in logs if log.get("thread_id") == thread_id]
                
            return logs
        except Exception as e:
            self.logger.error(f"Failed to read chat history: {str(e)}")
            return [] 