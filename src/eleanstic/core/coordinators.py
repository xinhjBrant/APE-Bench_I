# Copyright (2025) Bytedance Ltd. and/or its affiliates.

"""
Build Coordinator Module
Responsible for compilation and build process

This module implements build coordination functionality for Mathlib4 code, 
responsible for managing the build process, handling build dependencies, 
executing build commands, and storing build results. Uses semaphores to control
concurrent builds, ensuring reasonable system resource utilization.
"""
import os
import shutil
import threading
import time
import concurrent.futures
import traceback
import json
import hashlib
import subprocess
import random
import git

from ..utils import verify_with_lean, run_lake_build, run_command, setup_logger, log_progress
from ..core.status import STATUS_READY, STATUS_COLLAPSED, STATUS_FAILED_VERIFY
from ...utils import convert_to_serializable

def get_worktree_path(worktree_dir, commit_id: str) -> str:
    """
    Get the worktree path for a specified commit
    
    Generates the corresponding worktree directory path based on commit ID.
    
    Args:
        commit_id (str): Git commit hash
        
    Returns:
        str: Absolute worktree path
    """
    return os.path.join(worktree_dir, commit_id)

class BuildCoordinator:
    """
    Build Coordinator, responsible for building, storing and fetching processes
    
    Manages the build process of Mathlib4 code, including preparing worktrees, 
    obtaining caches, executing build commands, and storing build results. 
    Implements concurrency control and error handling.
    Merges cache management functionality, responsible for downloading and managing cache files.
    """
    
    def __init__(self, 
                 mathlib_repo_path,
                 worktree_dir, 
                 file_map_manager,
                 status_manager,
                 cache_dir: str,
                 remove_worktree_after_build=True,
                 max_concurrent_file_storage=16,
                 download_timeout: int = 600, 
                 download_retries: int = 3, 
                 retry_wait: int = 10, 
                 log_config = {},
                 log_file: str = None):
        """
        Initialize the build coordinator
        
        Args:
            mathlib_repo_path (str): Mathlib4 repository path
            worktree_dir (str): Worktree directory path, for storing worktrees for each commit
            file_map_manager: File mapping manager, for storing mapping relationships of .lake directory files
            status_manager: Manager for commit build status
            cache_dir (str): Cache directory path, for storing downloaded cache files
            remove_worktree_after_build (bool): Whether to delete the .lake directory after build, defaults to True
            max_concurrent_file_storage (int): Maximum number of parallel file storage threads, defaults to 16
            download_timeout (int): Download timeout in seconds, defaults to 600 seconds
            download_retries (int): Download retry count, defaults to 3 times
            retry_wait (int): Retry wait time in seconds, defaults to 10 seconds
            log_config (dict): Logging configuration
            log_file (str): Log file path
        """
        self.mathlib_repo_path = mathlib_repo_path
        self.worktree_dir = worktree_dir
        os.makedirs(self.worktree_dir, exist_ok=True)
        self.file_map_manager = file_map_manager
        self.log_file = log_file
        self.logger = setup_logger(__name__, log_file=log_file, **dict(log_config))

        self.remove_worktree_after_build = remove_worktree_after_build
        self.max_concurrent_file_storage = max_concurrent_file_storage
        
        # If status_manager is not provided, create a default instance
        self.status_manager = status_manager
        
        # Cache management related attributes
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        self.download_timeout = download_timeout
        self.download_retries = download_retries
        self.retry_wait = retry_wait
    
    def get_cache_for_worktree(self, worktree_path: str) -> bool:
        """
        Execute lake exe cache get command, retrying on failure according to settings
        
        Args:
            worktree_path (str): Worktree directory path
            
        Returns:
            bool: Whether cache retrieval was successful
        """
        retry_count = 0
        max_retries = self.download_retries
        
        while retry_count <= max_retries:
            if retry_count > 0:
                retry_wait = self.retry_wait * (1 + random.uniform(-0.2, 0.2))  # Add ±20% random variation to wait time
                self.logger.info(f"Retrying cache retrieval ({retry_count}/{max_retries}), wait time: {retry_wait} seconds")
                time.sleep(retry_wait)  # Wait specified seconds before retrying
                
            try:
                # Set environment variable for cache directory
                env = os.environ.copy()
                env["XDG_CACHE_HOME"] = self.cache_dir
                self.logger.info(f"Setting XDG_CACHE_HOME={self.cache_dir}")
                # Execute lake exe cache get command
                # Note: No need to specify cache file, lake handles it automatically
                self.logger.info("Executing lake exe cache get command")
                stdout_lines, stderr_lines, build_time, returncode = run_command(
                    ["lake", "exe", "cache", "get"],
                    worktree_path,
                    self.logger,
                    env
                )
                
                # Check if output contains success flag
                if returncode == 0:
                    self.logger.info("Cache retrieval successful")
                    return True
                else:
                    self.logger.error(f"Cache retrieval failed {worktree_path}: {''.join(line for line in (stderr_lines + stdout_lines) if not ' [attempted ' in line)}")
                    if retry_count >= max_retries:
                        return False
                    
            except subprocess.TimeoutExpired:
                self.logger.warning("Cache retrieval timeout")
                if retry_count >= max_retries:
                    return False
            except Exception as e:
                self.logger.error(f"Error executing cache get command: {traceback.format_exc()}")
                if retry_count >= max_retries:
                    return False
            
            retry_count += 1
            
        return False
    
    def build_commit(self, commit_id: str, force: bool = False) -> dict:
        """
        Build the specified commit
        
        Args:
            commit_id: Git commit hash
            force: Whether to force rebuild
            
        Returns:
            dict: Build result, contains success field indicating success or failure
        """            
        if not force:
            status = self.status_manager.get_commit_status(commit_id)
            if status and status.get('status') == STATUS_COLLAPSED:
                self.logger.info(f"Commit already built successfully, skipping: {commit_id}")
                return {'success': True, 'skipped': True, 'message': 'Already built'}
            
        # 1. Create worktree
        try:
            start_time = time.time()
            self.logger.info(f"Starting build for commit: {commit_id}")
            worktree_path = get_worktree_path(self.worktree_dir, commit_id)

            # Delete worktree directory if it exists
            if os.path.exists(worktree_path):
                self.logger.info(f"Deleting existing worktree directory: {worktree_path}")
                shutil.rmtree(worktree_path)

            self.logger.info(f"Creating worktree: {commit_id} -> {worktree_path}")
            repo = git.Repo(self.mathlib_repo_path)
            info = repo.git.worktree("add", "-f", "--detach", worktree_path, commit_id)
            self.logger.info(f"Worktree creation info: {info}")
            try:
                git.Repo(worktree_path)
            except Exception as e:
                self.logger.error(f"Failed to create worktree: {commit_id}")
                self._update_build_failure(commit_id, "Failed to create worktree")
                return {'success': False, 'error': 'Failed to create worktree'}

            lake_dir = os.path.join(worktree_path, ".lake")
            if os.path.exists(lake_dir):
                self.logger.info(f"Deleting .lake directory: {lake_dir}")
                shutil.rmtree(lake_dir)
            
            # 2. Download cache
            if not self.get_cache_for_worktree(worktree_path):
                self.logger.error(f"Failed to get cache, attempting direct build")
            
            # 3. Execute build
            build_success, build_message = run_lake_build(worktree_path, self.logger, self.cache_dir)
            
            if not build_success:
                self.logger.error(f"Mathlib build failed: {commit_id}")
                self._update_build_failure(commit_id, build_message)
                return {'success': False, 'error': f'Mathlib build failed: {build_message}'}
            
            # Calculate disk usage before cleanup
            self.logger.info(f"Calculating worktree disk usage for {commit_id}")
            worktree_size = self._get_directory_size(worktree_path)
            self.logger.info(f"Worktree disk usage: {worktree_size} bytes ({worktree_size / (1024*1024):.2f} MB)")
            
            if self.remove_worktree_after_build:
                cache_dir = self.cache_dir
                if os.path.exists(cache_dir):
                    self.logger.info(f"Deleting cache directory: {cache_dir}")
                    shutil.rmtree(cache_dir)
            
            # 4. Save worktree directory content
            if not self.store_worktree_directory(commit_id):
                self.logger.error(f"Failed to store worktree directory: {commit_id}")
                self._update_build_failure(commit_id, "Failed to store worktree directory")
                return {'success': False, 'error': 'Failed to store worktree directory'}
            
            # 5. Update status with disk usage information
            additional_data = {'full_size': worktree_size, 'build_time': time.time() - start_time}
            self.status_manager.update_commit_status(
                commit_id, 
                STATUS_COLLAPSED, 
                build_message,
                additional_data=additional_data
            )
            
            self.logger.info(f"Build successful: {commit_id}, time taken {time.time() - start_time:.2f} seconds")
            return {'success': True, 'message': f"Time taken {time.time() - start_time:.2f} seconds"}
        except Exception as e:
            self.logger.error(f"Exception during commit build: {commit_id}, error: {traceback.format_exc()}")
            self._update_build_failure(commit_id, f"Build exception: {traceback.format_exc()}")
            # Re-raise exception for upper layer handling
            raise
    
    def store_worktree_directory(self, commit_id: str) -> bool:
        """
        Store all files from the entire worktree directory to content storage
        
        Optimized processing flow:
        1. Collect all file paths in the worktree, distinguishing between regular files and symlinks
        2. Calculate hash values for regular files
        3. Check which files need to be copied by checking file existence
        4. Batch copy files that need processing
        
        Args:
            commit_id: Commit ID
                
        Returns:
            bool: Returns True on success, False on failure
        """
        try:
            # Get worktree path
            worktree_path = get_worktree_path(self.worktree_dir, commit_id)
            
            # Check if worktree directory exists
            if not os.path.exists(worktree_path) or not os.path.isdir(worktree_path):
                self.logger.error(f"Worktree directory does not exist: {worktree_path}")
                return False
            
            # 1. Collect all file paths and distinguish file types
            regular_files = []
            symlink_files = []
            
            for root, _, files in os.walk(worktree_path):
                for filename in files:
                    file_path = os.path.join(root, filename)
                    if os.path.islink(file_path):
                        symlink_files.append(file_path)
                    else:
                        regular_files.append(file_path)
            
            total_files = len(regular_files) + len(symlink_files)

            # 2. Calculate hash values for regular files
            self.logger.info(f"Starting to process worktree directory, total {total_files} files (regular files: {len(regular_files)}, symlinks: {len(symlink_files)})")
            
            start_time = time.time()

            file_hashes = {}
            for file_path in regular_files:
                rel_path = os.path.relpath(file_path, worktree_path)
                hasher = hashlib.sha256()
                with open(file_path, 'rb') as f:
                    for chunk in iter(lambda: f.read(4096), b''):
                        hasher.update(chunk)
                file_hashes[rel_path] = (hasher.hexdigest(), "regular")
            
            hash_time = time.time() - start_time
            self.logger.info(f"Hash calculation complete: {len(file_hashes)} files, time taken {hash_time:.2f} seconds")
            
            # 3. Process symlink files
            self.logger.info(f"Processing {len(symlink_files)} symlink files")
            for file_path in symlink_files:
                try:
                    hasher = hashlib.sha256()
                    target = os.readlink(file_path)
                    hasher.update(target.encode())
                    rel_path = os.path.relpath(file_path, worktree_path)
                    file_hashes[rel_path] = (hasher.hexdigest(), "symlink")
                except Exception as e:
                    self.logger.error(f"Failed to process symlink {file_path}: {str(e)}")
            
            # 4. Check which files need to be copied by directly checking existence
            files_to_copy = {}
            check_start = time.time()
            self.logger.info(f"Starting to check existence for {len(file_hashes)} files")
            
            for rel_path, (file_hash, file_type) in file_hashes.items():
                storage_path = self.file_map_manager.get_storage_path(file_hash)
                if not os.path.exists(storage_path):
                    files_to_copy[rel_path] = (file_hash, file_type)
            
            check_time = time.time() - check_start
            self.logger.info(f"File existence check complete: {len(files_to_copy)} new files to process, {len(file_hashes) - len(files_to_copy)} files already exist, time taken {check_time:.2f} seconds")
            
            # 5. Multi-threaded batch copy of files that need processing
            file_mappings = {}  # Final file mapping results
            total_copied = 0
            copy_lock = threading.Lock()
            
            # File copy worker function
            def copy_file_batch(batch_items):
                nonlocal total_copied
                
                for rel_path, (file_hash, file_type) in batch_items:
                    file_path = os.path.join(worktree_path, rel_path)
                    storage_path = self.file_map_manager.get_storage_path(file_hash)
                    
                    # Ensure target directory exists
                    os.makedirs(os.path.dirname(storage_path), exist_ok=True)
                    
                    if file_type == "symlink":
                        # Process symlink
                        if not os.path.exists(storage_path):
                            link_target = os.readlink(file_path)
                            with open(storage_path, 'w') as f:
                                f.write(link_target)
                    else:
                        # Process regular file
                        if not os.path.exists(storage_path):
                            shutil.copy2(file_path, storage_path)
                    
                    # Atomic operation, increment counter
                    with copy_lock:
                        total_copied += 1
            
            # Use thread pool for batch copying
            self.logger.info(f"Starting to copy {len(files_to_copy)} new files")
            
            # Distribute files evenly among threads
            max_workers = int(min(self.max_concurrent_file_storage, 16))  # Maximum 32 threads
            batch_size = max(1, len(files_to_copy) // max_workers)
            batches = []
            items = list(files_to_copy.items())
            
            for i in range(0, len(items), batch_size):
                batches.append(items[i:i+batch_size])
            
            # Use thread pool to copy files
            copy_start = time.time()
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(copy_file_batch, batch) for batch in batches]
                concurrent.futures.wait(futures)
            
            copy_time = time.time() - copy_start
            self.logger.info(f"File copying complete: copied {total_copied} files, time taken {copy_time:.2f} seconds")
            
            # 6. Build final file mappings
            for rel_path, (file_hash, file_type) in file_hashes.items():
                file_mappings[rel_path] = {
                    "hash": file_hash,
                    "type": file_type
                }
            
            # 7. Store file mappings
            self.logger.info(f"Storing file mappings for commit {commit_id}, {len(file_mappings)} files total")
            if not self.file_map_manager.store_file_mapping(commit_id, file_mappings):
                self.logger.error(f"Failed to store file mappings: {commit_id}")
                return False
            
            # 8. Cleanup
            if self.remove_worktree_after_build:
                self.logger.info(f"Deleting worktree directory: {worktree_path}")
                shutil.rmtree(worktree_path)
            
            total_time = time.time() - start_time
            self.logger.info(f"Worktree directory processing complete: processed {len(file_mappings)} files, copied {total_copied} files, total time {total_time:.2f} seconds")
            return True
        except Exception as e:
            self.logger.error(f"Error storing worktree directory: {traceback.format_exc()}")
            return False

    def _get_directory_size(self, path):
        """
        Calculate the total size of a directory in bytes using system du command
        
        Args:
            path: Directory path
            
        Returns:
            int: Total size in bytes
        """
        try:
            # Use du command to get directory size in KB (-k flag) and summarize (-s flag)
            # The output format will be: "12345 /path/to/directory"
            start_time = time.time()
            result = subprocess.run(['du', '-sk', path], capture_output=True, text=True, check=True)
            # Extract the size in KB from the output and convert to bytes
            total_size = int(result.stdout.split()[0]) * 1024  # Convert KB to bytes
        except Exception as e:
            self.logger.error(f"Error calculating directory size with du command: {str(e)}")
            # Fall back to more efficient Python method if du command fails
            try:
                total_size = 0
                for dirpath, dirnames, filenames in os.walk(path):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        if not os.path.islink(fp):  # Skip symbolic links
                            try:
                                total_size += os.path.getsize(fp)
                            except (FileNotFoundError, PermissionError):
                                # Skip files that can't be accessed
                                pass
            except Exception as e2:
                self.logger.error(f"Manual directory size calculation also failed: {str(e2)}")
                return 0
        finally:
            self.logger.info(f"Directory size calculation complete: {total_size} bytes ({total_size / (1024*1024):.2f} MB), time taken {time.time() - start_time:.2f} seconds")
            return total_size
            
    def _update_build_failure(self, commit_id: str, message: str, additional_data = None) -> None:
        """
        Update build failure status
        
        Args:
            commit_id: Git commit hash
            message: Failure message
            additional_data: Optional additional data to include in status
        """
        if self.status_manager:
            self.status_manager.update_commit_status(commit_id, "failed", message, additional_data)

class VerifyCoordinator:
    """Verification coordinator, used to retrieve .lake directory, verify build integrity, and validate Lean files."""
    def __init__(self, worktree_dir, file_map_manager, status_manager, cache_dir=None, log_config={}, log_file=None, failed_threshold=10, max_concurrent_lean_verifications=8):
        """
        Initialize verification coordinator
        
        Args:
            worktree_dir: Worktree directory
            file_map_manager: File mapping manager
            status_manager: Commit status manager
            cache_dir: Cache directory
            log_config: Logging configuration
            log_file: Log file path
            failed_threshold: Maximum allowed failed file count
            max_concurrent_lean_verifications: Maximum parallel Lean verification threads
        """
        self.worktree_dir = worktree_dir
        self.file_map_manager = file_map_manager
        self.status_manager = status_manager
        self.cache_dir = cache_dir
        self.logger = setup_logger(__name__, log_file=log_file, **dict(log_config))
        self.failed_threshold = failed_threshold
        self.max_concurrent_lean_verifications = max_concurrent_lean_verifications

    def restore_worktree_directory(self, commit_id):
        """
        Restore the entire worktree directory from file mappings
        
        Args:
            commit_id: Commit ID
            
        Returns:
            Number of failed files, 0 means completely successful
        """
        start_time = time.time()
        worktree_path = get_worktree_path(self.worktree_dir, commit_id)

        if os.path.exists(worktree_path):
            self.logger.info(f"Deleting existing worktree directory: {worktree_path}")
            shutil.rmtree(worktree_path)

        os.makedirs(worktree_path, exist_ok=True)
        
        # Get file mappings for this commit from file mapping manager
        self.logger.info(f"Starting to get file mappings for commit {commit_id}")
        file_mappings = self.file_map_manager.get_file_mapping(commit_id)
        
        if not file_mappings:
            self.logger.error(f"Cannot get file mappings for commit {commit_id}, restoration failed")
            return float('inf')  # Return infinity to indicate mapping retrieval failure
            
        total_files = len(file_mappings)
        self.logger.info(f"Restoring worktree directory for commit {commit_id}, {total_files} files total")
        
        # File counters for progress display
        restored_files = 0
        failed_files = 0
        
        # Batch process file copying function
        def restore_file_batch(file_batch, batch_idx=0):
            local_success = 0
            local_failed = 0
            batch_size = len(file_batch)
            is_first_batch = (batch_idx == 0)  # Flag whether this is the first batch
            
            # Set internal progress update timer
            last_log_time = time.time()
            log_interval = 60.0  # Update progress log every 60 seconds
            
            for i, (rel_path, file_info) in enumerate(file_batch):
                file_hash = file_info["hash"]
                file_type = file_info["type"]
                
                # Target path, restore original relative path under worktree_path
                dest_path = os.path.join(worktree_path, rel_path)
                
                # Skip if file already exists
                if os.path.exists(dest_path):
                    self.logger.debug(f"File {rel_path} already exists, skipping")
                    local_success += 1
                    continue
                
                # Try to restore file from storage system
                result, message = self.file_map_manager.restore_file(dest_path, file_hash, file_type)
                if not result:
                    self.logger.error(f"Failed to restore file: {message}")
                    local_failed += 1
                else:
                    local_success += 1
                
                # Periodically update progress, only in first batch
                current_time = time.time()
                if is_first_batch and (current_time - last_log_time > log_interval):
                    # Log progress
                    log_progress(
                        self.logger, 
                        i + 1, 
                        batch_size, 
                        start_time, 
                        current_time, 
                        log_every_file=False
                    )
                    last_log_time = current_time
            
            return local_success, local_failed
        
        # Determine thread pool size, default is 2x CPU cores, but not more than 32 threads
        max_workers = int(max(min(os.cpu_count() / 2, 64), 1))
        self.logger.info(f"Using {max_workers} threads for parallel file copying")
        
        # Split file list into batches
        file_items = list(file_mappings.items())

        random.shuffle(file_items)
        
        # Determine batch size based on thread count
        file_batches = [file_items[i::max_workers] for i in range(max_workers)]
        
        self.logger.info(f"Total files: {total_files}, Threads: {max_workers}, Batches: {len(file_batches)}")
        
        # Use thread pool to process file batches in parallel
        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit tasks for each batch and pass batch index
            futures = [
                executor.submit(restore_file_batch, batch, batch_idx=idx) 
                for idx, batch in enumerate(file_batches)
            ]
            
            # Wait for all tasks to complete
            for future in concurrent.futures.as_completed(futures):
                try:
                    success, failed = future.result()
                    restored_files += success
                    failed_files += failed
                    # Periodically update overall progress
                    completed_percentage = (restored_files + failed_files) / total_files * 100
                    self.logger.debug(f"Batch completed, total progress: {completed_percentage:.2f}%, Success: {restored_files}, Failed: {failed_files}")
                except Exception as e:
                    self.logger.error(f"Exception during batch file processing: {traceback.format_exc()}")
                    raise e
                
        used_time = time.time() - start_time
        self.logger.info(f"Worktree directory restoration for commit {commit_id} complete, time taken {used_time:.2f} seconds")
        self.logger.info(f"Result summary: Total files {total_files}, Success {restored_files}, Failed {failed_files}")
        
        if failed_files > 0:
            self.logger.warning(f"{failed_files} files failed to restore")
            
        return failed_files

    def verify_commit(self, commit_id, lean_records, code_key, result_dir, timeout=600):
        """
        Coordinate the entire verification process: restore worktree, verify build environment, validate Lean files, and record status.
        Use multi-threading to verify Lean records in parallel for improved performance.
        
        Args:
            commit_id: Commit ID
            lean_records: List of Lean records, each record contains a Lean code snippet
            code_key: Key name for Lean code in the record
            result_dir: Result output directory
            
        Returns:
            Verification result dictionary
        """
        self.logger.info(f"Starting verification for commit {commit_id}")
        start_time = time.time()
        # 1. Restore worktree
        failed_files = self.restore_worktree_directory(commit_id)
        if failed_files > self.failed_threshold:
            self.logger.error(f"Failed to restore worktree directory, commit {commit_id}, {failed_files} files failed")
            return {"commit_id": commit_id, "status": "restore_failed", "details": None}
            
        worktree_path = get_worktree_path(self.worktree_dir, commit_id)

        # 2. Run lake build for integrity verification
        build_success, build_message = run_lake_build(worktree_path, self.logger, self.cache_dir)
        if not build_success:
            self.logger.error(f"Verification build failed, commit {commit_id}: {build_message}")
            self.status_manager.update_commit_status(commit_id, STATUS_FAILED_VERIFY, f"Verify build failed: {build_message}")
            return {"commit_id": commit_id, "status": "build_failed", "details": build_message}

        # Update status to READY, preserving existing data like full_size
        self.status_manager.update_commit_status(commit_id, STATUS_READY, build_message)

        # 3. Verify Lean files - using multi-threading for parallel processing
        output_dir = os.path.join(result_dir, f"{commit_id}.jsonl")
        os.makedirs(os.path.dirname(output_dir), exist_ok=True)
        
        # Filter out records without code
        valid_records = [record for record in lean_records if record.get(code_key)]
        total_records = len(valid_records)
        
        if not valid_records:
            self.logger.warning(f"No valid Lean records found, commit: {commit_id}")
            return {
                "commit_id": commit_id, 
                "status": "success", 
                "details": "No valid Lean records found",
                "output_file": output_dir
            }
        
        self.logger.info(f"Starting to verify {total_records} Lean records, commit: {commit_id}")
        
        # Record verification results and counts
        verified_count = 0
        passed_records = 0
        completed_records = 0

        progress_lock = threading.Lock()
        
        # Determine thread pool size
        max_workers = int(max(1, min(self.max_concurrent_lean_verifications, 
                        os.cpu_count() / 4)))
        self.logger.info(f"Using {max_workers} threads to verify Lean records in parallel")
        
        # Open the file before creating the thread pool
        with open(output_dir, "w") as f:
            # Use thread pool for parallel verification
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Batch process Lean record verification
                def verify_batch(records_batch, file_handle, batch_idx=0):
                    nonlocal passed_records, completed_records
                    batch_size = len(records_batch)
                    is_first_batch = (batch_idx == 0)  # Flag whether this is the first batch
                    
                    # Set internal progress update timer
                    last_log_time = time.time()
                    log_interval = 60.0  # Update progress every 60 seconds
                    
                    for i, (idx, record) in enumerate(records_batch):
                        try:
                            res = verify_with_lean(record[code_key], worktree_path, self.logger, timeout)
                            
                            # Update local statistics
                            with progress_lock:
                                if res.get("pass"):
                                    passed_records += 1
                                if res.get("complete"):
                                    completed_records += 1
                                result_record = record.copy()
                                result_record["verification_result"] = res
                                file_handle.write(json.dumps(convert_to_serializable(result_record), ensure_ascii=False) + "\n")
                            
                            # Periodically update progress, only in first batch
                            current_time = time.time()
                            if is_first_batch and (current_time - last_log_time > log_interval):
                                # Log progress
                                log_progress(
                                    self.logger, 
                                    i + 1, 
                                    batch_size, 
                                    start_time, 
                                    current_time, 
                                    log_every_file=False,
                                    pass_rate=f"{passed_records}/{total_records} {(passed_records / total_records) if total_records else 0:.2%}",
                                    completed_rate=f"{completed_records}/{total_records} {(completed_records / total_records) if total_records else 0:.2%}"
                                )
                                last_log_time = current_time
                                
                        except Exception as e:
                            self.logger.error(f"Error during record {idx} verification: {traceback.format_exc()}")
                
                # Split records into batches
                indexed_records = [(idx, record) for idx, record in enumerate(valid_records)]
                batch_size = max(1, (total_records + max_workers - 1) // max_workers)
                record_batches = [indexed_records[i:i+batch_size] for i in range(0, total_records, batch_size)]
                
                self.logger.info(f"Total records: {total_records}, Threads: {max_workers}, Records per batch: {batch_size}, Batches: {len(record_batches)}")
                
                # Submit all batch tasks and pass the file handle
                futures = {
                    executor.submit(verify_batch, batch, f, batch_idx=idx): len(batch)
                    for idx, batch in enumerate(record_batches)
                }
                
                # Wait for all tasks to complete and process results
                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result()
                        verified_count += futures[future]
                    except Exception as e:
                        self.logger.error(f"Error processing verification batch results: {traceback.format_exc()}")
        
        total_time = time.time() - start_time
        self.logger.info(
            f"Completed verification of {verified_count}/{total_records} Lean records, "
            f"Time taken: {total_time:.2f} seconds, "
            f"Average per record: {(total_time / verified_count if verified_count else 0):.2f} seconds"
        )

        # 4. Delete worktree directory
        worktree_path = get_worktree_path(self.worktree_dir, commit_id)
        if os.path.exists(worktree_path):
            self.logger.info(f"Deleting worktree directory: {worktree_path}")
            shutil.rmtree(worktree_path)

        # 5. Update commit status to verified, preserving existing data like full_size
        self.status_manager.update_commit_status(commit_id, STATUS_COLLAPSED, f"Verification complete: {verified_count} Lean records")
        
        return {
            "commit_id": commit_id, 
            "status": "success", 
            "details": f"Verified {verified_count} Lean records",
            "output_file": output_dir
        }