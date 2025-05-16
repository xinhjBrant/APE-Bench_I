# Copyright (2025) Bytedance Ltd. and/or its affiliates.
"""
Configuration management module responsible for loading, validating, and providing access to configurations
"""

import os
import json
import yaml
from typing import Dict, Any, Union
from .default_config import DEFAULT_CONFIG

class ConfigDict:
    """Class that allows dictionary data to be accessed via attributes"""
    
    def __init__(self, config_data: Dict[str, Any]):
        for key, value in config_data.items():
            if isinstance(value, dict):
                setattr(self, key, ConfigDict(value))
            else:
                setattr(self, key, value)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration back to a dictionary"""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, ConfigDict):
                result[key] = value.to_dict()
            else:
                result[key] = value
        return result

class ConfigManager:
    """Configuration manager"""
    
    def __init__(self, config_file: str = None):
        """
        Initialize the configuration manager
        
        Args:
            config_file: Optional path to a configuration file
        """
        # Load default configuration
        self.config_data = DEFAULT_CONFIG.copy()
        
        # If a configuration file is provided, load and merge it
        if config_file and os.path.exists(config_file):
            self._load_from_file(config_file)
        
        # Convert to attribute access form
        if config_file and not 'progress_log' in self.config_data:
            self.config_data['progress_log'] = config_file[ : config_file.find('.')] + '_progress.json'
        self.config = ConfigDict(self.config_data)
    
    def _load_from_file(self, config_file: str) -> None:
        """Load configuration from file and merge it"""
        file_extension = os.path.splitext(config_file)[1].lower()
        
        try:
            if file_extension == '.json':
                with open(config_file, 'r') as f:
                    user_config = json.load(f)
            elif file_extension in ('.yaml', '.yml'):
                with open(config_file, 'r') as f:
                    user_config = yaml.safe_load(f)
            else:
                raise ValueError(f"Unsupported config file format: {file_extension}")
            
            # Recursively merge configurations
            self._merge_configs(self.config_data, user_config)
        except Exception as e:
            print(f"Error loading config file: {e}")
    
    def _merge_configs(self, base: Dict[str, Any], override: Dict[str, Any]) -> None:
        """Recursively merge configuration dictionaries"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_configs(base[key], value)
            else:
                base[key] = value
    
    def get_config(self) -> ConfigDict:
        """Get the configuration object"""
        return self.config
    
    def save_config(self, output_file: str) -> None:
        """Save current configuration to a file"""
        file_extension = os.path.splitext(output_file)[1].lower()
        
        try:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            if file_extension == '.json':
                with open(output_file, 'w') as f:
                    json.dump(self.config_data, f, indent=2)
            elif file_extension in ('.yaml', '.yml'):
                with open(output_file, 'w') as f:
                    yaml.dump(self.config_data, f, default_flow_style=False)
            else:
                raise ValueError(f"Unsupported config file format: {file_extension}")
        except Exception as e:
            print(f"Error saving config file: {e}")