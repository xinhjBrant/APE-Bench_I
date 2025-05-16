# Copyright (2025) Bytedance Ltd. and/or its affiliates.
from multiprocessing import Pool, cpu_count
import Levenshtein
import pandas as pd
import matplotlib.pyplot as plt
import tiktoken
from tqdm import tqdm
import re

def display_data_info(df):
    print("\nDataframe Overview:")
    print(f"Total records: {len(df)}")
    # print("\nSample record:")
    # print(df.sample(n=1).iloc[0].to_dict())
    print("\nAvailable columns:")
    print(df.keys())
    print("\nChange type distribution:")
    print(df['change_type'].value_counts())


def plot_histogram(data, title='Distribution', xlabel='Value', ylabel='Frequency', log_scale=False, save_path='histogram.png'):
    plt.figure(figsize=(10, 6))
    bins = max(data) - min(data) + 1
    plt.hist(data, bins=bins, edgecolor='black')
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    
    if log_scale:
        plt.yscale('log')
    
    plt.grid(True, alpha=0.3)
    # plt.show()
    plt.savefig(save_path)
    
    # Display statistics
    print(f"Min: {min(data)}, Max: {max(data)}, Avg: {sum(data)/len(data):.2f}")

def get_commit_type(message):
    TYPO_MAPS = {
        'faet': 'feat',
        'feature': 'feat',
        'featl': 'feat',
        'feeat': 'feat',
    }

    CHOSEN_COMMIT_TYPES = ['chore', 'feat', 'refactor', 'fix']
    commit_type = message[ : min(message.find(':'), message.find('('), message.find(')'), message.find('/'))].strip().lower()
    if commit_type in TYPO_MAPS:
        return TYPO_MAPS[commit_type]
    elif commit_type in CHOSEN_COMMIT_TYPES:
        return commit_type
    else:
        return None
    
def modify_lines(diff):
    lines = diff.split('\n')
    for line in lines:
        if line.startswith('+') or line.startswith('-'):
            yield line[1:]
        else:
            yield line

def process_token_count_batch(args):
    """Process a batch of text content, calculating their token counts"""
    i, batch, show_progress, _ = args
    encoding = tiktoken.encoding_for_model("gpt-4o")
    batch_iter = tqdm(batch) if show_progress else batch
    return {content: (len(encoding.encode(content)) if content else 0) for content in batch_iter}

def filter_by_token_limit(df, token_limit=16384):
    content_before_dedup = list(set(df['content_before']))
    print(f"Processing {len(content_before_dedup)} unique content items...")
    
    # Use generic parallel processing tools
    content_before_dedup_tokens_map = parallel_process(
        items=content_before_dedup,
        process_func=process_token_count_batch
    )
    
    df['input_tokens'] = df['content_before'].map(content_before_dedup_tokens_map)
    
    filtered_df = df[df['input_tokens'] <= token_limit]
    print(f"Records within {token_limit} token limit: {len(filtered_df)}")
    
    return filtered_df

def split_data(df, test_length=1000, redundancy_ratio=1.0):
    df = df.sort_values('date', ascending=False, key=lambda x: pd.to_datetime(x, format='%Y-%m-%dT%H:%M:%S%z', utc=True))
    test_size = int(test_length * (1 + redundancy_ratio))
    test_df = df.iloc[-test_size : ]
    return df, test_df

def analyze_modifications(str1, str2, scattered_threshold=1):
    """
    Analyze modifications between two strings, distinguishing between scattered edits and consecutive multi-character edits
    
    Args:
    - str1, str2: Two strings to compare
    - scattered_threshold: Threshold defining scattered edits, default is 1
    
    Returns:
    - scattered_count: Number of scattered edits
    - block_count: Number of consecutive multi-character edits
    - total_operations: Total number of edit operations
    """
    # Get detailed edit operations
    edit_ops = Levenshtein.editops(str1, str2)
    total_operations = len(edit_ops)
    
    if not edit_ops:
        return 0, 0, 0
    
    # Initialize
    blocks = []
    current_block = [edit_ops[0]]
    
    # Group edit operations into consecutive blocks
    for i in range(1, len(edit_ops)):
        prev_op = edit_ops[i-1]
        current_op = edit_ops[i]
        
        # Determine if it's a consecutive operation
        # Check continuity of operation type and position
        if (current_op[0] == prev_op[0] and  # Same operation type
            ((current_op[0] == 'insert' and current_op[2] == prev_op[2] + 1) or
             (current_op[0] == 'delete' and current_op[1] == prev_op[1] + 1) or
             (current_op[0] == 'replace' and 
              current_op[1] == prev_op[1] + 1 and 
              current_op[2] == prev_op[2] + 1))):
            # Add to current block
            current_block.append(current_op)
        else:
            # Start new block
            blocks.append(current_block)
            current_block = [current_op]
    
    # Add the last block
    blocks.append(current_block)
    
    # Count scattered edits and block edits
    scattered_count = 0
    block_count = 0
    
    for block in blocks:
        if len(block) <= scattered_threshold:
            # Scattered edit
            scattered_count += len(block)
        else:
            # Consecutive multi-character edit
            block_count += 1
    
    return scattered_count, block_count, total_operations

def analyze_code_modifications(before_code, after_code, scattered_threshold=1, return_details=False):
    """Analyze code modifications by comparing line by line"""
    before_lines = before_code.strip().split("\n")
    after_lines = after_code.strip().split("\n")
    
    # Match corresponding lines (simplified approach, assuming one-to-one correspondence)
    total_scattered = 0
    total_blocks = 0
    total_ops = 0
    if return_details:
        line_results = []
    else:
        line_results = None
    
    # Process lines within the minimum length range
    min_len = min(len(before_lines), len(after_lines))
    for i in range(min_len):
        scattered, blocks, ops = analyze_modifications(before_lines[i], after_lines[i], scattered_threshold)
        total_scattered += scattered
        total_blocks += blocks
        total_ops += ops
        if return_details and ops > 0:
            line_results.append((i+1, scattered, blocks, ops))
    
    # Process extra lines (if any)
    if len(before_lines) > len(after_lines):
        for i in range(min_len, len(before_lines)):
            # Delete entire line
            total_blocks += 1
            total_ops += len(before_lines[i])
            if return_details:
                line_results.append((i+1, 0, 1, len(before_lines[i])))
    elif len(after_lines) > len(before_lines):
        for i in range(min_len, len(after_lines)):
            # Add entire line
            total_blocks += 1
            total_ops += len(after_lines[i])
            if return_details:
                line_results.append((i+1, 0, 1, len(after_lines[i])))
    
    return total_scattered, total_blocks, total_ops, line_results

non_coding_content_regex = re.compile(r'--.*?(\n|$)|/-.*?-/|#align.*?(\n|$)|set_option.*?(\n|$)|import.*?(\n|$)|open.*?(\n|$)', re.DOTALL)

def calculate_edit_distance_batch(args):
    """
    Process a batch of rows, calculating their edit distances
    
    Returns dictionary: {index: edit_distance}
    """
    blank_regex = re.compile(r'[\s\n]', re.MULTILINE)
    
    i, batch, show_progress, kwargs = args
    min_edit_distance = kwargs['min_edit_distance']
    scattered_threshold = kwargs['scattered_threshold']
    max_scattered_count = kwargs['max_scattered_count']
    max_scattered_ratio = kwargs['max_scattered_ratio']
    batch_iter = tqdm(batch) if show_progress else batch
    
    results = {}
    for idx, row in batch_iter:
        _process_content = lambda content: blank_regex.sub('', non_coding_content_regex.sub('', content))
        
        if not row['content_before'] or not row['content_after']:
            results[idx] = True
            continue
            
        # If processed content is identical, set to 0
        before_processed = _process_content(row['content_before'])
        after_processed = _process_content(row['content_after'])
        
        if before_processed == after_processed:
            results[idx] = False
            continue
            
        # Calculate edit distance
        total_scattered, _, total_ops, _ = analyze_code_modifications(before_processed, after_processed, scattered_threshold=scattered_threshold, return_details=True)
        results[idx] = total_scattered <= max_scattered_count and total_scattered / total_ops < max_scattered_ratio and total_ops >= min_edit_distance
        
    return results

def filter_by_edit_distance(df, min_edit_distance=10, scattered_threshold=1, max_scattered_count=10, max_scattered_ratio=0.1):
    indexed_rows = [(idx, row) for idx, row in df.iterrows()]
    edit_distances = parallel_process(
        items=indexed_rows,
        process_func=calculate_edit_distance_batch,
        process_args={
            'min_edit_distance': min_edit_distance,
            'scattered_threshold': scattered_threshold,
            'max_scattered_count': max_scattered_count,
            'max_scattered_ratio': max_scattered_ratio
        }
    )
    # Use precalculated edit distances for filtering
    filtered_df = df[df.index.map(lambda idx: edit_distances.get(idx, None))]
    return filtered_df

def get_repeating_modifications(diff, repeat_threshold=0.8):
    lines = diff.split('\n')
    addition_lines = [line[1:].strip() for line in lines if line[1:].strip() and line.startswith('+')]
    if len(addition_lines) > 0 and len(set(addition_lines)) / len(addition_lines) < repeat_threshold:
        return False
    deletion_lines = [line[1:].strip() for line in lines if line[1:].strip() and line.startswith('-')]
    if len(deletion_lines) > 0 and len(set(deletion_lines)) / len(deletion_lines) < repeat_threshold:
        return False
    return True

def parallel_process(items, process_func, process_args=None, max_cpus=16, show_progress=True):
    """
    Generic parallel processing function to process a batch of items in parallel
    
    Args:
        items: List of items to process
        process_func: Function to process a single batch
        process_args: Additional parameter dictionary passed to process_func
        max_cpus: Maximum number of CPUs
        show_progress: Whether to show progress bar
    
    Returns:
        Merged processing results
    """
    if not items:
        return {}
    
    print(f"Processing {len(items)} items in parallel...")
    
    num_cpus = min(max_cpus, cpu_count())
    batches = [(i, items[i::num_cpus], show_progress and i == num_cpus - 1, process_args) 
               for i in range(num_cpus)]
    
    with Pool(num_cpus) as pool:
        results = list(pool.imap(process_func, batches))
    
    # Merge results
    combined_results = {}
    for result in results:
        combined_results.update(result)
    
    return combined_results

