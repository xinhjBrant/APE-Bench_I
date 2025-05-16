# Copyright (2025) Bytedance Ltd. and/or its affiliates.
"""
A script to find and kill all processes containing a specific command pattern
"""

import os
import subprocess
import sys
import signal

def find_and_kill_processes(pattern):
    """
    Find and kill all processes containing the specified pattern
    
    Args:
        pattern: Command pattern to search for
    
    Returns:
        killed_count: Number of processes killed
    """
    # Use ps command to find all processes
    try:
        ps_output = subprocess.check_output(
            ["ps", "-ef"], 
            universal_newlines=True
        )
    except subprocess.SubprocessError as e:
        print(f"Error running ps command: {e}")
        return 0
    
    killed_count = 0
    current_pid = os.getpid()  # Get current script's PID
    
    # Iterate through all process lines
    for line in ps_output.strip().split('\n')[1:]:  # Skip header line
        parts = line.split()
        if len(parts) < 8:
            continue
            
        pid = int(parts[1])
        cmd = ' '.join(parts[7:])
        
        # If a matching process is found and it's not the current script itself
        if pattern in cmd and pid != current_pid:
            try:
                print(f"Terminating process {pid}: {cmd}")
                os.kill(pid, signal.SIGTERM)
                killed_count += 1
            except OSError as e:
                print(f"Error terminating process {pid}: {e}")
    
    return killed_count

if __name__ == "__main__":
    # Command pattern to search for
    for pattern in ["eleanstic", "lean", "lake"]:
        print(f"Finding and terminating processes containing '{pattern}'...")
        killed = find_and_kill_processes(pattern)
        
        if killed == 0:
            print("No matching processes found")
        else:
            print(f"Successfully terminated {killed} processes")

# Helper commands for monitoring disk space and directory sizes:
# 1. Monitor free space on the mounted volume every 20 seconds:
# while true; do echo "$(date) - Storage space: $(df -h | grep -E '/mnt/bd/ape-bench-dev$' | awk '{print $4}')"; sleep 20; done

# 2. Monitor used space on root and size of verify database storage directory every 60 seconds:
# while true; do echo "$(date) - Storage space: $(df -h | grep -E '/$' | awk '{print $3}') - Directory size: $(du -sh /mnt/bd/ape-bench-dev/ape-bench1/datasets/verify_database/storage/partitions 2>/dev/null || echo 'Cannot access')"; sleep 60; done

# 3. Monitor used space on mounted volume and size of verify database storage partitions every 20 seconds:
# while true; do echo "$(date) - Storage space: $(df -h | grep -E '/mnt/bd/ape-bench-dev$' | awk '{print $3}') - Directory size: $(du -sh /mnt/bd/ape-bench-dev/ape-bench1/datasets/verify_database/storage/partitions 2>/dev/null | awk '{print $1}')"; sleep 20; done