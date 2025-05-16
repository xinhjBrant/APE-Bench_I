# Copyright (2025) Bytedance Ltd. and/or its affiliates.

import os
import re
import difflib
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set, Tuple
from datetime import datetime
import multiprocessing as mp
from tqdm import tqdm
import pandas as pd
import logging
import tiktoken
import pickle

@dataclass
class Position:
    """Position in a file"""
    line: int
    column: int


@dataclass
class Range:
    """Range in a file"""
    start: Position
    end: Position
    
    @property
    def line_count(self) -> int:
        return self.end.line - self.start.line + 1


@dataclass
class Import:
    """Represents an import statement"""
    module: str
    line_number: int


@dataclass
class Namespace:
    """Represents a namespace"""
    name: str
    start_line: int
    end_line: int
    
    @property
    def content_lines(self) -> int:
        return self.end_line - self.start_line + 1


@dataclass
class Declaration:
    """Represents a declaration"""
    type: str  # theorem, lemma, definition, etc.
    name: Optional[str]
    range: Range
    
    @property
    def content_lines(self):
        return self.range.line_count


@dataclass
class LeanFile:
    """Represents a Lean file"""
    path: str
    relative_path: str
    line_count: int
    imports: List[Import] = field(default_factory=list)
    namespaces: List[Namespace] = field(default_factory=list)
    declarations: List[Declaration] = field(default_factory=list)
    
    @property
    def import_count(self):
        return len(self.imports)
    
    @property
    def namespace_count(self):
        return len(self.namespaces)
    
    @property
    def declaration_count(self):
        return len(self.declarations)
    
    def get_declarations_by_type(self, decl_type):
        return [d for d in self.declarations if d.type == decl_type]


@dataclass
class FileChange:
    """Represents a file change"""
    file_path: str
    change_type: str  # A (added), M (modified), D (deleted), R (renamed)
    lines_added: int = 0
    lines_deleted: int = 0
    old_path: Optional[str] = None
    
    @property
    def is_addition(self):
        return self.change_type == 'A'
    
    @property
    def is_modification(self):
        return self.change_type == 'M'
    
    @property
    def is_deletion(self):
        return self.change_type == 'D'
    
    @property
    def is_rename(self):
        return self.change_type == 'R'
    
    @property
    def net_change(self):
        return self.lines_added - self.lines_deleted


@dataclass
class Commit:
    """Represents a commit"""
    hash: str
    author: str
    email: str
    date: datetime
    message: str
    type: str  # feature_addition, refactoring, bug_fix, documentation, other
    file_changes: List[FileChange] = field(default_factory=list)
    
    @property
    def file_count(self):
        return len(self.file_changes)
    
    @property
    def lines_added(self):
        return sum(fc.lines_added for fc in self.file_changes)
    
    @property
    def lines_deleted(self):
        return sum(fc.lines_deleted for fc in self.file_changes)
    
    @property
    def net_change(self):
        return self.lines_added - self.lines_deleted
    
    def get_changed_files_by_type(self, change_type):
        return [fc for fc in self.file_changes if fc.change_type == change_type]


class TokenType(Enum):
    """Token types for Lean 4 lexer"""
    DEFINITION_COMMAND = auto()   # inductive, structure, theorem, etc.
    KEYWORD = auto()              # namespace, end, import, etc.
    IDENTIFIER = auto()           # identifiers
    OPERATOR = auto()             # operators like :=, =, +, etc.
    PUNCTUATION = auto()          # :, (, ), {, }, etc.
    STRING = auto()               # "..." strings
    COMMENT = auto()              # comments
    WHITESPACE = auto()           # spaces, tabs, newlines
    UNKNOWN = auto()              # anything else
    EOF = auto()                  # end of file


@dataclass
class Token:
    """A token in Lean 4"""
    type: TokenType
    value: str
    line: int
    column: int
    position: int  # Position in the original text


@dataclass
class Definition:
    """Represents a definition in a Lean file (def, theorem, etc.)"""
    kind: str      # "def" or "theorem"
    type: str      # specific type (def, theorem, lemma, inductive, structure, class, etc.)
    name: str
    range: Range
    content: str = ""  # Stores the complete text content of the definition
    
    @property
    def line_count(self) -> int:
        return self.range.line_count


@dataclass
class FileStats:
    """Statistics for a Lean file"""
    def_count: int = 0
    theorem_count: int = 0
    definitions: List[Definition] = field(default_factory=list)
    
    def add_definition(self, definition: Definition):
        self.definitions.append(definition)
        if definition.kind == "def":
            self.def_count += 1
        elif definition.kind == "theorem":
            self.theorem_count += 1


@dataclass
class ChangeStats:
    """
    Statistics for a specific type of change (added, modified, or deleted)
    for a specific entity type (definition or theorem)
    """
    # Counts
    count: int = 0
    # Line counts
    total_lines: int = 0
    
    @property
    def avg_lines(self) -> float:
        """Average lines per change"""
        return self.total_lines / self.count if self.count > 0 else 0


@dataclass
class EntityChangeStats:
    """
    Statistics for changes to a specific entity type (definition or theorem)
    Tracks added, changed (modified), and deleted items
    """
    # Statistics for each change type
    added: ChangeStats = field(default_factory=ChangeStats)
    changed: ChangeStats = field(default_factory=ChangeStats)
    deleted: ChangeStats = field(default_factory=ChangeStats)
    
    @property
    def total_affected_count(self) -> int:
        """Total number of entities affected (added, changed, or deleted)"""
        return self.added.count + self.changed.count + self.deleted.count


@dataclass
class LeanFileDiffStats:
    """
    Comprehensive statistics about changes between original and modified Lean files
    
    Tracks:
    - Total counts in original and new (modified) files
    - Added, changed, and deleted items
    - Line counts for all change types
    - Average lines per change type
    """
    # Original file statistics
    original_def_count: int = 0
    original_theorem_count: int = 0
    
    # New file statistics (previously called "modified")
    new_total_def_count: int = 0
    new_total_theorem_count: int = 0
    
    # Change statistics for definitions and theorems
    definitions: EntityChangeStats = field(default_factory=EntityChangeStats)
    theorems: EntityChangeStats = field(default_factory=EntityChangeStats)
    
    def to_dict(self) -> Dict[str, float]:
        """Convert statistics to a dictionary for reporting"""
        return {
            # Original file counts
            "original_total_def_count": self.original_def_count,
            "original_total_theorem_count": self.original_theorem_count,
            
            # Modified file counts
            "new_total_def_count": self.new_total_def_count,
            "new_total_theorem_count": self.new_total_theorem_count,
            
            # Definition changes
            "added_def_count": self.definitions.added.count,
            "changed_def_count": self.definitions.changed.count,
            "deleted_def_count": self.definitions.deleted.count,
            "affected_def_count": self.definitions.total_affected_count,
            
            # Theorem changes
            "added_theorem_count": self.theorems.added.count,
            "changed_theorem_count": self.theorems.changed.count,
            "deleted_theorem_count": self.theorems.deleted.count,
            "affected_theorem_count": self.theorems.total_affected_count,
            
            # Definition line counts
            "added_def_line_count": self.definitions.added.total_lines,
            "changed_def_line_count": self.definitions.changed.total_lines,
            "deleted_def_line_count": self.definitions.deleted.total_lines,
            
            # Theorem line counts
            "added_theorem_line_count": self.theorems.added.total_lines,
            "changed_theorem_line_count": self.theorems.changed.total_lines,
            "deleted_theorem_line_count": self.theorems.deleted.total_lines,
            
            # Average lines per change
            "avg_added_def_line_count": self.definitions.added.avg_lines,
            "avg_changed_def_line_count": self.definitions.changed.avg_lines,
            "avg_deleted_def_line_count": self.definitions.deleted.avg_lines,
            
            "avg_added_theorem_line_count": self.theorems.added.avg_lines,
            "avg_changed_theorem_line_count": self.theorems.changed.avg_lines,
            "avg_deleted_theorem_line_count": self.theorems.deleted.avg_lines
        }


class Lean4Lexer:
    """Simplified Lean 4 lexical analyzer, focused on identifying definition types"""

    def __init__(self):
        # Definition type patterns - updated for clear categorization
        self.def_pattern = re.compile(
            r'\b(?:def|definition|class|inductive|coinductive|structure|abbrev)\b'
        )
        self.theorem_pattern = re.compile(
            r'\b(?:theorem|lemma|example)\b'
        )
        
        # Compile regex patterns
        self.patterns = [
            # Comments
            (TokenType.COMMENT, re.compile(r'--.*?(?:\n|$)|/-.*?-/', re.DOTALL)),
            
            # Strings
            (TokenType.STRING, re.compile(r'"(?:\\.|[^\\"])*"')),
            
            # Definition commands
            (TokenType.DEFINITION_COMMAND, re.compile(
                r'\b(?:def|definition|theorem|lemma|example|class|inductive|coinductive|structure|abbrev)\b'
            )),
            
            # Other keywords
            (TokenType.KEYWORD, re.compile(
                r'\b(?:namespace|section|end|import|open|export|variable|variables|where|by|do|let)\b'
            )),
            
            # Operators
            (TokenType.OPERATOR, re.compile(r':=|=|→|⟹|⟸|\+=|-=|\*=|/=|\.\.|≠|≤|≥|\+|\-|\*|/|%|\^|&|\||!|~')),
            
            # Punctuation
            (TokenType.PUNCTUATION, re.compile(r'[:\(\)\{\}\[\]<>⟨⟩.,;]')),
            
            # Identifiers
            (TokenType.IDENTIFIER, re.compile(r'[a-zA-Z_][a-zA-Z0-9_\']*')),
            
            # Whitespace
            (TokenType.WHITESPACE, re.compile(r'\s+')),
        ]

    def tokenize(self, text: str) -> List[Token]:
        """Convert Lean 4 code to a token sequence"""
        tokens = []
        line = 1
        column = 1
        pos = 0

        while pos < len(text):
            matched = False

            for token_type, pattern in self.patterns:
                match = pattern.match(text, pos)
                if match:
                    value = match.group(0)
                    tokens.append(Token(token_type, value, line, column, pos))
                    
                    # Update line and column numbers
                    newlines = value.count('\n')
                    if newlines > 0:
                        line += newlines
                        column = len(value) - value.rfind('\n')
                    else:
                        column += len(value)
                    
                    pos = match.end()
                    matched = True
                    break

            if not matched:
                # If no patterns match, add the character as UNKNOWN
                tokens.append(Token(TokenType.UNKNOWN, text[pos], line, column, pos))
                if text[pos] == '\n':
                    line += 1
                    column = 1
                else:
                    column += 1
                pos += 1

        # Add EOF token
        tokens.append(Token(TokenType.EOF, "", line, column, pos))
        return tokens
    
    def is_def_type(self, token_value: str) -> bool:
        """Check if token is a def type"""
        return bool(self.def_pattern.match(token_value))
    
    def is_theorem_type(self, token_value: str) -> bool:
        """Check if token is a theorem type"""
        return bool(self.theorem_pattern.match(token_value))


class LeanFileAnalyzer:
    """Lean file analyzer for counting definitions and analyzing diffs"""
    
    def __init__(self):
        self.lexer = Lean4Lexer()
    
    def _parse_file_content(self, content: str) -> FileStats:
        """
        Parse file content, extract all definitions and theorems
        
        Args:
            content: File content
            
        Returns:
            FileStats object containing all definitions and theorems
        """
        if not content:
            content = ""
        tokens = self.lexer.tokenize(content)
        file_stats = FileStats()
        lines = content.splitlines()
        
        pos = 0
        while pos < len(tokens):
            token = tokens[pos]
            
            if token.type == TokenType.DEFINITION_COMMAND:
                definition = self._parse_definition(tokens, pos, content, lines)
                if definition:
                    file_stats.add_definition(definition)
            
            pos += 1
        
        return file_stats
    
    def _parse_definition(self, tokens: List[Token], start_pos: int, content: str, lines: List[str]) -> Optional[Definition]:
        """
        Parse definition, extract name and range
        
        Args:
            tokens: Token list
            start_pos: Start position in token list
            content: Full file content
            lines: File content split by lines
            
        Returns:
            Definition object or None if parsing failed
        """
        if start_pos >= len(tokens):
            return None
        
        token = tokens[start_pos]
        def_type = token.value
        start_position = Position(token.line, token.column)
        
        # Determine definition type (def or theorem)
        if self.lexer.is_def_type(def_type):
            kind = "def"
        elif self.lexer.is_theorem_type(def_type):
            kind = "theorem"
        else:
            return None
        
        # Find definition name
        name = ""
        pos = start_pos + 1
        while pos < len(tokens):
            if tokens[pos].type == TokenType.WHITESPACE:
                pos += 1
                continue
            
            if tokens[pos].type == TokenType.IDENTIFIER:
                name = tokens[pos].value
                break
            
            pos += 1
        
        if not name:
            return None
        
        # Find definition end position
        end_pos, _, _ = self._find_definition_boundaries(tokens, start_pos, content)
        
        if end_pos >= len(tokens):
            end_pos = len(tokens) - 1
        
        end_position = Position(tokens[end_pos].line, tokens[end_pos].column)
        definition_range = Range(start_position, end_position)
        
        # Extract full definition content text
        def_content = ""
        if start_position.line <= end_position.line and start_position.line <= len(lines):
            if start_position.line == end_position.line:
                # Single-line definition
                line = lines[start_position.line - 1]  # Subtract 1 because list index starts at 0
                def_content = line[start_position.column - 1:end_position.column]
            else:
                # Multi-line definition
                # First line
                if start_position.line <= len(lines):
                    def_content += lines[start_position.line - 1][start_position.column - 1:] + "\n"
                
                # Middle lines
                for line_num in range(start_position.line + 1, end_position.line):
                    if line_num <= len(lines):
                        def_content += lines[line_num - 1] + "\n"
                
                # Last line
                if end_position.line <= len(lines):
                    def_content += lines[end_position.line - 1][:end_position.column]
        
        return Definition(
            kind=kind,
            type=def_type,
            name=name,
            range=definition_range,
            content=def_content
        )
    
    def _find_definition_boundaries(self, tokens: List[Token], start_pos: int, content: str) -> Tuple[int, int, int]:
        """
        Find definition end position
        
        Args:
            tokens: Token list
            start_pos: Start position in token list
            content: Full file content
            
        Returns:
            Tuple of (end_pos, proof_start_pos, proof_end_pos)
        """
        pos = start_pos + 1
        next_def_pos = len(tokens)
        proof_start_pos = -1
        proof_end_pos = -1
        
        # Find start position of next definition
        for i in range(start_pos + 1, len(tokens)):
            if tokens[i].type == TokenType.DEFINITION_COMMAND:
                next_def_pos = i
                break
        
        # Find proof part (for boundary detection, but not stored)
        bracket_stack = []
        for i in range(start_pos + 1, next_def_pos):
            token = tokens[i]
            
            # Detect proof start
            if (token.type == TokenType.OPERATOR and token.value == ":=") or \
               (token.type == TokenType.KEYWORD and token.value == "by"):
                if not bracket_stack:  # Ensure not inside brackets
                    proof_start_pos = i
                    break
            
            # Handle nested brackets
            if token.type == TokenType.PUNCTUATION:
                if token.value in "({[":
                    bracket_stack.append(token.value)
                elif token.value in ")}]" and bracket_stack:
                    # Check bracket matching
                    open_bracket = bracket_stack.pop()
                    if not ((open_bracket == "(" and token.value == ")") or 
                            (open_bracket == "{" and token.value == "}") or 
                            (open_bracket == "[" and token.value == "]")):
                        # Not matching, but continue processing
                        pass
        
        # If proof start found, find proof end
        if proof_start_pos > 0:
            # Reset bracket stack
            bracket_stack = []
            for i in range(proof_start_pos + 1, next_def_pos):
                token = tokens[i]
                
                if token.type == TokenType.PUNCTUATION:
                    if token.value in "({[":
                        bracket_stack.append(token.value)
                    elif token.value in ")}]" and bracket_stack:
                        bracket_stack.pop()
                
                # If found next definition or end keyword (outside nested brackets), proof ends
                if not bracket_stack and \
                   ((token.type == TokenType.DEFINITION_COMMAND) or 
                    (token.type == TokenType.KEYWORD and token.value == "end")):
                    proof_end_pos = i - 1  # End at previous position
                    break
            
            # If no clear end found, proof ends just before next definition
            if proof_end_pos == -1:
                proof_end_pos = next_def_pos - 1
        
        # Return definition end position (either proof end if exists, or just before next definition)
        end_pos = proof_end_pos if proof_end_pos > 0 else next_def_pos - 1
        
        return end_pos, proof_start_pos, proof_end_pos
    
    def _compute_line_differences(self, original_content: str, modified_content: str) -> Tuple[int, int]:
        """
        Compute lines added and deleted between original and modified content
        
        Args:
            original_content: Original content
            modified_content: Modified content
            
        Returns:
            Tuple of (lines_added, lines_deleted)
        """
        # Split content into lines
        original_lines = original_content.splitlines()
        modified_lines = modified_content.splitlines()
        
        # Use SequenceMatcher to find differences
        matcher = difflib.SequenceMatcher(None, original_lines, modified_lines)
        
        # Count added and deleted lines
        lines_added = 0
        lines_deleted = 0
        
        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            if op == 'replace':
                # Count replaced lines as both added and deleted
                lines_deleted += i2 - i1
                lines_added += j2 - j1
            elif op == 'delete':
                # Count deleted lines
                lines_deleted += i2 - i1
            elif op == 'insert':
                # Count inserted lines
                lines_added += j2 - j1
        
        return lines_added, lines_deleted
    
    def _compare_definitions(self, original_def: Definition, modified_def: Definition) -> Tuple[bool, int]:
        """
        Compare two definitions to find if modified and how many lines changed
        
        Args:
            original_def: Original definition
            modified_def: Modified definition
            
        Returns:
            Tuple of (is_modified, changed_lines)
        """
        # Compare content text to determine if modified
        if original_def.content == modified_def.content:
            return False, 0
        
        # If content differs, calculate number of changed lines
        original_lines = original_def.content.splitlines()
        modified_lines = modified_def.content.splitlines()
        
        matcher = difflib.SequenceMatcher(None, original_lines, modified_lines)
        changed_lines = 0
        
        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            if op != 'equal':
                # Count changed, added, or deleted lines
                changed_lines += max(i2 - i1, j2 - j1)
        
        return True, changed_lines

    def analyze_file_stats(self, original_content: str, modified_content: str) -> Dict[str, float]:
        """
        Analyze differences between original and modified file, calculate statistics
        
        Args:
            original_content: Original file content
            modified_content: Modified file content
            
        Returns:
            Dictionary of statistics
        """
        # Parse original and modified files
        original_stats = self._parse_file_content(original_content)
        modified_stats = self._parse_file_content(modified_content)
        
        # Create mapping from definition name to definition object for easier lookup
        original_defs_map = {d.name: d for d in original_stats.definitions}
        modified_defs_map = {d.name: d for d in modified_stats.definitions}
        
        # Initialize diff statistics
        diff_stats = LeanFileDiffStats(
            original_def_count=original_stats.def_count,
            original_theorem_count=original_stats.theorem_count,
            new_total_def_count=modified_stats.def_count,
            new_total_theorem_count=modified_stats.theorem_count
        )
        
        # Find modified and deleted definitions
        for name, original_def in original_defs_map.items():
            if name in modified_defs_map:
                # Definition exists in both files, check if modified
                modified_def = modified_defs_map[name]
                is_modified, changed_lines = self._compare_definitions(original_def, modified_def)
                
                if is_modified:
                    # Update statistics based on definition type
                    if original_def.kind == "def":
                        diff_stats.definitions.changed.count += 1
                        diff_stats.definitions.changed.total_lines += changed_lines
                    elif original_def.kind == "theorem":
                        diff_stats.theorems.changed.count += 1
                        diff_stats.theorems.changed.total_lines += changed_lines
            else:
                # Definition exists only in original file, it was deleted
                if original_def.kind == "def":
                    diff_stats.definitions.deleted.count += 1
                    diff_stats.definitions.deleted.total_lines += original_def.line_count
                elif original_def.kind == "theorem":
                    diff_stats.theorems.deleted.count += 1
                    diff_stats.theorems.deleted.total_lines += original_def.line_count
        
        # Find added definitions
        for name, modified_def in modified_defs_map.items():
            if name not in original_defs_map:
                # Definition exists only in modified file, it was added
                if modified_def.kind == "def":
                    diff_stats.definitions.added.count += 1
                    diff_stats.definitions.added.total_lines += modified_def.line_count
                elif modified_def.kind == "theorem":
                    diff_stats.theorems.added.count += 1
                    diff_stats.theorems.added.total_lines += modified_def.line_count
        
        # Return statistics dictionary
        return diff_stats.to_dict()


class TokenCounter:
    """Class for counting tokens in text"""
    
    def __init__(self):
        self.encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4o tokenizer
    
    def count_tokens(self, text: str) -> int:
        """Calculate token count in text using GPT-4o tokenizer"""
        if not text:
            return 0
        
        try:
            return len(self.encoding.encode(text))
        except Exception as e:
            logging.error(f"Error calculating tokens: {e}")
            return 0


class ParallelLeanAnalyzer:
    """Class for parallel processing of Lean file analysis"""
    
    def __init__(self, analyzer_class=None):
        """
        Initialize analyzer
        
        Args:
            analyzer_class: Class used for analyzing Lean files, if None then LeanFileAnalyzer is used
        """
        self.analyzer = analyzer_class() if analyzer_class else LeanFileAnalyzer()
        self.token_counter = TokenCounter()
        
    def _process_single_row(self, row_data: Tuple[int, pd.Series]) -> Optional[Tuple[int, Dict[str, Any]]]:
        """
        Process a single row of data
        
        Args:
            row_data: Tuple containing row index and row data
        
        Returns:
            Dictionary containing statistics, or None if processing failed
        """
        idx, row = row_data
        
        try:
            # Handle potential NaN values
            before_content = str(row['content_before']) if not pd.isna(row['content_before']) else ""
            after_content = str(row['content_after']) if not pd.isna(row['content_after']) else ""
            
            # Create new analyzer instance (avoid multiprocessing sharing issues)
            analyzer = LeanFileAnalyzer()
            
            # Analyze changes
            stats = analyzer.analyze_file_stats(before_content, after_content)
            
            return idx, stats
            
        except Exception as e:
            print(f"Error processing row {idx}: {str(e)}")
            return None
    
    def process_dataframe(self, df: pd.DataFrame) -> List[Tuple[int, Dict[str, Any]]]:
        """
        Process dataframe in parallel using multiprocessing
        
        Args:
            df: DataFrame containing content_before and content_after columns
        
        Returns:
            List containing analysis statistics
        """
        print("Starting parallel data processing...")
        
        # Determine CPU cores and set process pool size
        num_cores = mp.cpu_count()
        num_processes = max(1, min(num_cores - 1, 8))  # Use appropriate number of processes, at least 1, at most 8
        print(f"Using {num_processes} processes for parallel processing")
        
        # Prepare row data list
        row_data = list(df.iterrows())
        total_rows = len(row_data)
        
        # Create process pool
        with mp.Pool(processes=num_processes) as pool:
            # Use tqdm to show progress bar
            stats_list = list(tqdm(
                pool.imap(self._process_single_row, row_data),
                total=total_rows,
                desc="Processing progress"
            ))
            
        # Filter out None results (failed processing rows)
        stats_list = [item for item in stats_list if item is not None]
        
        # Convert to DataFrame
        if not stats_list:
            print("No valid data after processing")
            return []
        
        print(f"Data processing completed, processed {len(stats_list)} rows")
        return stats_list


def analyze_lean_files_parallel(df: pd.DataFrame, cache_path: Optional[str] = None) -> pd.DataFrame:
    """
    Analyze Lean file changes in parallel and add results to dataframe
    
    Args:
        df: DataFrame containing content_before and content_after columns
        cache_path: Optional cache file path for saving and loading analysis results
        
    Returns:
        DataFrame with added analysis result columns
    """
    # Create analyzer and process data
    analyzer = ParallelLeanAnalyzer()
    
    # Process token data
    token_counter = TokenCounter()
    
    # Calculate instruction tokens
    if 'full_instruction' in df.columns:
        df['instruction_tokens'] = df['full_instruction'].apply(
            lambda x: token_counter.count_tokens(x) if isinstance(x, str) else 0
        )
    else:
        df['instruction_tokens'] = 0
    
    # Calculate input tokens (context tokens)
    if 'content_before' in df.columns:
        df['input_tokens'] = df['content_before'].apply(
            lambda x: token_counter.count_tokens(x) if isinstance(x, str) else 0
        )
    else:
        df['input_tokens'] = 0
        
    # Extract second-level directory from file_path_after as a feature
    if 'file_path_after' in df.columns:
        df['module'] = df['file_path_after'].apply(
            lambda x: x.split('/')[1] if isinstance(x, str) and len(x.split('/')) > 1 else "other"
        )
    else:
        df['module'] = "other"
    
    # Process Lean file changes
    if cache_path and os.path.exists(cache_path):
        print(f"Loading analysis results from cache: {cache_path}")
        with open(cache_path, 'rb') as f:
            stats_list = pickle.load(f)
    else:
        stats_list = analyzer.process_dataframe(df)
        if cache_path:
            print(f"Saving analysis results to cache: {cache_path}")
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, 'wb') as f:
                pickle.dump(stats_list, f)
    
    # Convert results to dictionary and add to DataFrame
    stats_dict = {item[0]: item[1] for item in stats_list}
    stats_df = pd.DataFrame.from_dict(stats_dict, orient='index')
    
    # Check index matches and update df
    if not stats_df.empty:
        # Remove existing analysis result columns to avoid duplication
        stats_columns = stats_df.columns.tolist()
        existing_columns = [col for col in stats_columns if col in df.columns]
        if existing_columns:
            df = df.drop(columns=existing_columns)
        
        # Join DataFrames using index
        result_df = df.join(stats_df, how='left')
        
        print(f"Analysis complete, added {len(stats_df.columns)} new feature columns")
        return result_df
    else:
        print("No analysis results generated, returning original DataFrame")
        return df