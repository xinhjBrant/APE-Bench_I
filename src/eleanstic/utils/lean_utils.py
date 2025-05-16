# Copyright (2025) Bytedance Ltd. and/or its affiliates.

import os
import time
import subprocess
from typing import List, Tuple
import logging
import threading
import psutil
import signal
import random
import tempfile
import traceback

def run_command(command: List[str], cwd: str, logger: logging.Logger, env: dict = None) -> Tuple[List[str], List[str], float, int]:
    # Record start time
    start_time = time.time()
    
    # Use subprocess.run to execute command and wait for result
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env=env,
            check=False  # Don't automatically raise exceptions, let caller handle return code
        )
        
        # Process output results
        stdout_lines = []
        if result.stdout:
            stdout_lines = [line.strip() + '\n' for line in result.stdout.splitlines() if line.strip()]
            # for line in result.stdout.splitlines():
            #     if line.strip():
            #         logger.info(f"[lake build] {line.strip()}")
        
        stderr_lines = []
        if result.stderr:
            stderr_lines = [line.strip() + '\n' for line in result.stderr.splitlines() if line.strip()]
            # for line in result.stderr.splitlines():
            #     if line.strip():
            #         logger.warning(f"[lake build stderr] {line.strip()}")
        
        returncode = result.returncode
        
    except Exception as e:
        logger.error(f"Command execution exception: {traceback.format_exc()}")
        stderr_lines = [f"Command execution exception: {traceback.format_exc()}\n"]
        returncode = -1
    
    # Calculate build time
    build_time = time.time() - start_time
    return stdout_lines, stderr_lines, build_time, returncode

def run_lake_build(worktree_path: str, logger: logging.Logger, cache_dir: str = None) -> Tuple[bool, str]:
    """
    Run lake build command
    
    Args:
        worktree_path: Git worktree path
        
    Returns:
        Tuple[bool, str]: (success status, message)
    """
    try:
        # Check if worktree exists
        if not os.path.exists(worktree_path):
            return False, f"Worktree does not exist: {worktree_path}"
            
        # Execute lake build command
        logger.info(f"Starting to build Mathlib (worktree: {worktree_path})")
        
        # Set environment variables, specify cache directory
        env = os.environ.copy()
        if cache_dir:
            env["XDG_CACHE_HOME"] = cache_dir
            logger.info(f"Setting XDG_CACHE_HOME={cache_dir}")
        
        # Run lake build
        logger.info(f"Running lake build command")
        stdout_lines, stderr_lines, build_time, returncode = run_command(
            ["lake", "build"],
            worktree_path,
            logger,
            env
        )
        
        # Check build result
        if returncode == 0:
            logger.info(f"lake build completed, time taken {build_time:.1f} seconds")
            return True, f"lake build completed, time taken {build_time:.1f} seconds"
        else:
            error_message = "\n".join(line for line in (stderr_lines + stdout_lines) if not '] Building' in line)
            logger.error(f"lake build failed, time taken {build_time:.1f} seconds")
            return False, f"lake build failed, exit code {returncode}\n{error_message}"
            
    except Exception as e:
        logger.error(f"Error executing lake build: {traceback.format_exc()}")
        return False, f"Error executing lake build: {traceback.format_exc()}"
        
def parse_lean_output(output):
    """Parse Lean output, categorize each line as error, warning or info."""
    results = []
    for line in output.splitlines():
        line_lower = line.lower()
        if "error" in line_lower:
            results.append({"type": "error", "message": line.strip()})
        elif "warning" in line_lower:
            results.append({"type": "warning", "message": line.strip()})
        else:
            results.append({"type": "info", "message": line.strip()})
    return results

def verify_with_lean(content, worktree_path, logger, timeout=600):
    """Verify Lean file content.

    By creating a temporary Lean file at the given worktree path,
    call `lake env lean` to verify the file, and parse the output.
    """
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.lean', encoding='utf-8', delete=False) as temp_file:
        temp_file.write(content)
        temp_file.flush()
        temp_file_name = temp_file.name
        try:
            process = subprocess.run(
                ["lake", "env", "lean", temp_file_name],
                capture_output=True,
                text=True,
                cwd=worktree_path,
                timeout=timeout
            )
            lean_output = parse_lean_output(process.stdout)
            passed = (process.returncode == 0 and not any(r.get("type") == "error" for r in lean_output))
            complete = passed and not any(r.get("type") == "warning" for r in lean_output)
            result = {
                "parsed_output": lean_output,
                "raw_output": process.stdout,
                "raw_stderr": process.stderr,
                "returncode": process.returncode,
                "pass": passed,
                "complete": complete
            }
        except Exception as e:
            result = {
                "lean_output": None,
                "system_error": traceback.format_exc(),
                "pass": False,
                "complete": False
            }
            # logger.error(traceback.format_exc())
        finally:
            import os
            try:
                os.remove(temp_file_name)
            except Exception:
                pass
    return result