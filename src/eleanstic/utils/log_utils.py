# Copyright (2025) Bytedance Ltd. and/or its affiliates.

"""
Log utilities module
Supports colored log output and log file rotation
"""
import os
import logging
import logging.handlers
from pathlib import Path
from typing import Optional, Dict, Any
import colorlog

def setup_logger(
    name: str = "commit_database",
    level: str = "INFO",
    log_dir: Optional[str] = None,
    log_file: Optional[str] = None,
    max_size_mb: int = 100,
    backup_count: int = 10,
    console_output: bool = True,
    color_output: bool = True
) -> logging.Logger:
    """
    Set up logging system
    
    Args:
        name: Logger name
        level: Log level
        log_dir: Log directory
        log_file: Log file
        max_size_mb: Maximum log file size (MB)
        backup_count: Number of log files to keep
        console_output: Whether to output to console
        color_output: Whether to use colored logs
        
    Returns:
        logging.Logger: Configured logger
    """
    # Convert log level
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }
    log_level = level_map.get(level.upper(), logging.INFO)
    
    # Create complete log file path
    full_log_path = None
    if log_dir and not log_file:
        log_path = Path(log_dir)
        if not log_path.exists():
            log_path.mkdir(parents=True, exist_ok=True)
        full_log_path = str(log_path / f"{name}.log")
    elif log_file:
        full_log_path = log_file
    # if full_log_path:
    #     console_output = False
    
    # Create logger with "name:log_file" as unique identifier
    # This way even if name is the same but log_file is different, different logger instances will be created
    logger_id = name if full_log_path is None else f"{name}:{full_log_path}"
    logger = logging.getLogger(logger_id)
    logger.setLevel(log_level)
    
    # Clear old handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Define log format - Use custom Formatter to keep simple name display
    class SimpleNameFormatter(logging.Formatter):
        def format(self, record):
            # Temporarily save original name
            original_name = record.name
            # Set to simple name (remove log_file path)
            if ':' in original_name:
                record.name = original_name.split(':', 1)[0]
            result = super().format(record)
            # Restore original name
            record.name = original_name
            return result
    
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Add console output
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        
        if color_output:
            # Colored logs
            colors = {
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
            color_formatter = colorlog.ColoredFormatter(
                "%(log_color)s" + log_format,
                log_colors=colors
            )
            # Replace with custom Formatter
            class SimpleNameColorFormatter(colorlog.ColoredFormatter):
                def format(self, record):
                    # Temporarily save original name
                    original_name = record.name
                    # Set to simple name (remove log_file path)
                    if ':' in original_name:
                        record.name = original_name.split(':', 1)[0]
                    result = super().format(record)
                    # Restore original name
                    record.name = original_name
                    return result
            
            color_formatter = SimpleNameColorFormatter(
                "%(log_color)s" + log_format,
                log_colors=colors
            )
            console_handler.setFormatter(color_formatter)
        else:
            # Regular logs
            formatter = SimpleNameFormatter(log_format)
            console_handler.setFormatter(formatter)
            
        logger.addHandler(console_handler)
    
    # Add file output
    if full_log_path:
        file_handler = logging.FileHandler(
            filename=full_log_path,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        formatter = SimpleNameFormatter(log_format)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        # print(f"Logging {name}@{os.getpid()}: {full_log_path}")
    
    return logger

def log_progress(logger, file_count, total_files, start_time, current_time, logging_ratio = 0.1, log_every_file = False, **kwargs):
    """
    Log processing progress
    
    Args:
        file_count: Number of files processed
        total_files: Total number of files
        start_time: Start time
        current_time: Current time
    """
    elapsed_time = current_time - start_time
    if log_every_file or file_count / total_files > logging_ratio:
        progress_percent = (file_count / total_files) * 100 if total_files > 0 else 0
        
        # Calculate estimated remaining time
        if file_count > 0 and progress_percent < 100:
            time_per_file = elapsed_time / file_count
            remaining_files = total_files - file_count
            estimated_remaining_time = time_per_file * remaining_files
            
            logger.info(
                f"Progress: {progress_percent:.2f}% ({file_count}/{total_files}) | "
                f"Time used: {elapsed_time:.2f}s | "
                f"Est. remaining: {estimated_remaining_time:.2f}s" +
                (" | " + " | ".join([f"{k}: {v}" for k, v in kwargs.items()]) if kwargs else "")
            )
        else:
            logger.info(
                f"Progress: {progress_percent:.2f}% ({file_count}/{total_files}) | "
                f"Time used: {elapsed_time:.2f}s" +
                (" | " + " | ".join([f"{k}: {v}" for k, v in kwargs.items()]) if kwargs else "")
            )