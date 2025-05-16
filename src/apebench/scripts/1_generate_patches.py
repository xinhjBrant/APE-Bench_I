# Copyright (2025) Bytedance Ltd. and/or its affiliates.

#!/usr/bin/env python3
"""
Patch generation script, runs the patch generation process according to configuration.
"""

import argparse
import os
import sys
from typing import List

def main():
    """Script entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Generate patches using multiple models and configurations")
    parser.add_argument("--config", type=str, default="config.yaml", help="Configuration file")
    args = parser.parse_args()
    
    # Ensure src can be imported
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
    
    # Import modules
    from ..evaluation_pipelines.patch_generator import generate_patches
    from ..config.config_manager import ConfigManager
    
    # Load configuration to confirm generation section exists
    config = ConfigManager(args.config).get_config()
    if not hasattr(config, 'generation'):
        print(f"Error: Configuration file {args.config} does not have a 'generation' section")
        sys.exit(1)
    
    # Execute generation
    output_files = generate_patches(args.config)
    
    print(f"\nGeneration task completed successfully!")
    print(f"Generated {len(output_files)} patch files.")
    print(f"Next step: Run the verification script using the same configuration file.")

if __name__ == "__main__":
    main()