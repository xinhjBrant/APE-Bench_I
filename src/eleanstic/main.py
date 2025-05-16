# Copyright (2025) Bytedance Ltd. and/or its affiliates.

"""
Eleanstic Main Program Entry
Provides a unified entry point for batch building and verification of commits

This module serves as the main entry point for the Eleanstic system, responsible for:
1. Reading configuration files
2. Initializing necessary components
3. Executing build or verification processes based on subcommands
4. Tracking task status
"""

import os
import sys
import time
import argparse
import concurrent.futures
import pandas as pd
import traceback
import datetime
from tqdm import tqdm
from itertools import groupby
import shutil
from .core import ConfigManager, CommitStatus, BuildCoordinator, VerifyCoordinator, FileMapManager
from .utils import run_command, setup_logger
from ..utils import load_jsonl
import random

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Eleanstic - Elastic Mathlib Agent")
    
    # Common parameters
    parser.add_argument(
        "--config", 
        type=str, 
        default="src/eleanstic/config.yaml", 
        help="Configuration file path"
    )
    
    parser.add_argument(
        "--max_workers", 
        type=int, 
        help="Maximum worker processes, overrides setting in config file"
    )

    parser.add_argument(
        "--input_file", 
        type=str,
        help="Path to file containing commits to process"
    )
    parser.add_argument(
        "--commit_id_key", 
        type=str, 
        default='commit_hash', 
        help="Key name for commit in JSON object"
    )
    
    # Create subcommand parsers
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # build subcommand
    build_parser = subparsers.add_parser("build", help="Build Lean code")
    build_parser.add_argument(
        "--force", 
        action="store_true", 
        help="Force rebuild of already processed commits"
    )
    
    # verify subcommand
    verify_parser = subparsers.add_parser("verify", help="Verify Lean code")
    verify_parser.add_argument(
        "--code_key", 
        type=str, 
        default="code", 
        help="Key name for Lean code in JSON object"
    )
    verify_parser.add_argument(
        "--results_dir", 
        type=str,
        default=None,
        help="Output directory for verification results"
    )
    return parser.parse_args()


def install_toolchains(toolchain_list, logger=None):
    """
    Install all required lean toolchains
    
    Args:
        toolchain_list: List of toolchains to install
        logger: Logger
    
    Returns:
        bool: Whether all installations were successful
    """
    if not toolchain_list:
        print("No toolchains to install")
        return True
    
    print(f"Starting installation of {len(toolchain_list)} toolchains...")
    
    success_count = 0
    
    # Use ThreadPoolExecutor to install toolchains in parallel
    with concurrent.futures.ThreadPoolExecutor() as executor:
        def install_one_toolchain(item):
            idx, toolchain = item
            toolchain = toolchain.strip()
            if not toolchain:
                return None
            
            print(f"[{idx+1}/{len(toolchain_list)}] Installing toolchain: {toolchain}")
            
            stdout_lines, stderr_lines, install_time, returncode = run_command(
                ["elan", "toolchain", "install", toolchain],
                os.getcwd(),
                logger
            )
            
            if returncode == 0 or 'is already installed' in ''.join(stderr_lines):
                print(f"Successfully installed toolchain {toolchain}, time taken {install_time:.1f} seconds")
                return True
            else:
                print(f"Failed to install toolchain {toolchain}: {''.join(stdout_lines)}\n{''.join(stderr_lines)}")
                return False
        
        # Submit all tasks to thread pool
        futures = {executor.submit(install_one_toolchain, (idx, toolchain)): (idx, toolchain) 
                   for idx, toolchain in enumerate(toolchain_list) if toolchain.strip()}
        
        # Collect results
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                success_count += 1
    
    print(f"Toolchain installation complete, success: {success_count}/{len(toolchain_list)}")
    return success_count == len(toolchain_list)

def worker(args):
    """
    Worker process wrapper function, used to unpack arguments and call worker function
    
    Args:
        args: Parameter dictionary, containing command, config_path, commit_id, etc.
        
    Returns:
        Return value of worker function
    """
    # Unpack parameters
    command = args["command"]
    config_path = args["config_path"]
    commit_id = args["commit_id"]
    force = args.get("force", False)
    lean_records = args.get("lean_records", None)
    code_key = args.get("code_key", None)
    results_dir = args.get("results_dir", None)
    start_timestamp = args.get("start_timestamp", None)
    
    # Re-create config and status_manager objects in the process
    config = ConfigManager(config_path)
    
    # Initialize status manager
    status_manager = CommitStatus(
        status_dir=config.absolute_status_dir,
    )
    
    log_file = os.path.abspath(
        os.path.join(
            config.paths.workspace_root, 
            'logs', 
            command, 
            f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{commit_id}_{os.getpid()}.log"
        )
    )
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # Create file mapping manager instead of database
    file_map_manager = FileMapManager(
        storage_dir=config.absolute_storage_dir,
        maps_dir=os.path.join(config.paths.workspace_root, "file_maps")
    )

    cache_dir = os.path.join(config.absolute_cache_dir, commit_id)

    try:
        if command == "build":
            # Build mode
            coordinator = BuildCoordinator(
                mathlib_repo_path=config.paths.mathlib_repo,
                worktree_dir=config.absolute_worktree_dir,
                file_map_manager=file_map_manager,
                status_manager=status_manager,
                cache_dir=cache_dir,
                remove_worktree_after_build=config.storage.remove_worktree_after_build,
                max_concurrent_file_storage=config.concurrency.max_concurrent_file_storage,
                download_timeout=config.cache.download_timeout,
                download_retries=config.cache.download_retries,
                retry_wait=config.cache.retry_wait,
                log_config=config.logging,
                log_file=log_file
            )

            print(f"Starting build for commit: {commit_id}")
            result = coordinator.build_commit(commit_id, force)
            return result
            
        elif command == "verify":
            # Verify mode
            if results_dir is None:
                if start_timestamp is None:
                    start_timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                results_dir = os.path.join(
                    config.paths.verify_results_dir,
                    f"results_{start_timestamp}")
            if not os.path.exists(results_dir):
                os.makedirs(results_dir, exist_ok=True)
            
            coordinator = VerifyCoordinator(
                worktree_dir=config.absolute_worktree_dir,
                file_map_manager=file_map_manager,
                status_manager=status_manager,
                cache_dir=config.absolute_cache_dir,
                max_concurrent_lean_verifications=config.concurrency.max_concurrent_lean_verifications,
                log_config=config.logging,
                log_file=log_file
            )
            
            print(f"Starting verification for commit: {commit_id}")
            result = coordinator.verify_commit(commit_id, lean_records, code_key, results_dir, timeout=config.verification.timeout)
            return commit_id, result
            
    except Exception as e:
        print(f"{command} commit [{commit_id}] failed: {traceback.format_exc()}")
        if command == "build":
            return {"success": False, "error": traceback.format_exc(), "commit_id": commit_id}
        else:  # verify
            return commit_id, {"success": False, "error": traceback.format_exc()}

def main():
    """Main program entry"""
    start_time = time.time()

    start_timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Parse command line arguments
    args = parse_arguments()
    
    # Check if command is provided
    if not args.command:
        print("Error: Must specify subcommand (build or verify)")
        sys.exit(1)
    
    # Initialize configuration manager
    try:
        config = ConfigManager(args.config)
        print(f"Loaded configuration file: {args.config}")
    except Exception as e:
        print(f"Failed to load configuration file: {e}")
        sys.exit(1)
    
    # If max_workers is specified on command line, override config file setting
    if args.max_workers:
        config.concurrency.max_workers = args.max_workers
        print(f"Set maximum worker processes to: {args.max_workers}")
    # random.seed(42)
    if args.input_file.endswith('.jsonl'):
        input_content = load_jsonl(args.input_file)
        lean_toolchain_list = list(set(i['toolchain_content'].strip() for i in input_content if 'toolchain_content' in i))
        commits = list(set([i[args.commit_id_key] for i in input_content]))
        random.shuffle(commits)
        lean_records_by_commit = {commit_id: list(records) for commit_id, records in groupby(sorted(input_content, key=lambda x: x[args.commit_id_key]), key=lambda x: x[args.commit_id_key])}
    elif args.input_file.endswith('.parquet'):
        input_content = pd.read_parquet(args.input_file)
        lean_toolchain_list = list(set(i.strip() for i in input_content['toolchain_content'])) if 'toolchain_content' in input_content else []
        commits = list(set([i[args.commit_id_key] for _, i in input_content.iterrows()]))
        random.shuffle(commits)
        lean_records_by_commit = {commit_id: group.to_dict('records') for commit_id, group in input_content.groupby(args.commit_id_key)}
    else:
        raise ValueError(f"Unsupported file format: {args.input_file}")
    
    if args.command == "build":
        if not commits:
            print(f"No commits found to process")
            sys.exit(0)
        
        # Install all required toolchains before parallel processing
        main_logger = setup_logger("main", **dict(config.logging))
        install_success = install_toolchains(lean_toolchain_list, main_logger)
        if not install_success:
            print("Warning: Some toolchains failed to install, continuing with build process")
            
        # Display processing summary
        print(f"Preparing to process {len(commits)} commits, maximum concurrency: {config.concurrency.max_workers}")
        
        # Prepare build statistics
        stats = {
            "total": len(commits),
            "success": 0,
            "failed": 0,
            "skipped": 0
        }
        
        # Use process pool for concurrent builds
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=config.concurrency.max_workers
        ) as executor:
            # Prepare task parameters
            tasks = [
                {
                    "command": "build", 
                    "config_path": args.config, 
                    "commit_id": commit, 
                    "force": args.force
                }
                for commit in commits
            ]
            
            # Submit all tasks
            future_to_commit = {
                executor.submit(worker, task): task["commit_id"]
                for task in tasks
            }
            
            # Process completed tasks
            with tqdm(total=len(commits), desc="Build Progress") as pbar:
                for future in concurrent.futures.as_completed(future_to_commit):
                    commit_id = future_to_commit[future]
                    try:
                        result = future.result()
                        if result.get("success"):
                            if result.get("skipped"):
                                pbar.write(f"Skipped already processed commit [{commit_id}]")
                                stats["skipped"] += 1
                            else:
                                pbar.write(f"Successfully built commit [{commit_id}]: {result.get('message')}")
                                stats["success"] += 1
                        else:
                            pbar.write(f"Failed to build commit [{commit_id}]: {result.get('error')}")
                            stats["failed"] += 1
                    except KeyboardInterrupt as e:
                        raise e
                    except Exception as e:
                        pbar.write(f"Error processing result for commit [{commit_id}]: {traceback.format_exc()}")
                        stats["failed"] += 1
                    pbar.set_postfix(stats)
                    pbar.update(1)
        
                # Delete cache directory
                cache_dir = config.absolute_cache_dir
                if os.path.exists(cache_dir):
                    print(f"Deleting cache directory: {cache_dir}")
                    shutil.rmtree(cache_dir)
                else:
                    print(f"Cache directory does not exist: {cache_dir}")
    
    elif args.command == "verify":
        if len(lean_records_by_commit) == 0:
            print("Lean file records are empty")
            sys.exit(0)

        assert all(item.get(args.code_key) for records in lean_records_by_commit.values() for item in records)

        print(f"Starting verification for {len(lean_records_by_commit)} commits, using {config.concurrency.max_workers} worker processes...")

        # Use ProcessPoolExecutor for multi-process processing
        with concurrent.futures.ProcessPoolExecutor(max_workers=config.concurrency.max_workers) as executor:
            # Prepare task parameters
            tasks = [
                {
                    "command": "verify", 
                    "config_path": args.config, 
                    "commit_id": commit_id, 
                    "lean_records": records, 
                    "code_key": args.code_key, 
                    "results_dir": args.results_dir,
                    "start_timestamp": start_timestamp
                }
                for commit_id, records in lean_records_by_commit.items()
            ]
            
            # Submit all tasks
            future_to_commit = {
                executor.submit(worker, task): task["commit_id"] 
                for task in tasks
            }
            
            with tqdm(total=len(lean_records_by_commit), desc="Verification Progress") as pbar:
                for future in concurrent.futures.as_completed(future_to_commit):
                    commit_id = future_to_commit[future]
                    try:
                        future.result()
                    except Exception as e:
                        print(f"Error processing commit {commit_id}: {traceback.format_exc()}")
                    pbar.update(1)

    # Display processing statistics
    elapsed_time = time.time() - start_time
    print(f"Processing complete, total time: {elapsed_time / 3600:.2f} hours ({elapsed_time:.2f} seconds)")

if __name__ == "__main__":
    main()