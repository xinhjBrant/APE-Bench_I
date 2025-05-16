# Copyright (2025) Bytedance Ltd. and/or its affiliates.

"""
Configuration Management Module
Responsible for loading and validating system configuration files, providing a unified configuration access interface

This module defines configuration models for various parts of the system using Pydantic for validation,
and provides the ConfigManager singleton class for managing the entire system's configuration.
"""
import os
import yaml
import traceback
from pathlib import Path
from pydantic import BaseModel, field_validator

# Define configuration models
class PathsConfig(BaseModel):
    """
    Path-related configuration
    
    Defines various paths required for system operation, including repository path, working directory,
    storage directory, cache directory, database path and log directory, etc.
    
    Attributes:
        mathlib_repo (str): Local path to Mathlib4 Git repository
        worktree_dir (str): Root directory for Git worktrees
        storage_dir (str): Root directory for content storage
        cache (str): Directory for cache file storage
        log_dir (str): Directory for log file storage
    """
    mathlib_repo: str = "mathlib4"
    workspace_root: str = "datasets/verify_database"
    status_dir: str = "status"
    worktree_dir: str = "worktrees"
    storage_dir: str = "storage"
    cache_dir: str = "cache"
    log_dir: str = "logs"
    
    @field_validator('mathlib_repo')
    def validate_mathlib_repo(cls, v: str) -> str:
        """
        Validate that the mathlib repository path exists
        
        Args:
            v (str): Repository path
            
        Returns:
            str: Validated path
            
        Warns:
            If path doesn't exist, a warning log is recorded
        """
        path = Path(v)
        if not path.exists():
            print(f"Mathlib repository path {v} does not exist!")
        return v

class ConcurrencyConfig(BaseModel):
    """
    Concurrency-related configuration
    
    Defines concurrency limit parameters for various parts of the system
    
    Attributes:
        max_workers (int): Maximum worker threads, default 8
        max_concurrent_file_storage (int): Maximum parallel file storage threads, default 16
        max_concurrent_lean_verifications (int): Maximum parallel Lean verification threads, default 8
    """
    max_workers: int = 8
    max_concurrent_file_storage: int = 16
    max_concurrent_lean_verifications: int = 8
    
    @field_validator('max_workers', 
                   'max_concurrent_file_storage', 'max_concurrent_lean_verifications')
    def validate_positive(cls, v: int) -> int:
        """
        Validate that concurrency parameters must be positive
        
        Args:
            v (int): Concurrency value to validate
            
        Returns:
            int: Validated value
            
        Raises:
            ValueError: If value is less than 1
        """
        if v < 1:
            raise ValueError("Concurrency value must be greater than 0")
        return v

class StorageConfig(BaseModel):
    """
    Storage-related configuration
    
    Defines configuration parameters for the content storage system
    
    Attributes:
        hash_algorithm (str): Hash algorithm to use, options are 'xxhash64' or 'sha256'
        max_in_memory_size_mb (int): Maximum size of a single file in memory (MB), default 100MB
    """
    hash_algorithm: str = "sha256"
    max_in_memory_size_mb: int = 100
    remove_worktree_after_build: bool = True
    
    @field_validator('hash_algorithm')
    def validate_hash_algorithm(cls, v: str) -> str:
        """
        Validate that the hash algorithm is supported
        
        Args:
            v (str): Hash algorithm name
            
        Returns:
            str: Validated hash algorithm name
            
        Raises:
            ValueError: If algorithm is not a supported option
        """
        if v not in ['xxhash64', 'sha256']:
            raise ValueError("Hash algorithm must be 'xxhash64' or 'sha256'")
        return v

class CacheConfig(BaseModel):
    """
    Cache-related configuration
    
    Defines configuration parameters for the cache system
    
    Attributes:
        download_retries (int): Download retry count, default 3 times
        download_timeout (int): Download timeout (seconds), default 600 seconds
        retry_wait (int): Retry wait time (seconds), default 10 seconds
    """
    download_retries: int = 3
    download_timeout: int = 600
    retry_wait: int = 10


class LoggingConfig(BaseModel):
    """
    Logging-related configuration
    
    Defines parameters for the logging system
    
    Attributes:
        level (str): Log level, options are 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
        max_size_mb (int): Maximum size of a single log file (MB)
        backup_count (int): Number of backup log files
        console_output (bool): Whether to output to console
        color_output (bool): Whether to enable colored output, default True
    """
    level: str = "INFO"
    max_size_mb: int = 100
    backup_count: int = 3
    console_output: bool = True
    color_output: bool = True
    
    @field_validator('level')
    def validate_level(cls, v: str) -> str:
        """
        Validate that the log level is valid
        
        Args:
            v (str): Log level
            
        Returns:
            str: Validated log level
            
        Raises:
            ValueError: If log level is not a valid option
        """
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v not in valid_levels:
            raise ValueError(f"Log level must be one of: {', '.join(valid_levels)}")
        return v

class VerificationConfig(BaseModel):
    """
    Verification-related configuration
    
    Defines configuration parameters for the verification service
    
    Attributes:
        timeout (int): Verification timeout (seconds), default 60 seconds
    """
    timeout: int = 600

class Config(BaseModel):
    """
    System total configuration
    
    Aggregates all sub-configurations into a complete configuration object
    
    Attributes:
        paths (PathsConfig): Path configuration
        concurrency (ConcurrencyConfig): Concurrency configuration
        storage (StorageConfig): Storage configuration
        cache (CacheConfig): Cache configuration
        logging (LoggingConfig): Logging configuration
        verification (VerificationConfig): Verification configuration
    """
    paths: PathsConfig = PathsConfig()
    concurrency: ConcurrencyConfig = ConcurrencyConfig()
    storage: StorageConfig = StorageConfig()
    cache: CacheConfig = CacheConfig()
    logging: LoggingConfig = LoggingConfig()
    verification: VerificationConfig = VerificationConfig()

class ConfigManager:
    """
    Configuration Manager
    
    A singleton implementation of the configuration manager, responsible for loading, validating and providing configuration objects
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        """
        Singleton pattern ensures only one configuration manager instance in the system
        
        Returns:
            ConfigManager: Configuration manager instance
        """
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, config_path = None):
        """
        Initialize configuration manager
        
        Args:
            config_path: Configuration file path, if not provided uses default path
        """ 
        # In singleton mode, initialize only once
        if type(self)._initialized:
            return
            
        self.config_path = config_path
        if not self.config_path:
            # Default configuration path
            self.config_path = os.environ.get(
                'MATHLIB_CONFIG',
                'config.yaml'
            )
        
        self.load_config()
        self.configure_absolute_paths()
        type(self)._initialized = True
    
    def load_config(self) -> None:
        """
        Load configuration file
        """
        
        try:
            assert os.path.exists(self.config_path)
            with open(self.config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            
            if not config_data:
                config_data = {}
            
            # First create default configuration
            self.config = Config()
            
            # If config_data has paths node, merge each sub-node
            if 'paths' in config_data:
                for key, value in config_data['paths'].items():
                    if hasattr(self.config.paths, key):
                        setattr(self.config.paths, key, value)
            
            # Merge other sections
            for section in ['concurrency', 'storage', 'cache', 'logging']:
                if section in config_data:
                    section_config = getattr(self.config, section)
                    for key, value in config_data[section].items():
                        if hasattr(section_config, key):
                            setattr(section_config, key, value)
            
            print(f"Configuration loaded from {self.config_path} and merged with defaults")
        except Exception as e:
            print(f"Error occurred: {traceback.format_exc()}, using default configuration")
            self.config = Config()
    
    def __getattr__(self, name: str):
        """
        Allow direct access to configuration attributes
        
        Args:
            name (str): Attribute name
            
        Returns:
            Any: Corresponding configuration attribute
            
        Raises:
            AttributeError: If attribute doesn't exist
        """
        if hasattr(self.config, name):
            return getattr(self.config, name)
        raise AttributeError(f"'{self.__class__.__name__}' has no attribute '{name}'")
    
    def configure_absolute_paths(self):
        self.absolute_worktree_dir = os.path.abspath(
            os.path.join(
                self.paths.workspace_root, 
                "worktrees"
            )
        )
        os.makedirs(self.absolute_worktree_dir, exist_ok=True)

        self.absolute_storage_dir = os.path.abspath(
            os.path.join(
                self.paths.workspace_root, 
                "storage"
            )
        )
        os.makedirs(self.absolute_storage_dir, exist_ok=True)

        self.absolute_cache_dir = os.path.abspath(
            os.path.join(
                self.paths.workspace_root, 
                "cache"
            )
        )
        os.makedirs(self.absolute_cache_dir, exist_ok=True)

        self.absolute_status_dir = os.path.abspath(
            os.path.join(
                self.paths.workspace_root, 
                "status"
            )
        )
        os.makedirs(self.absolute_status_dir, exist_ok=True)