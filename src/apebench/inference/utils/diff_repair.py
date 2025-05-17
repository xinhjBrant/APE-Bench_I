from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict
import difflib
import math
import traceback
import re
import tempfile
import os
import subprocess
from collections import defaultdict
import json

# Import apply_hunk_to_content from collect_commit_data
from ...data.collect_commit_data import apply_hunk_to_content


@dataclass
class DiffLine:
    prefix: str  # ' ', '-', '+'
    content: str
    original_line_number: Optional[int] = None  # Line number in original file
    original_hunk_line_number: Optional[int] = None  # Line number in original hunk


@dataclass
class Hunk:
    start_line: int  # @@ -start_line,count @@ in original file (1-indexed)
    line_count: int  # Lines covered in original file
    lines: List[DiffLine]
    new_start_line: Optional[int] = None  # Starting line in new file after applying previous hunks
    new_line_count: Optional[int] = None  # Line count in new file


class DiffRepairError(Exception):
    """Base class for DiffRepair exceptions."""
    pass


class HunkRepairError(DiffRepairError):
    """Exception raised when a hunk cannot be repaired."""
    pass


class HunkApplicationError(DiffRepairError):
    """Exception raised when a repaired hunk cannot be applied."""
    pass


class DiffRepair:
    def __init__(self, original_text: str, diff_text: str, strict_match_threshold: float = 0.5, max_context_lines: int = 3, exact_match: bool = False):
        """
        Initialize the DiffRepair with original text and diff text.
        
        Args:
            original_text: The original text content
            diff_text: The diff to repair
            strict_match_threshold: Threshold for required matching anchors
            max_context_lines: Maximum context lines to keep around modifications
            exact_match: Whether to use exact matching (baseline) instead of fuzzy matching
        """
        self.original_lines = original_text.split('\n')
        self.diff_text = diff_text
        self.hunks = self._parse_hunks(diff_text)
        self.last_hunk_start = 0  # Track the end position of last processed hunk (0-indexed)
        self.last_hunk_end = 0  # Track the end position of last processed hunk (0-indexed)
        self.strict_match_threshold = strict_match_threshold
        self.max_context_lines = max_context_lines
        self.exact_match = exact_match
    
    def _parse_hunks(self, diff_text: str) -> List[Hunk]:
        """
        Parse diff text into Hunk objects.
        
        Args:
            diff_text: The diff text to parse
            
        Returns:
            List of Hunk objects
        """
        
        # Split into lines for processing
        lines = diff_text.split('\n')
        
        # Check if this is a standard diff with hunk headers
        has_hunk_headers = any(line.startswith('@@') for line in lines)
        
        if not has_hunk_headers:
            # Treat entire diff as one hunk
            return self._parse_non_standard_diff(lines)
        
        # Parse standard diff with hunk headers
        return self._parse_standard_diff(lines)

    def _parse_non_standard_diff(self, lines: List[str]) -> List[Hunk]:
        """
        Parse a diff without hunk headers as a single hunk.
        
        Args:
            lines: List of lines from the diff
            
        Returns:
            List containing a single Hunk object
        """
        current_hunk = Hunk(0, 0, [])
        for i, line in enumerate(lines):
            if line:
                # Use existing prefix if present, otherwise default to context line
                if line[0] in (' ', '+', '-'):
                    prefix = line[0]
                    content = line[1:]
                else:
                    prefix = ' '
                    content = line
            else:
                prefix = ' '
                content = ''
            current_hunk.lines.append(DiffLine(prefix, content, original_hunk_line_number=i))
        return [current_hunk]

    def _parse_standard_diff(self, lines: List[str]) -> List[Hunk]:
        """
        Parse a standard diff with hunk headers.
        
        Args:
            lines: List of lines from the diff
            
        Returns:
            List of Hunk objects
        """
        hunks = []
        current_hunk = None

        for line in lines:
            if line.startswith("@@"):
                if current_hunk:
                    hunks.append(current_hunk)
                # [CRITICAL] **The original hunk header is not trustworthy, we shall omit it with a dummy line spread and fix it later**
                parts = line.split("@@")
                current_hunk = Hunk(0, 0, [])
                # Extract content after header if any
                if len(parts) >= 3:
                    content = parts[2].strip()
                    if content:
                        current_hunk.lines.append(DiffLine(' ', content, original_hunk_line_number=0))
            elif current_hunk is not None:
                prefix = line[0] if line else ' '
                content = line[1:] if line else ''
                current_hunk.lines.append(DiffLine(prefix, content, original_hunk_line_number=len(current_hunk.lines)))

        if current_hunk:
            hunks.append(current_hunk)
        return hunks

    @staticmethod
    def normalize_line(line: str) -> str:
        """Basic preprocessing: remove whitespace and convert to lowercase"""
        return line.strip(' \n\t·').lower()
    
    @staticmethod
    def _is_anchor_match(line1: str, line2: str) -> bool:
        """
        Check if two lines are similar enough to be considered a match.
        
        Args:
            line1: First line to compare
            line2: Second line to compare
            
        Returns:
            True if lines match, False otherwise
        """
        if line1 == line2:
            return True
        if line2.startswith(line1) and len(line1) > len(line2) / 2:
            return True
        tokens1 = [token for token in line1.split() if token.strip()]
        tokens2 = [token for token in line2.split() if token.strip()]
        if len(tokens1) != len(tokens2):
            return False
        diff_count = sum(1 for a, b in zip(tokens1, tokens2) if a != b)
        return diff_count / max(len(tokens1), 1) < 0.1  # Avoid division by zero
    
    def _find_candidate_region_exact(self, hunk_context: List[str], line_is_modified: List[bool] = None) -> Tuple[int, int]:
        """
        Find the exact matching region in the original text for the hunk context.
        Baseline implementation that requires exact line matches.
        
        Args:
            hunk_context: List of context lines from the hunk
            line_is_modified: List indicating which lines are part of a modification
            
        Returns:
            Tuple of (start_position, length) for the matching region
            
        Raises:
            HunkRepairError: When no exact matching region is found
        """
        if not hunk_context:
            raise HunkRepairError("Hunk context is empty")
        
        # Default value for line_is_modified if not provided
        if line_is_modified is None:
            line_is_modified = [False] * len(hunk_context)
        
        # Find the first line that is not modified
        first_unmodified_idx = 0
        while first_unmodified_idx < len(hunk_context) and line_is_modified[first_unmodified_idx]:
            first_unmodified_idx += 1
        
        if first_unmodified_idx >= len(hunk_context):
            raise HunkRepairError("All lines in hunk are modified, can't find exact match")
        
        # Find all potential starting positions in the original text
        potential_starts = []
        for i in range(self.last_hunk_start, len(self.original_lines)):
            if self.original_lines[i] == hunk_context[first_unmodified_idx]:
                # Calculate the actual start position by going back to line 0 of hunk_context
                start_pos = i - first_unmodified_idx
                potential_starts.append(start_pos)
        
        if not potential_starts:
            raise HunkRepairError(f"No exact match found for line: '{hunk_context[first_unmodified_idx]}'")
        
        # For each potential start, check if all unmodified lines match exactly
        for start_pos in potential_starts:
            valid_match = True
            
            for i in range(len(hunk_context)):
                # Skip modified lines
                if line_is_modified[i]:
                    continue
                    
                # Calculate the corresponding index in original text
                orig_idx = start_pos + i
                
                # Check if index is out of bounds
                if orig_idx < 0 or orig_idx >= len(self.original_lines):
                    valid_match = False
                    break
                    
                # Check if lines match exactly
                if hunk_context[i] != self.original_lines[orig_idx]:
                    valid_match = False
                    break
            
            if valid_match:
                # Return the matching region
                return start_pos, len(hunk_context)
        
        raise HunkRepairError("No exact match found for the hunk context")

    # 3. 修改_find_candidate_region方法，使其根据exact_match参数选择匹配策略
    def _find_candidate_region(self, hunk_context: List[str], line_is_modified: List[bool] = None) -> Tuple[int, int]:
        """
        Find the best matching region in the original text for the hunk context.
        
        Args:
            hunk_context: List of context lines from the hunk
            line_is_modified: List indicating which lines are part of a modification
            
        Returns:
            Tuple of (start_position, length) for the best matching region
            
        Raises:
            HunkRepairError: When no matching region is found
        """
        # 根据exact_match参数决定使用精确匹配还是模糊匹配
        if self.exact_match:
            return self._find_candidate_region_exact(hunk_context, line_is_modified)
            
        # 以下是原有的模糊匹配逻辑
        norm_hunk_context = [self.normalize_line(line) for line in hunk_context]
        
        # Find all possible matching positions for each line
        all_matches = []  # [(hunk_line_idx, orig_line_idx), ...]
        for h_idx, h_line in enumerate(norm_hunk_context):
            if h_line.strip():
                matches = []
                for o_idx, orig_line in enumerate(self.original_lines[self.last_hunk_start:], start=self.last_hunk_start):
                    if self._is_anchor_match(h_line, self.normalize_line(orig_line)):
                        matches.append((h_idx, o_idx))
                if matches:
                    all_matches.append(matches)

        if not all_matches:
            raise HunkRepairError("No anchor matches found for hunk context")

        # Check if there are enough matching lines
        num_context = sum(1 for line in norm_hunk_context if line.strip())
        required = max(1, math.ceil(num_context * self.strict_match_threshold))
        if len(all_matches) < required:
            raise HunkRepairError(f"Anchor search failed: only found {len(all_matches)} anchors, need {required}")

        # Use dynamic programming to find the best match combination
        return self._find_best_region_with_dp(all_matches, line_is_modified)
        
    def _find_best_region_with_dp(self, all_matches: List[List[Tuple[int, int]]], line_is_modified: List[bool] = None) -> Tuple[int, int]:
        """
        Use dynamic programming to find the best match combination with priority to modified lines.
        
        Args:
            all_matches: List of matches for each line
            line_is_modified: List indicating which lines are part of a modification
            
        Returns:
            Tuple of (start_position, length) for the best matching region
            
        Raises:
            HunkRepairError: When no valid combination is found
        """
        # Default value for line_is_modified if not provided
        if line_is_modified is None:
            line_is_modified = [False] * max(h_idx for matches in all_matches for h_idx, _ in matches) + 1
        
        # dp[i][j] represents the minimum cost and maximum modified count for using first i hunk lines with last match at position j
        dp = {}  # (i, j) -> (cost, prev_j, modified_count)
        
        # Initialize first line's possible positions
        for h_idx, o_idx in all_matches[0]:
            modified_bonus = 1 if h_idx < len(line_is_modified) and line_is_modified[h_idx] else 0
            dp[(0, o_idx)] = (0, None, modified_bonus)
        
        # For each line, find the best previous match position
        for i in range(1, len(all_matches)):
            for h_idx_curr, curr_pos in all_matches[i]:
                modified_bonus = 1 if h_idx_curr < len(line_is_modified) and line_is_modified[h_idx_curr] else 0
                min_cost = float('inf')
                best_prev = None
                max_modified_count = -1
                
                for h_idx_prev, prev_pos in all_matches[i-1]:
                    if (i-1, prev_pos) not in dp:
                        continue
                        
                    prev_cost, _, prev_modified_count = dp[(i-1, prev_pos)]
                    
                    # Calculate gap difference as before
                    h_gap = h_idx_curr - h_idx_prev
                    o_gap = curr_pos - prev_pos
                    # Linear gap penalty instead of quadratic for better handling of small misalignments
                    gap_diff = abs(o_gap - h_gap)
                    cost = prev_cost + gap_diff
                    
                    # Calculate total modified count
                    total_modified_count = prev_modified_count + modified_bonus
                    
                    # Prioritize minimum cost, but if costs are equal, prioritize more modified lines
                    if cost < min_cost or (cost == min_cost and total_modified_count > max_modified_count):
                        min_cost = cost
                        best_prev = prev_pos
                        max_modified_count = total_modified_count
                
                if best_prev is not None:
                    dp[(i, curr_pos)] = (min_cost, best_prev, max_modified_count)
        
        # Find the position with minimum cost (and maximum modified count as a tiebreaker)
        min_cost = float('inf')
        best_last_pos = None
        max_modified_count = -1
        
        for h_idx, o_idx in all_matches[-1]:
            if (len(all_matches)-1, o_idx) in dp:
                curr_cost, _, curr_modified_count = dp[(len(all_matches)-1, o_idx)]
                if curr_cost < min_cost or (curr_cost == min_cost and curr_modified_count > max_modified_count):
                    min_cost = curr_cost
                    best_last_pos = o_idx
                    max_modified_count = curr_modified_count
        
        if best_last_pos is None:
            raise HunkRepairError("Failed to find valid anchor combination")
            
        # Backtrack to find all selected anchor positions
        anchors = []
        curr_pos = best_last_pos
        for i in range(len(all_matches)-1, -1, -1):
            anchors.append(curr_pos)
            curr_pos = dp[(i, curr_pos)][1]
        
        anchors.reverse()
        
        start = min(anchors)
        end = max(anchors) + 1
        return start, end - start

    def _is_pure_addition_hunk(self, hunk: Hunk) -> bool:
        """
        Check if a hunk contains only additions.
        
        Args:
            hunk: The hunk to check
            
        Returns:
            True if all lines are additions, False otherwise
        """
        return all(line.prefix == '+' for line in hunk.lines)
    
    def _handle_pure_addition_hunk(self, hunk: Hunk) -> Hunk:
        """
        Handle a hunk that contains only additions.
        
        Args:
            hunk: The pure addition hunk
            
        Returns:
            A properly configured hunk for pure additions
        """
        return Hunk(
            start_line=self.last_hunk_end + 1,
            line_count=0,
            lines=hunk.lines,
            new_start_line=None,
            new_line_count=len(hunk.lines)
        )

    def _extract_base_and_insertions(self, hunk: Hunk) -> Tuple[List[DiffLine], Dict[int, List[DiffLine]]]:
        """
        Extract base lines and map insertions to their positions.
        
        Args:
            hunk: The hunk to process
            
        Returns:
            Tuple of (base_lines, insertion_dict)
        """
        insertion_dict = defaultdict(list)  # Key: base index, -1 for insertions at start
        base_lines = []
        base_idx_counter = 0
        
        for idx, line in enumerate(hunk.lines):
            if line.prefix in [' ', '-']:
                base_lines.append(line)
                base_idx_counter += 1
            elif line.prefix == '+':
                attach_idx = base_idx_counter - 1 if base_idx_counter > 0 else -1
                insertion_dict[attach_idx].append(DiffLine('+', line.content, original_hunk_line_number=idx))
        
        return base_lines, insertion_dict

    def _align_and_repair_segments(self, base_lines: List[DiffLine], candidate_region: List[str], region_start: int) -> List[DiffLine]:
        """
        Align base lines with candidate region and create repaired segments.
        
        Args:
            base_lines: The base lines from the hunk
            candidate_region: The matching region from the original text
            region_start: The starting position of the region
            
        Returns:
            List of repaired DiffLine objects
        """
        damaged_preset = [line.content for line in base_lines]
        
        # Compare the damaged preset with the candidate region
        matcher = difflib.SequenceMatcher(None, damaged_preset, candidate_region)
        opcodes = matcher.get_opcodes()
        repaired_segments = []

        for tag, i1, i2, j1, j2 in opcodes:
            if tag == 'equal':
                for offset in range(j2 - j1):
                    orig_idx = i1 + offset
                    repaired_segments.append(DiffLine(
                        base_lines[orig_idx].prefix, 
                        candidate_region[j1 + offset], 
                        original_line_number=region_start + j1 + offset, 
                        original_hunk_line_number=orig_idx
                    ))
            elif tag == 'replace':
                num_candidate = j2 - j1
                num_damaged = i2 - i1
                for idx in range(num_candidate):
                    if idx < num_damaged:
                        orig_idx = i1 + idx
                        prefix = base_lines[orig_idx].prefix
                    else:
                        orig_idx = None
                        prefix = ' '
                    repaired_segments.append(DiffLine(
                        prefix, 
                        candidate_region[j1 + idx], 
                        original_line_number=region_start + j1 + idx, 
                        original_hunk_line_number=orig_idx
                    ))
            elif tag == 'insert':
                for offset in range(j2 - j1):
                    repaired_segments.append(DiffLine(
                        " ", 
                        candidate_region[j1 + offset], 
                        original_line_number=region_start + j1 + offset, 
                        original_hunk_line_number=None
                    ))
        
        return repaired_segments

    def _merge_with_insertions(self, hunk: Hunk, repaired_segments: List[DiffLine], insertion_dict: Dict[int, List[DiffLine]]) -> List[DiffLine]:
        """
        Merge repaired segments with insertions.
        
        Args:
            repaired_segments: The repaired segments
            insertion_dict: Mapping of insertions to positions
            
        Returns:
            List of merged DiffLine objects
        """
        if not repaired_segments:
            return []
            
        merged = []
        first_repair_line = [line.original_hunk_line_number for line in repaired_segments if line.original_hunk_line_number is not None][0]
        insertion_dict_ids = sorted(list(insertion_dict.keys()))
        for i in insertion_dict_ids:
            if i < first_repair_line:
                merged.extend(insertion_dict.pop(i))
        original_hunk_line_numbers = [line.original_hunk_line_number for line in repaired_segments if line.original_hunk_line_number is not None] + [float('inf')]
        for line in repaired_segments:
            merged.append(line)
            if line.original_hunk_line_number is not None:
                i = original_hunk_line_numbers.pop(0)
                assert i == line.original_hunk_line_number
                while i < original_hunk_line_numbers[0]:
                    if i in insertion_dict:
                        insertion = insertion_dict.pop(i)
                        if merged and merged[-1].content.strip() and merged[-1].prefix != '-' and insertion[0].content.strip() and insertion[0].original_hunk_line_number - 1 >= 0 and not hunk.lines[insertion[0].original_hunk_line_number - 1].content.strip():
                            merged.append(DiffLine('+', ''))
                        merged.extend(insertion)
                    if not insertion_dict:
                        break
                    i += 1
        
        return merged

    def _trim_context(self, merged: List[DiffLine]) -> List[DiffLine]:
        """
        Trim context to essential lines around modifications.
        If there are not enough context lines before the first modification or
        after the last modification, extract additional context from the original code to supplement.
        
        Args:
            merged: The merged lines
            
        Returns:
            List of trimmed DiffLine objects
        """
        if not merged:
            return []
            
        try:
            # Find the first and last modified lines
            first_modify_idx = next(idx for idx, line in enumerate(merged) if line.prefix != ' ')
            last_modify_idx = len(merged) - 1 - next(idx for idx, line in enumerate(merged[::-1]) if line.prefix != ' ')
            
            # Apply original trimming logic
            start_idx = max(0, first_modify_idx - self.max_context_lines)
            end_idx = min(len(merged), last_modify_idx + self.max_context_lines + 1)
            trimmed_lines = merged[start_idx:end_idx]
            
            # Handle insufficient context before first modification
            prefix_lines = []
            additional_context_needed = self.max_context_lines - first_modify_idx
            if additional_context_needed > 0:
                # Find a reference line with an original_line_number
                ref_idx = None
                for i in range(len(merged)):
                    if merged[i].original_line_number is not None:
                        ref_idx = i
                        break
                
                # If we couldn't find a reference, return with standard trimming
                if ref_idx is None:
                    return trimmed_lines
                    
                # Calculate what original line corresponds to the first merged line
                first_merged_orig_line = merged[ref_idx].original_line_number
                
                # Calculate where to start extracting from original file
                first_needed_line = max(0, first_merged_orig_line - additional_context_needed)
                
                # Extract additional context
                for i in range(first_needed_line, first_merged_orig_line):
                    prefix_lines.append(DiffLine(
                        prefix=' ',
                        content=self.original_lines[i],
                        original_line_number=i,
                        original_hunk_line_number=None
                    ))
            
            # Handle insufficient context after last modification
            suffix_lines = []
            additional_end_context_needed = self.max_context_lines - (len(merged) - 1 - last_modify_idx)
            if additional_end_context_needed > 0:
                # Find the last line with an original_line_number
                last_ref_idx = None
                for i in range(len(merged) - 1, -1, -1):
                    if merged[i].original_line_number is not None:
                        last_ref_idx = i
                        break
                
                # If we couldn't find a reference, return with standard trimming + prefix
                if last_ref_idx is None:
                    return prefix_lines + trimmed_lines
                    
                # Calculate what original line corresponds to the last merged line with a reference
                last_merged_orig_line = merged[last_ref_idx].original_line_number
                
                # Calculate where to end extracting from original file
                last_needed_line = min(len(self.original_lines), last_merged_orig_line + additional_end_context_needed + 1)
                
                # Extract additional context
                for i in range(last_merged_orig_line + 1, last_needed_line):
                    suffix_lines.append(DiffLine(
                        prefix=' ',
                        content=self.original_lines[i],
                        original_line_number=i,
                        original_hunk_line_number=None
                    ))
            
            # Combine and return
            return prefix_lines + trimmed_lines + suffix_lines
            
        except StopIteration as e:
            # If there are no modified lines, keep all context
            raise e

    def _create_new_hunk(self, lines: List[DiffLine]) -> Hunk:
        """
        Create a new hunk from the repaired lines.
        
        Args:
            lines: The repaired lines
            
        Returns:
            A properly configured Hunk object
        """
        if not lines:
            return Hunk(0, 0, [])
            
        # Check if this is a pure addition hunk
        if all(line.prefix == '+' for line in lines):
            return Hunk(
                start_line=self.last_hunk_start + 1,
                line_count=0,
                lines=lines,
                new_start_line=None,
                new_line_count=len(lines)
            )
        
        # Find the first unmodified or removed line for start position
        first_unmodified = next((line for line in lines if line.prefix != '+'), None)
        if first_unmodified is None:
            # Should not happen as we checked for pure addition above
            return Hunk(0, 0, lines)
            
        # Calculate line counts
        context_lines = sum(1 for line in lines if line.prefix == ' ')
        added_lines = sum(1 for line in lines if line.prefix == '+')
        removed_lines = sum(1 for line in lines if line.prefix == '-')
        
        return Hunk(
            start_line=first_unmodified.original_line_number + 1,  # 1-indexed
            line_count=context_lines + removed_lines,
            lines=lines,
            new_start_line=None,  # Will be set in repair method
            new_line_count=context_lines + added_lines
        )

    def _repair_hunk(self, hunk: Hunk) -> Hunk:
        """
        Repair a single hunk by finding the best matching region in the original text.
        
        Args:
            hunk: The hunk to repair
            
        Returns:
            A repaired Hunk object
        """
        # Handle special case for pure addition hunks
        if self._is_pure_addition_hunk(hunk):
            return self._handle_pure_addition_hunk(hunk)
        
        # Extract base lines and insertion mapping
        base_lines, insertion_dict = self._extract_base_and_insertions(hunk)
        
        # Return original hunk if no base lines
        if not base_lines:
            return hunk
        
        # Identify which lines are modified (have a - prefix)
        line_is_modified = [line.prefix == '-' for line in base_lines]
        
        # Find matching region
        try:
            candidate_start, candidate_length = self._find_candidate_region(
                [line.content for line in base_lines], line_is_modified)
            candidate_region = self.original_lines[candidate_start: candidate_start + candidate_length]
            
            # Align and repair segments
            repaired_segments = self._align_and_repair_segments(base_lines, candidate_region, candidate_start)
            
            # Merge with insertions
            merged_lines = self._merge_with_insertions(hunk, repaired_segments, insertion_dict)
            
            # Trim context
            trimmed_lines = self._trim_context(merged_lines)
            
            # Create new hunk
            return self._create_new_hunk(trimmed_lines)
        except HunkRepairError as e:
            raise e


    def _process_hunk(self, hunk: Hunk) -> Hunk:
        """
        Process a single hunk and update state.
        
        Args:
            hunk_idx: Index of the hunk
            hunk: The hunk to process
            
        Returns:
            Repaired hunk
            
        Raises:
            HunkApplicationError: When the hunk cannot be applied
        """
        # 修复该hunk
        repaired_hunk = self._repair_hunk(hunk)
        if repaired_hunk.new_line_count is None:
            repaired_hunk.new_line_count = 0
        
        # 更新last_hunk位置
        self.last_hunk_start = (repaired_hunk.start_line - 1)
        self.last_hunk_end = (repaired_hunk.start_line - 1) + repaired_hunk.line_count
        
        return repaired_hunk

    def _generate_final_diff(self, repaired_hunks: List[Hunk]) -> str:
        """
        Generate the final diff text with correct headers.
        
        Args:
            repaired_hunks: List of repaired hunks
            
        Returns:
            String containing the final diff
        """
        diff_lines = []
        
        # Add file headers if not present
        if not any(line.startswith('---') for line in self.diff_text.split('\n')):
            if not any(line.startswith('+++') for line in self.diff_text.split('\n')):
                diff_lines.append("--- a/file")
                diff_lines.append("+++ b/file")
        
        for h in repaired_hunks:
            assert h.lines, "h.lines is empty"
            old_count = h.line_count
            new_count = h.new_line_count if h.new_line_count is not None else 0

            if not any(line.strip() for line in self.original_lines):
                # assert len(repaired_hunks) == 1
                h.start_line = 0
                old_count = 0

            diff_lines.append(f"@@ -{h.start_line},{old_count} +{h.new_start_line},{new_count} @@")
            for line in h.lines:
                diff_lines.append(f"{line.prefix}{line.content}")
        
        return '\n'.join(diff_lines).strip() + '\n'

    def repair(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Repair the entire diff.
        If the diff is a single hunk that's effectively a pure addition 
        (intended for new file creation or full replacement), 
        it returns (None, new_file_content).
        Otherwise, it returns (repaired_diff_text, None).
        
        Returns:
            A tuple (repaired_diff_text, new_file_content_if_pure_add_create)
        """
        # Check for single, effectively pure-addition hunk scenario
        if len(self.hunks) == 1:
            hunk = self.hunks[0]
            
            # A line is considered 'substantive' if it's a '+', '-', or a non-blank ' ' (context)
            # These are lines that define the structure or changes, not just empty formatting lines.
            substantive_lines = [
                line for line in hunk.lines 
                if (line.prefix == '+' or
                    line.prefix == '-' or
                    (line.prefix == ' ' and line.content.strip()))
            ]
            
            is_effectively_pure_add = False
            if substantive_lines: # If hunk is not empty or only blank context lines
                is_effectively_pure_add = True
                for line in substantive_lines:
                    if line.prefix != '+':
                        is_effectively_pure_add = False
                        break
            
            if is_effectively_pure_add:
                # This hunk consists only of additions when considering substantive lines.
                # Construct the new content directly from all '+' lines in the original hunk,
                # preserving their order.
                new_content_lines = [line.content for line in hunk.lines if line.prefix == '+']
                return None, "\n".join(new_content_lines)

        # Original repair logic follows if not the special case
        repaired_hunks = []
        
        # 第一阶段：仅修复各个hunk，不关注line_offset
        for hunk_idx, hunk in enumerate(self.hunks):
            try:
                # 找到最佳匹配区域并修复hunk
                repaired_hunk = self._repair_hunk(hunk)
                if repaired_hunk.new_line_count is None:
                    repaired_hunk.new_line_count = 0
                repaired_hunks.append(repaired_hunk)
            except Exception as e:
                # print(f"Error processing hunk {hunk_idx}, attempting recovery: {e}")
                # 恢复尝试，重置位置
                self.last_hunk_start = 0
                try:
                    repaired_hunk = self._repair_hunk(hunk)
                    if repaired_hunk.new_line_count is None:
                        repaired_hunk.new_line_count = 0
                    repaired_hunks.append(repaired_hunk)
                except Exception as e2:
                    # 跳过这个hunk
                    # print(f"Recovery failed, skipping hunk: {e2}")
                    continue
        
        assert repaired_hunks, "repaired_hunks is empty"
        # 按开始行排序hunks
        sorted_hunks = sorted(repaired_hunks, key=lambda h: h.start_line)
        
        # 过滤掉重叠的hunks
        non_overlapping_hunks = self._filter_overlapping_hunks(sorted_hunks)
        
        # 第二阶段：计算正确的行偏移量
        final_hunks = []
        cumulative_offset = 0
        
        for hunk in non_overlapping_hunks:
            # 计算此hunk添加和删除的行数
            added_lines = sum(1 for line in hunk.lines if line.prefix == '+')
            removed_lines = sum(1 for line in hunk.lines if line.prefix == '-')
            line_adjustment = added_lines - removed_lines
            
            # 使用累积偏移量更新new_start_line
            hunk.new_start_line = hunk.start_line + cumulative_offset
            final_hunks.append(hunk)
            
            # 为下一个hunk更新累积偏移量
            cumulative_offset += line_adjustment
        
        # 生成最终的diff
        return self._generate_final_diff(final_hunks), None

    def _filter_overlapping_hunks(self, sorted_hunks: List[Hunk]) -> List[Hunk]:
        """
        Filter out overlapping hunks, keeping the one with more significant changes.
        
        Args:
            sorted_hunks: List of hunks sorted by start_line
            
        Returns:
            List of non-overlapping hunks
        """
        if not sorted_hunks:
            return []
        
        result = [sorted_hunks[0]]
        
        for current in sorted_hunks[1:]:
            last = result[-1]
            
            # Check if hunks overlap
            last_end = last.start_line + last.line_count - 1
            
            if current.start_line <= last_end:
                # Hunks overlap, decide which one to keep
                
                # Calculate significance by counting non-context lines
                last_changes = sum(1 for line in last.lines if line.prefix != ' ')
                current_changes = sum(1 for line in current.lines if line.prefix != ' ')
                
                # Also consider total line changes as a secondary metric
                last_impact = sum(1 for line in last.lines if line.prefix == '+') - sum(1 for line in last.lines if line.prefix == '-')
                current_impact = sum(1 for line in current.lines if line.prefix == '+') - sum(1 for line in current.lines if line.prefix == '-')
                
                # Keep the hunk with more changes, or if equal, the one with bigger impact
                if current_changes > last_changes or (current_changes == last_changes and abs(current_impact) > abs(last_impact)):
                    # Replace with current hunk if it has more significant changes
                    result[-1] = current
                # Otherwise, keep the existing hunk
            else:
                # No overlap, add the current hunk
                result.append(current)
        
        return result


def apply_diff(original_code: str, diff_text: str) -> str:
    """
    Apply a diff to original code.
    
    Args:
        original_code: Original code content
        diff_text: Unified diff to apply
        
    Returns:
        Code after applying the diff
        
    Raises:
        ValueError: When the patch cannot be applied
    """
    # Handle empty original code case
    if not original_code:
        result_lines = []
        for line in diff_text.split('\n'):
            # Only keep addition lines
            if line.startswith('+') and not line.startswith('+++'):
                result_lines.append(line[1:])
        return "\n".join(result_lines)
    
    # Use the patch utility to apply the diff via apply_hunk_to_content
    patched_code = apply_hunk_to_content(original_code, diff_text)
    if patched_code is None:
        raise ValueError("Failed to apply patch")
    
    return patched_code

def generate_diff(original_content: str, new_content: str) -> str:
    """
    Generate a unified diff between original content and new content.
    
    Args:
        original_content: Original content
        new_content: New content
        
    Returns:
        String containing the unified diff
    """
    # Split content into lines
    original_lines = original_content.splitlines(True) if original_content else []
    new_lines = new_content.splitlines(True) if new_content else []
    
    # Generate diff
    diff_generator = difflib.unified_diff(
        original_lines, 
        new_lines,
        fromfile='a/file',
        tofile='b/file',
        n=3  # Context lines
    )
    
    # Join diff lines into a single string
    diff_text = ''.join(diff_generator)
    
    # Ensure diff ends with a newline
    if diff_text and not diff_text.endswith('\n'):
        diff_text += '\n'
    
    return diff_text

def process_repair_chunk(chunk_data, strict_match_threshold: float = 0.5, exact_match: bool = False):
    """
    Process a chunk of the dataframe using DiffRepair.
    
    Args:
        chunk_data: DataFrame chunk to process
        strict_match_threshold: Threshold for required matching anchors
        exact_match: Whether to use exact matching instead of fuzzy matching
        
    Returns:
        Tuple of (stats, successful_matches, failed_matches, time_taken)
    """
    import time
    chunk_stats = {}
    chunk_successful_matches = []
    chunk_failed_matches = []
    
    for _, row in chunk_data.iterrows():
        original_code = row['content_before'] if row['content_before'] is not None else ''
        model_name = row['raw_response']['model']
        for idx, gen_diff in enumerate(row['gen_diff']):
            start_time = time.time()
            if model_name not in chunk_stats:
                chunk_stats[model_name] = {'total': 0, 'success': 0, 'time_taken': 0}
            chunk_stats[model_name]['total'] += 1
            if gen_diff is None:
                chunk_failed_matches.append({
                    **row,
                    'gen_diff': None,
                    'repaired_diff': None,
                    'content_after_gen_diff': None,
                    'error': "Generated diff is None",
                    'raw_response': None
                })
            else:
                raw_response = row['raw_response'].copy()
                raw_response['choices'] = [raw_response['choices'][idx]]
                try:
                    repairer = DiffRepair(original_code, gen_diff, strict_match_threshold, max_context_lines=3, exact_match=exact_match)
                    repaired_diff_text, full_new_content = repairer.repair()
                    
                    content_after_gen_diff: Optional[str]
                    actual_diff_to_store: Optional[str]

                    if full_new_content is not None:
                        # Special case: repairer determined it's a full content replacement
                        content_after_gen_diff = full_new_content
                        actual_diff_to_store = generate_diff(original_code, full_new_content)
                    elif repaired_diff_text is not None:
                        # Standard case: repairer returned a patchable diff
                        content_after_gen_diff = apply_diff(original_code, repaired_diff_text)
                        actual_diff_to_store = generate_diff(original_code, content_after_gen_diff)
                    else:
                        # Repair failed to produce either, treat as failure for this item
                        raise Exception("DiffRepair.repair() returned (None, None), indicating an issue.")

                    chunk_stats[model_name]['success'] += 1
                    chunk_successful_matches.append({
                        **row,
                        'gen_diff': gen_diff,
                        'repaired_diff': actual_diff_to_store,  # Use the accurate diff
                        'content_after_gen_diff': content_after_gen_diff,
                        'raw_response': raw_response
                    })
                except Exception as e:
                    chunk_failed_matches.append({
                        **row,
                        'gen_diff': gen_diff,
                        'repaired_diff': None,
                        'content_after_gen_diff': None,
                        'error': traceback.format_exc(),
                        'raw_response': raw_response
                    })
            end_time = time.time()
            chunk_stats[model_name]['time_taken'] += end_time - start_time
    
    return chunk_stats, chunk_successful_matches, chunk_failed_matches