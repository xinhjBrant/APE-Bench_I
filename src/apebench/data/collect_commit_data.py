# Copyright (2025) Bytedance Ltd. and/or its affiliates.
import os
import re
import time
import argparse
import enum
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor
import concurrent.futures
import multiprocessing
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import traceback
from git import Repo, Commit, Diff, Blob
import tempfile
import subprocess
from datetime import datetime

class ChangeType(enum.Enum):
    """Enumeration of file change types"""
    CREATED = "created"      # Created file
    MODIFIED = "modified"    # Modified file
    DELETED = "deleted"      # Deleted file
    RENAMED = "renamed"      # Renamed file
    COPIED = "copied"        # Copied file
    UNKNOWN = "unknown"      # Unknown operation


@dataclass
class FileChange:
    """Represents change information for a single file"""
    file_path_before: Optional[str]  # File path before change, None if file is newly created
    file_path_after: Optional[str]   # File path after change, None if file is deleted
    content_before: Optional[str]    # File content before change, None if file is newly created
    content_after: Optional[str]     # File content after change, None if file is deleted
    gold_diff: str                        # Diff information for this file
    added_lines: int                # Number of lines added
    total_changes: int               # Total changed lines (all + and - lines)
    pure_changes: int                # Pure change lines (replacement lines counted as one modification)
    absolute_added_lines: int        # Absolute lines added
    change_type: ChangeType          # Change type: created, modified, or deleted
    
    # Statistics after filtering non-code content
    filtered_gold_diff: Optional[str] = None  # Filtered diff information
    filtered_added_lines: Optional[int] = None  # Filtered added lines
    filtered_total_changes: Optional[int] = None  # Filtered total changes
    filtered_pure_changes: Optional[int] = None  # Filtered pure changes
    filtered_absolute_added_lines: Optional[int] = None  # Filtered absolute added lines
    
    # Hunk information
    # hunk_header: Optional[str] = None  # Hunk header information
    # original_line_start: Optional[int] = None  # Starting line in original file
    # original_line_count: Optional[int] = None  # Line count in original file
    # new_line_start: Optional[int] = None  # Starting line in new file
    # new_line_count: Optional[int] = None  # Line count in new file
    is_split_hunk: bool = False  # Whether this is a split hunk
    
    def to_dict(self) -> Dict:
        return {
            'file_path_before': self.file_path_before,
            'file_path_after': self.file_path_after,
            'content_before': self.content_before,
            'content_after': self.content_after,
            'gold_diff': self.gold_diff,
            'added_lines': self.added_lines,
            'total_changes': self.total_changes,
            'pure_changes': self.pure_changes,
            'absolute_added_lines': self.absolute_added_lines,
            'change_type': self.change_type.value,  # Store the enum value
            'filtered_gold_diff': self.filtered_gold_diff,
            'filtered_added_lines': self.filtered_added_lines,
            'filtered_total_changes': self.filtered_total_changes,
            'filtered_pure_changes': self.filtered_pure_changes,
            'filtered_absolute_added_lines': self.filtered_absolute_added_lines,
            # 'hunk_header': self.hunk_header,
            # 'original_line_start': self.original_line_start,
            # 'original_line_count': self.original_line_count,
            # 'new_line_start': self.new_line_start,
            # 'new_line_count': self.new_line_count,
            'is_split_hunk': self.is_split_hunk,
        }


@dataclass
class CommitInfo:
    """Represents information for a single commit"""
    commit_hash: str                 # Commit hash
    author: str                      # Author
    message: str                     # Commit message
    date: str                        # Commit date
    parent_commit_hash: List[str]    # Parent commit hashes (may have multiple)
    toolchain_content: Optional[str] = None  # Content of mathlib4/lean-toolchain file

    def to_dict(self) -> Dict:
        return {
            'commit_hash': self.commit_hash,
            'author': self.author,
            'message': self.message,
            'date': self.date,
            'parent_commit_hash': self.parent_commit_hash,
            'toolchain_content': self.toolchain_content,
        }

def get_content(repo: Repo, parent_commit: Commit, file_path: str) -> Optional[str]:
    try:
        blob = parent_commit.tree[file_path]
        content = blob.data_stream.read().decode('utf-8', errors='replace')
    except ValueError as ve:
        if "could not be resolved" in str(ve):
            try:
                content = repo.git.execute(
                    ['git', 'cat-file', '-p', f"{parent_commit.hexsha}:{file_path}"],
                    with_stdout=True
                )
            except Exception:
                content = None
        else:
            raise ve
    return content

def split_diff_into_hunks(diff_text: str) -> List[Dict]:
    """
    Split a diff into individual hunks.
    
    Args:
        diff_text: The diff text to split
        
    Returns:
        List of dictionaries with hunk information
    """
    hunks = []
    
    # Pattern to match hunk headers
    hunk_pattern = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', re.MULTILINE)
    
    # Find file header (everything before the first hunk header)
    file_header = ''
    match = hunk_pattern.search(diff_text)
    if match:
        file_header = diff_text[:match.start()]
    
    # Find all hunk headers
    matches = list(hunk_pattern.finditer(diff_text))
    
    # Extract each hunk
    for i, match in enumerate(matches):
        # Determine hunk boundaries
        hunk_start = match.start()
        hunk_end = matches[i+1].start() if i < len(matches) - 1 else len(diff_text)
        
        # Extract hunk text
        hunk_text = diff_text[hunk_start:hunk_end]
        
        # Extract line numbers
        original_start = int(match.group(1))
        original_count = int(match.group(2) or 1)
        new_start = int(match.group(3))
        new_count = int(match.group(4) or 1)
        
        hunks.append({
            'text': hunk_text,
            'header': match.group(0),
            'original_start': original_start,
            'original_count': original_count,
            'new_start': new_start,
            'new_count': new_count,
            'file_header': file_header
        })
    
    return hunks

def apply_hunk_to_content(original_content: str, complete_diff: str) -> str:
    """
    Apply a hunk to the original content to get the modified content.
    
    Args:
        original_content: The original content
        complete_diff: The complete diff
        
    Returns:
        The content after applying the hunk
    """
    if original_content is None:
        return None
    
    # Create a temporary directory to work in
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create file paths within the temporary directory
        content_file_path = os.path.join(temp_dir, 'original_content')
        diff_file_path = os.path.join(temp_dir, 'diff_content')
        
        # Write files in the temporary directory
        with open(content_file_path, 'w', encoding='utf-8') as content_file:
            content_file.write(original_content)
        
        with open(diff_file_path, 'w', encoding='utf-8') as diff_file:
            diff_file.write(complete_diff)
        
        # Apply the patch within the temporary directory
        patch_cmd = ['patch', '-u', '-p0', '-f', '-l', '-N', '--no-backup-if-mismatch', content_file_path]
        with open(diff_file_path, 'r') as diff_input:
            result = subprocess.run(patch_cmd, stdin=diff_input, capture_output=True, text=True, cwd=temp_dir)
        
        # Read the result
        if result.returncode == 0:
            with open(content_file_path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            return None

def process_sequential_hunks(content_before: str, hunks: List[Dict], file_path_before: str, file_path_after: str, change_type: ChangeType) -> List[FileChange]:
    """
    Process hunks sequentially, applying each hunk to the content modified by previous hunks.
    
    Args:
        content_before: Original content
        hunks: List of hunk dictionaries (should be sorted by original line number)
        file_path_before: Path of the file before changes
        file_path_after: Path of the file after changes
        change_type: Type of change
        
    Returns:
        List of FileChange objects
    """
    if not hunks:
        return []
    
    # Check for overlapping hunks
    for i in range(1, len(hunks)):
        prev_hunk_end = hunks[i-1]['original_start'] + hunks[i-1]['original_count'] - 1
        curr_hunk_start = hunks[i]['original_start']
        if prev_hunk_end >= curr_hunk_start:
            raise ValueError(f"Overlapping hunks detected: previous hunk ends at line {prev_hunk_end}, current hunk starts at line {curr_hunk_start}")
    
    file_changes = []
    accumulated_content = content_before
    line_offset = 0  # Offset for adjusting original line numbers
    
    for hunk in hunks:
        # Adjust line numbers for current hunk based on changes from previous hunks
        adjusted_original_start = hunk['original_start'] + line_offset
        
        # Update the hunk header to reflect adjusted line numbers
        old_header = hunk['header']
        new_header = f"@@ -{adjusted_original_start},{hunk['original_count']} +{hunk['new_start']},{hunk['new_count']} @@"
        adjusted_text = hunk['text'].replace(old_header, new_header)
        
        # Apply this hunk to accumulated content
        complete_diff = f"{hunk['file_header']}{adjusted_text}"
        updated_content = apply_hunk_to_content(accumulated_content, complete_diff)
        
        if updated_content is None:
            raise ValueError(f"Failed to apply hunk: {adjusted_text}")
        
        # Calculate statistics for this hunk
        hunk_added_lines, hunk_total_changes, hunk_pure_changes, hunk_absolute_added_lines, _ = calculate_diff_stats(adjusted_text)

        filtered_diff, filtered_added_lines, filtered_total_changes, filtered_pure_changes, filtered_absolute_added_lines = calculate_filtered_diff_stats(accumulated_content, updated_content)
        
        # Create FileChange object for this hunk
        file_change = FileChange(
            file_path_before=file_path_before,
            file_path_after=file_path_after,
            content_before=accumulated_content,  # The content before applying this specific hunk
            content_after=updated_content,       # The content after applying this specific hunk
            gold_diff=adjusted_text,
            added_lines=hunk_added_lines,
            total_changes=hunk_total_changes,
            pure_changes=hunk_pure_changes,
            absolute_added_lines=hunk_absolute_added_lines,
            change_type=change_type,
            filtered_gold_diff=filtered_diff,
            filtered_added_lines=filtered_added_lines,
            filtered_total_changes=filtered_total_changes,
            filtered_pure_changes=filtered_pure_changes,
            filtered_absolute_added_lines=filtered_absolute_added_lines,
            # hunk_header=new_header,
            # original_line_start=adjusted_original_start,
            # original_line_count=hunk['original_count'],
            # new_line_start=hunk['new_start'],
            # new_line_count=hunk['new_count'],
            is_split_hunk=True
        )
        
        file_changes.append(file_change)
        
        # Update accumulated content for next hunk
        accumulated_content = updated_content
        
        # Update line offset for next hunk
        # The adjustment is the difference between lines added and lines removed
        line_adjustment = hunk['new_count'] - hunk['original_count']
        line_offset += line_adjustment
    
    return file_changes

def calculate_filtered_diff_stats(content_before: str, content_after: str) -> Tuple[int, int, int, int, int]:
    # Process filtered content
    filtered_content_before = remove_non_coding_content(content_before)
    filtered_content_after = remove_non_coding_content(content_after)
    
    # Generate filtered diff statistics
    filtered_diff, filtered_added_lines, filtered_total_changes, filtered_pure_changes, filtered_absolute_added_lines = None, None, None, None, None
    
    if filtered_content_before is not None or filtered_content_after is not None:
        # Create temporary files for filtered content
        with tempfile.NamedTemporaryFile(mode='w+', encoding='utf-8', delete=False) as f_before, \
            tempfile.NamedTemporaryFile(mode='w+', encoding='utf-8', delete=False) as f_after:
            
            f_before.write(filtered_content_before or '')
            f_after.write(filtered_content_after or '')
            
            f_before_path = f_before.name
            f_after_path = f_after.name
        
        try:
            # Generate filtered diff
            diff_cmd = ['diff', '-u', f_before_path, f_after_path]
            result = subprocess.run(diff_cmd, capture_output=True, text=True)
            
            filtered_diff = result.stdout
            filtered_diff = filtered_diff[filtered_diff.find('@@') : ]
            if filtered_diff:
                filtered_added_lines, filtered_total_changes, filtered_pure_changes, filtered_absolute_added_lines, _ = calculate_diff_stats(filtered_diff)
        
        except Exception as e:
            print(f"Error generating filtered diff: {e}")
        
        finally:
            # Clean up temporary files
            try:
                os.unlink(f_before_path)
                os.unlink(f_after_path)
            except:
                pass

    return filtered_diff, filtered_added_lines, filtered_total_changes, filtered_pure_changes, filtered_absolute_added_lines

def process_new_file_chunks(file_path_after: str, content_after: str, max_diff_lines: int) -> List[FileChange]:
    """
    Split a new file into chunks and create FileChange objects for each chunk.
    Ensures chunks don't split in the middle of multiline comments and
    each chunk ends with at least two newlines.
    
    Args:
        file_path_after: Path of the new file
        content_after: Content of the new file
        max_diff_lines: Maximum diff lines per chunk
        
    Returns:
        List of FileChange objects
    """
    if not content_after:
        return []
    
    # Find all multiline comments
    comment_pattern = r'/-.*?-/'
    comments = list(re.finditer(comment_pattern, content_after, re.DOTALL))
    comment_ranges = [(m.start(), m.end()) for m in comments]
    
    # Find potential split points (double newlines)
    split_points = [m.start() + 1 for m in re.finditer(r'\n\n', content_after)]  # +1 to position after first \n
    
    # Filter out split points that occur inside comments
    valid_split_points = []
    for point in split_points:
        inside_comment = False
        for start, end in comment_ranges:
            if start <= point <= end:
                inside_comment = True
                break
        if not inside_comment:
            valid_split_points.append(point)
    
    # Add the end of the file as the final split point
    valid_split_points.append(len(content_after))
    
    # Create initial chunks based on valid split points
    chunks = []
    last_point = 0
    for point in valid_split_points:
        chunk = content_after[last_point:point]
        if chunk:  # Skip empty chunks
            chunks.append(chunk)
        last_point = point
    
    # Combine chunks that are too small until they approach max_diff_lines
    combined_chunks = []
    current_chunk = ""
    current_lines = 0
    
    for chunk in chunks:
        chunk_lines = len(chunk.splitlines())
        
        if current_lines + chunk_lines <= max_diff_lines:
            current_chunk += chunk
            current_lines += chunk_lines
        else:
            if current_chunk:
                combined_chunks.append(current_chunk)
            current_chunk = chunk
            current_lines = chunk_lines
    
    if current_chunk:
        combined_chunks.append(current_chunk)
    
    # Generate FileChange objects for each combined chunk
    file_changes = []
    accumulated_content = ""
    
    for chunk in combined_chunks:
        content_before = accumulated_content
        content_after_chunk = accumulated_content + chunk
        
        # Generate diff between before and after
        with tempfile.NamedTemporaryFile(mode='w+', encoding='utf-8', delete=False) as f_before, \
             tempfile.NamedTemporaryFile(mode='w+', encoding='utf-8', delete=False) as f_after:
            
            f_before.write(content_before)
            f_after.write(content_after_chunk)
            
            f_before_path = f_before.name
            f_after_path = f_after.name
        
        try:
            # Generate diff using external diff command
            diff_cmd = ['diff', '-u', f_before_path, f_after_path]
            result = subprocess.run(diff_cmd, capture_output=True, text=True)
            diff_text = result.stdout
            diff_text = diff_text[diff_text.find('@@') : ]
            
            # Calculate statistics
            added_lines, total_changes, pure_changes, absolute_added_lines, _ = calculate_diff_stats(diff_text)

            filtered_diff, filtered_added_lines, filtered_total_changes, filtered_pure_changes, filtered_absolute_added_lines = calculate_filtered_diff_stats(content_before, content_after_chunk)
            
            # Create FileChange object
            file_change = FileChange(
                file_path_before=None,
                file_path_after=file_path_after,
                content_before=content_before,
                content_after=content_after_chunk,
                gold_diff=diff_text,
                added_lines=added_lines,
                total_changes=total_changes,
                pure_changes=pure_changes,
                absolute_added_lines=absolute_added_lines,
                change_type=ChangeType.CREATED,
                filtered_gold_diff=filtered_diff,
                filtered_added_lines=filtered_added_lines,
                filtered_total_changes=filtered_total_changes,
                filtered_pure_changes=filtered_pure_changes,
                filtered_absolute_added_lines=filtered_absolute_added_lines,
                # hunk_header=None,
                # original_line_start=None,
                # original_line_count=None,
                # new_line_start=None,
                # new_line_count=None,
                is_split_hunk=True
            )
            
            file_changes.append(file_change)
            
            # Update accumulated content for next chunk
            accumulated_content = content_after_chunk
            
        finally:
            # Clean up temporary files
            try:
                os.unlink(f_before_path)
                os.unlink(f_after_path)
            except:
                pass
    
    return file_changes

# Update split_diff_into_hunks to return sorted hunks
def split_diff_into_hunks(diff_text: str) -> List[Dict]:
    """
    Split a diff into individual hunks, sorted by original line number.
    
    Args:
        diff_text: The diff text to split
        
    Returns:
        List of dictionaries with hunk information, sorted by original line number
    """
    hunks = []
    
    # Pattern to match hunk headers
    hunk_pattern = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', re.MULTILINE)
    
    # Find file header (everything before the first hunk header)
    file_header = ''
    match = hunk_pattern.search(diff_text)
    if match:
        file_header = diff_text[:match.start()]
    
    # Find all hunk headers
    matches = list(hunk_pattern.finditer(diff_text))
    
    # Extract each hunk
    for i, match in enumerate(matches):
        # Determine hunk boundaries
        hunk_start = match.start()
        hunk_end = matches[i+1].start() if i < len(matches) - 1 else len(diff_text)
        
        # Extract hunk text
        hunk_text = diff_text[hunk_start:hunk_end]
        
        # Extract line numbers
        original_start = int(match.group(1))
        original_count = int(match.group(2) or 1)
        new_start = int(match.group(3))
        new_count = int(match.group(4) or 1)
        
        hunks.append({
            'text': hunk_text,
            'header': match.group(0),
            'original_start': original_start,
            'original_count': original_count,
            'new_start': new_start,
            'new_count': new_count,
            'file_header': file_header
        })
    
    # Sort hunks by original line number
    return sorted(hunks, key=lambda h: h['original_start'])

# Modify the process_diff function to use our new sequential processing
def process_diff(repo: Repo, diff: Diff, parent_commit: Commit, current_commit: Commit, max_diff_lines: int = 1000) -> List[FileChange]:
    """
    Process a diff to extract file change information. If the diff exceeds max_diff_lines,
    it will be processed sequentially, respecting dependencies between hunks.
    For new files, content is split into chunks separated by double newlines.
    
    Args:
        repo: Git repository object
        diff: Diff object
        parent_commit: Parent commit object
        current_commit: Current commit object
        max_diff_lines: Maximum number of diff lines before splitting
        
    Returns:
        A list of FileChange objects, with proper sequential processing
    """
    try:
        file_path_before = diff.a_path if diff.a_path != '/dev/null' else None
        file_path_after = diff.b_path if diff.b_path != '/dev/null' else None

        # Determine change type
        change_type = ChangeType.UNKNOWN
        if file_path_before is None and file_path_after is not None:
            change_type = ChangeType.CREATED
        elif file_path_before is not None and file_path_after is None:
            change_type = ChangeType.DELETED
        elif file_path_before != file_path_after and file_path_before is not None and file_path_after is not None:
            change_type = ChangeType.RENAMED
        elif file_path_before == file_path_after:
            change_type = ChangeType.MODIFIED
            
        # Check if it's a copy operation
        if hasattr(diff, 'copied') and diff.copied:
            change_type = ChangeType.COPIED

        # Get diff text
        diff_text = diff.diff.decode('utf-8', errors='replace')
        if not diff_text:
            return []  # Skip empty diffs

        # Get content before change
        content_before = None
        if file_path_before and parent_commit:
            try:
                content_before = get_content(repo, parent_commit, file_path_before)
            except Exception as e:
                raise e
        
        # Get content after change
        content_after = None
        if file_path_after:
            try:
                content_after = get_content(repo, current_commit, file_path_after)
            except Exception as e:
                raise e
        
        # Calculate original diff statistics
        added_lines, total_changes, pure_changes, absolute_added_lines, _ = calculate_diff_stats(diff_text)
        
        filtered_diff, filtered_added_lines, filtered_total_changes, filtered_pure_changes, filtered_absolute_added_lines = calculate_filtered_diff_stats(content_before, content_after)
        
        # Special handling based on change type and diff size
        if change_type == ChangeType.CREATED and content_after and pure_changes > max_diff_lines:
            # For new files with large diffs, split into chunks
            try:
                return process_new_file_chunks(file_path_after, content_after, max_diff_lines)
            except Exception as e:
                print(f"Error processing new file chunks: {e}")
                # Fall back to returning a single FileChange
                return [FileChange(
                    file_path_before=None,
                    file_path_after=file_path_after,
                    content_before=None,
                    content_after=content_after,
                    gold_diff=diff_text,
                    added_lines=added_lines,
                    total_changes=total_changes,
                    pure_changes=pure_changes,
                    absolute_added_lines=absolute_added_lines,
                    change_type=change_type,
                    filtered_gold_diff=filtered_diff,
                    filtered_added_lines=filtered_added_lines,
                    filtered_total_changes=filtered_total_changes,
                    filtered_pure_changes=filtered_pure_changes,
                    filtered_absolute_added_lines=filtered_absolute_added_lines
                )]
        
        elif pure_changes > max_diff_lines and change_type not in [ChangeType.DELETED]:
            # For modified files with large diffs, process hunks sequentially
            hunks = split_diff_into_hunks(diff_text)
            
            try:
                return process_sequential_hunks(content_before, hunks, file_path_before, file_path_after, change_type)
            except Exception as e:
                print(f"Error processing sequential hunks: {e}")
                # Fall back to returning a single FileChange
                return [FileChange(
                    file_path_before=file_path_before,
                    file_path_after=file_path_after,
                    content_before=content_before,
                    content_after=content_after,
                    gold_diff=diff_text,
                    added_lines=added_lines,
                    total_changes=total_changes,
                    pure_changes=pure_changes,
                    absolute_added_lines=absolute_added_lines,
                    change_type=change_type,
                    filtered_gold_diff=filtered_diff,
                    filtered_added_lines=filtered_added_lines,
                    filtered_total_changes=filtered_total_changes,
                    filtered_pure_changes=filtered_pure_changes,
                    filtered_absolute_added_lines=filtered_absolute_added_lines
                )]
        
        else:
            # For small diffs or deleted files, return a single FileChange
            return [FileChange(
                file_path_before=file_path_before,
                file_path_after=file_path_after,
                content_before=content_before,
                content_after=content_after,
                gold_diff=diff_text,
                added_lines=added_lines,
                total_changes=total_changes,
                pure_changes=pure_changes,
                absolute_added_lines=absolute_added_lines,
                change_type=change_type,
                filtered_gold_diff=filtered_diff,
                filtered_added_lines=filtered_added_lines,
                filtered_total_changes=filtered_total_changes,
                filtered_pure_changes=filtered_pure_changes,
                filtered_absolute_added_lines=filtered_absolute_added_lines
            )]

    except Exception as e:
        print(f"Error processing diff: {e}")
        traceback.print_exc()
        return []
    
def remove_non_coding_content(content: Optional[str]) -> Optional[str]:
    """
    Remove comments and other non-essential content from code
    
    Args:
        content: Code content
        
    Returns:
        Filtered code content
    """
    if content is None:
        return None
    
    non_coding_content_regex = re.compile(r'--.*?(\n|$)|/-.*?-/|#align.*?(\n|$)|set_option.*?(\n|$)|import.*?(\n|$)|open.*?(\n|$)|^\s*$\n', re.DOTALL)
    return non_coding_content_regex.sub('', content)


def calculate_diff_stats(diff_text: str) -> Tuple[int, int, int, int, int]:
    """
    Calculate difference statistics
    
    Args:
        diff_text: Difference text
        
    Returns:
        (added_lines, total_changes, pure_changes, absolute_added_lines, genuine_additions)
    """
    added_lines = 0     # Total added lines
    genuine_additions = 0  # Pure added lines (non-replacement part)
    removed_lines = 0    # Total removed lines
    genuine_removals = 0   # Pure removed lines (non-replacement part)
    replacements = 0     # Number of replacements

    diff_lines = diff_text.splitlines()
    i = 0
    while i < len(diff_lines):
        line = diff_lines[i]
        
        if line.startswith('-') and not line.startswith('---'):
            removed_lines += 1
            
            # Check if the next line is an added line (part of a replacement)
            if i + 1 < len(diff_lines) and diff_lines[i+1].startswith('+') and not diff_lines[i+1].startswith('+++'):
                replacements += 1
                i += 1  # Skip the next line as it's already counted as a replacement
                added_lines += 1  # Count added line
            else:
                genuine_removals += 1
            
        elif line.startswith('+') and not line.startswith('+++'):
            added_lines += 1
            genuine_additions += 1
        
        i += 1

    # Total modifications
    total_changes = added_lines + removed_lines
    pure_changes = genuine_additions + genuine_removals + replacements
    absolute_added_lines = added_lines - removed_lines
    
    return added_lines, total_changes, pure_changes, absolute_added_lines, genuine_additions

def process_commit(repo_path: str, commit_hash: str, max_diff_lines: int = 1000) -> Tuple[List[Dict], int, int, int]:
    """
    Process a single commit
    
    Args:
        repo_path: Path to Git repository
        commit_hash: Commit hash
        max_diff_lines: Maximum number of diff lines before splitting
    
    Returns:
        A tuple of (list of file change dictionaries, processed count, success count, file changes count)
    """
    processed_count = 0
    success_count = 0
    file_changes_count = 0
    try:
        # Create a new Repo instance for each process to ensure thread safety
        repo = Repo(repo_path)
        commit = repo.commit(commit_hash)
        
        # Get parent commit hashes
        parent_hashes = [p.hexsha for p in commit.parents]
        
        # Extract toolchain file content
        toolchain_content = None
        toolchain_path = "lean-toolchain"
        try:
            toolchain_content = get_content(repo, commit, toolchain_path)
        except Exception as e:
            # Toolchain file might not exist in this commit
            # print(f"Could not get toolchain file for commit {commit_hash}: {str(e)}")
            toolchain_content = None
        
        # Initialize commit info
        commit_info = CommitInfo(
            commit_hash=commit.hexsha,
            author=f"{commit.author.name} <{commit.author.email}>",
            message=commit.message,
            date=commit.committed_datetime.isoformat(),
            parent_commit_hash=parent_hashes,
            toolchain_content=toolchain_content,
        )
        
        file_changes = []

        # Process file changes
        if parent_hashes:
            # Has parent commit, calculate changes
            for parent in commit.parents:
                # Calculate diff for each parent commit
                diffs = parent.diff(commit, create_patch=True)
                
                # Process diff for each file
                for diff in diffs:
                    processed_count += 1
                    try:
                        file_change_list = process_diff(repo, diff, parent, commit, max_diff_lines)
                        
                        for file_change in file_change_list:
                            file_changes.append({**commit_info.to_dict(), **file_change.to_dict()})
                            file_changes_count += 1
                        
                        success_count += 1
                    except Exception as e:
                        print(f"Error processing diff in commit {commit_hash}: {e}")
        
        return file_changes, processed_count, success_count, file_changes_count
    
    except Exception as e:
        print(f"Error processing commit {commit_hash}: {e}")
        return [], processed_count, success_count, file_changes_count

def process_commit_batch(batch_info):
    """
    Process a batch of commits in a single process.
    
    Args:
        batch_info: Tuple containing (batch_id, commit_hashes, show_progress, repo_path, max_diff_lines)
    
    Returns:
        List of file change dictionaries, and processing statistics
    """
    batch_id, commit_hashes, show_progress, repo_path, max_diff_lines = batch_info
    
    file_changes = []
    total_processed = 0
    total_success = 0
    total_file_changes = 0
    total_commit_parent_pairs = 0
    
    start_time = time.time()
    for i, commit_hash in enumerate(commit_hashes):
        try:
            changes, processed, success, file_changes_count = process_commit(repo_path, commit_hash, max_diff_lines)
            file_changes.extend(changes)
            total_processed += processed
            total_success += success
            total_file_changes += file_changes_count
            
            # Count commit-parent pairs (assumes each commit has at least one parent)
            repo = Repo(repo_path)
            commit = repo.commit(commit_hash)
            total_commit_parent_pairs += len(commit.parents) if commit.parents else 0
            
            # Print progress if this is the progress-reporting batch and we hit a milestone
            if show_progress and ((i + 1) % 10 == 0 or (i + 1) == len(commit_hashes)):
                elapsed = time.time() - start_time
                commits_per_second = (i + 1) / elapsed if elapsed > 0 else 0
                progress_pct = (i + 1) / len(commit_hashes) * 100
                success_rate = (total_success / total_processed * 100) if total_processed > 0 else 0
                est_remaining = (elapsed / (i + 1)) * (len(commit_hashes) - (i + 1)) if (i + 1) > 0 else 0
                
                print(f"Batch {batch_id}: Processed {i + 1}/{len(commit_hashes)} commits ({progress_pct:.1f}%) | "
                      f"Speed: {commits_per_second:.2f} commits/sec | "
                      f"Success rate: {success_rate:.2f}% | "
                      f"Est. remaining: {est_remaining:.2f} sec")
        
        except Exception as e:
            print(f"Error processing commit {commit_hash} in batch {batch_id}: {e}")
    
    return file_changes, total_processed, total_success, total_file_changes, total_commit_parent_pairs, len(commit_hashes)

def extract_git_history_parallel(repo_path: str, max_workers: int = None, max_diff_lines: int = 1000) -> Tuple[List[Dict], Dict]:
    """
    Parallel extraction of all commit history and file change information from a Git repository
    using batch processing to reduce process creation overhead.
    
    Args:
        repo_path: Local path to the Git repository
        max_workers: Maximum number of parallel processes, defaults to CPU core count
        max_diff_lines: Maximum number of diff lines, beyond which diffs will be split into hunks
    
    Returns:
        A tuple of (list of file changes, dictionary of expansion statistics)
    """
    if max_workers is None:
        max_workers = min(32, multiprocessing.cpu_count())
    
    repo = Repo(repo_path)
    
    # Get hashes of all commits
    commit_hashes = [commit.hexsha for commit in repo.iter_commits()]
    total_commits = len(commit_hashes)
    print(f"Found {total_commits} commits, processing with {max_workers} workers in batch mode...")
    
    # Create batches of commits for parallel processing
    batches = []
    batch_size = max(1, (total_commits + max_workers - 1) // max_workers)  # Ceiling division
    
    for i in range(0, total_commits, batch_size):
        batch_commits = commit_hashes[i:i+batch_size]
        batch_id = i // batch_size
        show_progress = (batch_id == 0)  # Only the last batch shows detailed progress
        batches.append((batch_id, batch_commits, show_progress, repo_path, max_diff_lines))
    
    # Process batches in parallel
    file_changes = []
    total_processed = 0
    total_success = 0
    total_file_changes = 0
    total_commit_parent_pairs = 0
    total_commits_processed = 0
    completed_batches = 0
    
    start_time = time.time()
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all batches for processing
        future_to_batch = {executor.submit(process_commit_batch, batch): batch for batch in batches}
        
        for future in concurrent.futures.as_completed(future_to_batch):
            batch = future_to_batch[future]
            batch_id = batch[0]
            
            try:
                batch_changes, batch_processed, batch_success, batch_file_changes, batch_commit_parent_pairs, batch_commits = future.result()
                file_changes.extend(batch_changes)
                total_processed += batch_processed
                total_success += batch_success
                total_file_changes += batch_file_changes
                total_commit_parent_pairs += batch_commit_parent_pairs
                total_commits_processed += batch_commits
                
                # Update progress
                completed_batches += 1
                elapsed = time.time() - start_time
                completion_pct = (completed_batches / len(batches)) * 100
                success_rate = (total_success / total_processed * 100) if total_processed > 0 else 0
                est_remaining = (elapsed/completed_batches) * (len(batches)-completed_batches) if completed_batches > 0 else 0
                
                print(f"Completed batch {batch_id} ({completed_batches}/{len(batches)}) | "
                      f"{completion_pct:.1f}% complete | "
                      f"Elapsed time: {elapsed:.2f} sec | "
                      f"Success rate: {success_rate:.2f}% | "
                      f"Est. remaining: {est_remaining:.2f} sec")
                
            except Exception as e:
                print(f"Batch {batch_id} failed: {e}")
                traceback.print_exc()
    
    # Print final statistics
    elapsed = time.time() - start_time
    success_rate = (total_success / total_processed * 100) if total_processed > 0 else 0
    
    # Track expansion statistics
    expansion_stats = {
        'initial_commits': total_commits,
        'commit_parent_pairs': total_commit_parent_pairs,
        'file_changes': total_processed,
        'final_file_changes': total_file_changes  # After splitting into chunks
    }
    
    print(f"All batches completed in {elapsed:.2f} seconds")
    print(f"Total processed: {total_processed} changes with {total_success} successful operations")
    print(f"Initial commits: {total_commits}")
    print(f"Commit-parent pairs: {total_commit_parent_pairs}")
    print(f"File changes processed: {total_processed}")
    print(f"Final file changes after chunking: {total_file_changes}")
    print(f"Overall success rate: {success_rate:.2f}%")
    if elapsed > 0:
        print(f"Average processing speed: {len(file_changes) / elapsed:.2f} changes/sec")
    
    return file_changes, expansion_stats


def save_to_parquet(file_changes: List[Dict], expansion_stats: Dict, output_file: str) -> None:
    """
    Save commit information and expansion statistics as a Parquet file
    
    Args:
        file_changes: List of file change dictionaries
        expansion_stats: Dictionary containing expansion statistics
        output_file: Output file path
    """
    # Create DataFrame
    df = pd.DataFrame(file_changes)
    
    # Add expansion statistics as metadata
    metadata = {'expansion_stats': json.dumps(expansion_stats)}
    
    # Save as Parquet file with metadata
    table = pa.Table.from_pandas(df)
    pq.write_table(table, output_file, compression='snappy')
    
    # Also save a separate JSON file with expansion stats
    stats_file = output_file.replace('.parquet', '_expansion_stats.json')
    with open(stats_file, 'w') as f:
        json.dump(expansion_stats, f, indent=2)
    print(f"Expansion statistics saved to {stats_file}")


def main(repo_path: str, output_path: Optional[str], workers: int, max_diff_lines: int = 1000):
    start_time = time.time()
    date_stramp = datetime.now().strftime('%Y%m%d_%H%M%S')
    file_changes, expansion_stats = extract_git_history_parallel(repo_path, workers, max_diff_lines)
    
    # Process output path
    base_filename, ext = os.path.splitext(output_path)
    if ext == '':
        ext = '.parquet'
    elif ext != '.parquet':
        raise ValueError(f"Output file format must be .parquet, current format is {ext}")
    output_filename = f"{base_filename}{ext}"
    
    save_to_parquet(file_changes, expansion_stats, output_filename)
    print(f"Saved {len(file_changes)} file changes to {output_filename}")

    elapsed = time.time() - start_time
    print(f"Total processing time: {elapsed:.2f} seconds")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Parallel extraction of commit history and file change information from a Git repository')
    parser.add_argument('--repo_path', help='Local path to the Git repository')
    parser.add_argument('--output_path', '-o', help='Output file path')
    parser.add_argument('--workers', '-w', type=int, default=None, 
                        help='Number of parallel processes, defaults to CPU core count')
    parser.add_argument('--max_diff_lines', '-m', type=int, default=100,
                        help='Maximum number of diff lines, beyond which diffs will be split')
    
    args = parser.parse_args()
    main(args.repo_path, args.output_path, args.workers, args.max_diff_lines)