# Copyright (2025) Bytedance Ltd. and/or its affiliates.
"""
MathLib4 Commits Analysis
A modular implementation for analyzing MathLib4 repository commits.
"""

import pandas as pd
import argparse
import os
import json
import pyarrow.parquet as pq
from ..data.utils import (
    display_data_info, 
    filter_by_token_limit, 
    get_commit_type,
    filter_by_edit_distance,
    get_repeating_modifications,
    plot_histogram
)
from ...utils.colors import colors
import matplotlib.pyplot as plt

def create_waterfall_chart(expansion_stages, filter_stages, save_path=None, format='html'):
    """
    Create a waterfall chart to visualize the expansion and filtering process.
    
    Args:
        expansion_stages: A list of dictionaries with keys for the expansion phase:
                      - 'name': The name of the expansion stage
                      - 'before': Count before the expansion
                      - 'after': Count after the expansion
                      - 'description': (Optional) Description of the expansion
        filter_stages: A list of dictionaries with keys for the filtering phase:
                      - 'name': The name of the filter stage
                      - 'before': Count before the filter
                      - 'after': Count after the filter
                      - 'description': (Optional) Description of the filter
        save_path: Path to save the generated chart
        format: Output format - 'html' or 'pdf'
    """
    import plotly.graph_objects as go
    
    # Prepare the data for the waterfall chart
    labels = ["Initial"]  # Start with the initial count
    values = [expansion_stages[0]['before']]  # The initial count
    measures = ["absolute"]  # The first value is absolute
    text = [f"{expansion_stages[0]['before']:,}"]  # Format the initial count
    
    # Add each expansion stage as an increase
    for stage in expansion_stages[1:]:
        increase = stage['after'] - stage['before']
        labels.append(f"{stage['name']} Expansion")
        values.append(increase)  # Positive for visual increase
        measures.append("relative")
        text.append(f"+{increase:,}")
    
    # Add each filter stage as a decrease
    for stage in filter_stages[1:]:  # Skip the initial stage of filtering
        decrease = stage['before'] - stage['after']
        if decrease > 0:  # Only add stages that filter out data
            labels.append(f"{stage['name']} Filter")
            values.append(-decrease)  # Negative for visual decrease
            measures.append("relative")
            text.append(f"-{decrease:,}")
    
    # Add the final remaining count
    labels.append("Remaining")
    values.append(filter_stages[-1]['after'])
    measures.append("total")
    text.append(f"{filter_stages[-1]['after']:,}")
    
    # Use high contrast colors to enhance visualization
    decreasing_color = colors['red_colors'][-1]  # Use bright red for decreases/filtering
    increasing_color = colors['green_colors'][-1]  # Use bright green for increases
    total_color = colors['blue_colors'][-2]  # Use deep blue for totals
    connector_color = colors['blue_colors'][-1]  # Use blue for connector lines
    
    # Create the waterfall chart
    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=measures,
        x=labels,
        y=values,
        text=text,
        textposition="outside",
        connector={"line": {"color": connector_color}},
        decreasing={"marker": {"color": decreasing_color}},
        increasing={"marker": {"color": increasing_color}},
        totals={"marker": {"color": total_color}}
    ))
    
    # Update the layout with clearer colors and background
    fig.update_layout(
        showlegend=False,
        width=1200,
        height=700,
        margin=dict(l=25, r=25, t=50, b=25),
        xaxis_title="Processing Stage",
        yaxis_title="Number of Data Items",
        plot_bgcolor='white',  # White background for better contrast
        paper_bgcolor='white',  # White chart background
        font=dict(size=14, color='black'),  # Larger font size with black color
    )
    
    # Save the figure if a save path is provided
    if save_path:
        if format.lower() == 'pdf':
            try:
                fig.write_image(save_path, scale=2)  # Scale=2 for better resolution
                print(f"Waterfall chart saved as PDF to {save_path}")
            except ImportError:
                print("Warning: Could not save as PDF. Please install the 'kaleido' package: pip install kaleido")
                # Fall back to HTML if kaleido is not available
                html_path = save_path.replace('.pdf', '.html')
                fig.write_html(html_path)
                print(f"Falling back to HTML: Waterfall chart saved to {html_path}")
        else:
            fig.write_html(save_path)
            print(f"Waterfall chart saved as HTML to {save_path}")
    
    return fig

def filter_mathlib_data(df, expansion_stats, min_changes=2, max_changes=50, min_edit_distance=10, scattered_threshold=1, 
                        max_scattered_count=10, max_scattered_ratio=0.1, repeat_threshold=0.5, 
                        max_more_removed_line_ratio=0.5, min_absolute_added_lines=5, **kwargs):
    print("\nFiltering data:")
    
    # Create lists to store the expansion and filter stages
    expansion_stages = []
    filter_stages = []
    
    # Process expansion stages from the stats
    initial_commits = expansion_stats['initial_commits']
    commit_parent_pairs = expansion_stats['commit_parent_pairs']
    file_changes = expansion_stats['file_changes']
    final_file_changes = expansion_stats['final_file_changes']
    
    # Track the expansion stages
    expansion_stages.append({
        'name': 'Initial',
        'before': initial_commits,
        'after': initial_commits,
        'description': 'Initial commits count'
    })
    
    expansion_stages.append({
        'name': 'Commit-Parent',
        'before': initial_commits,
        'after': commit_parent_pairs,
        'description': 'Expansion to commit-parent pairs'
    })
    
    expansion_stages.append({
        'name': 'File',
        'before': commit_parent_pairs,
        'after': file_changes,
        'description': 'Expansion to file changes'
    })
    
    expansion_stages.append({
        'name': 'Chunk',
        'before': file_changes,
        'after': final_file_changes,
        'description': 'Expansion to diff chunks'
    })
    
    # Start filtering from the final expanded data
    initial_size = len(df)
    print(f"Initial dataset size after expansion: {initial_size}")
    
    # Track the initial state for filtering
    filter_stages.append({
        'name': 'Initial',
        'before': initial_size,
        'after': initial_size,
        'description': 'Starting dataset after expansion'
    })
    
    # Filter by commit type
    df['type'] = df['message'].apply(get_commit_type)
    df = df[df['type'].notna()]
    type_filtered_size = len(df)
    
    # Track this filter stage
    filter_stages.append({
        'name': 'Type',
        'before': initial_size,
        'after': type_filtered_size,
        'description': 'Filter by commit type'
    })
    print(f"After filtering by commit type: {type_filtered_size} (removed {initial_size - type_filtered_size})")

    # Remove deleted files
    prev_size = type_filtered_size
    df = df[df['change_type'] != 'deleted']
    deleted_filtered_size = len(df)
    
    # Track this filter stage
    filter_stages.append({
        'name': 'Deleted',
        'before': prev_size,
        'after': deleted_filtered_size,
        'description': 'Remove deleted files'
    })
    print(f"After removing deleted files: {deleted_filtered_size} (removed {prev_size - deleted_filtered_size})")
    
    # Filter by file path pattern
    prev_size = deleted_filtered_size
    df = df[df.apply(
        lambda x: x['file_path_after'] != 'Mathlib.lean' and x['file_path_after'].startswith('Mathlib/') and x['file_path_after'].endswith('.lean'), 
        axis=1
    )]
    path_filtered_size = len(df)
    
    # Track this filter stage
    filter_stages.append({
        'name': 'Path',
        'before': prev_size,
        'after': path_filtered_size,
        'description': 'Filter by file path'
    })
    print(f"After filtering by file path: {path_filtered_size} (removed {prev_size - path_filtered_size})")

    # Keep only files with positive changes
    prev_size = path_filtered_size
    df = df[df.apply(
        lambda x: x['filtered_pure_changes'] > 0 and (
            x['filtered_absolute_added_lines'] > 0 or 
            (x['filtered_added_lines'] > min_absolute_added_lines and x['filtered_absolute_added_lines'] * max_more_removed_line_ratio + x['filtered_added_lines'] > 0)
            ),
        axis=1
    )]
    positive_filtered_size = len(df)
    
    # Track this filter stage
    filter_stages.append({
        'name': 'Positive',
        'before': prev_size,
        'after': positive_filtered_size,
        'description': 'Keep only positive changes'
    })
    print(f"After keeping only positive changes: {positive_filtered_size} (removed {prev_size - positive_filtered_size})")
    
    # Limit to changes between min_changes and max_changes
    prev_size = positive_filtered_size
    df = df[df['filtered_pure_changes'].between(min_changes, max_changes)]
    change_limit_filtered_size = len(df)
    
    # Track this filter stage
    filter_stages.append({
        'name': 'Change Limit',
        'before': prev_size,
        'after': change_limit_filtered_size,
        'description': f'Limit to changes between {min_changes} and {max_changes}'
    })
    print(f"After limiting to changes between {min_changes} and {max_changes}: {change_limit_filtered_size} (removed {prev_size - change_limit_filtered_size})")

    # Filter out repeating modifications
    prev_size = change_limit_filtered_size
    df = df[df['filtered_gold_diff'].apply(
        lambda x: get_repeating_modifications(x, repeat_threshold=repeat_threshold)
    )]
    repeat_filtered_size = len(df)
    
    # Track this filter stage
    filter_stages.append({
        'name': 'Repeat',
        'before': prev_size,
        'after': repeat_filtered_size,
        'description': 'Filter out repeating modifications'
    })
    print(f"After filtering out repeating modifications: {repeat_filtered_size} (removed {prev_size - repeat_filtered_size})")

    # Compute edit distance
    print("Computing edit distance...")
    prev_size = repeat_filtered_size
    df = filter_by_edit_distance(
        df,
        min_edit_distance=min_edit_distance,
        scattered_threshold=scattered_threshold,
        max_scattered_count=max_scattered_count,
        max_scattered_ratio=max_scattered_ratio
    )
    edit_distance_filtered_size = len(df)
    
    # Track this filter stage
    filter_stages.append({
        'name': 'Edit Distance',
        'before': prev_size,
        'after': edit_distance_filtered_size,
        'description': 'Filter by edit distance'
    })
    print(f"After filtering by edit distance: {edit_distance_filtered_size} (removed {prev_size - edit_distance_filtered_size})")
    
    return df, expansion_stages, filter_stages

def load_expansion_stats(file_path):
    """
    Load expansion statistics from a Parquet file or a companion JSON file.
    
    Args:
        file_path: Path to the Parquet file
        
    Returns:
        Dictionary of expansion statistics
    """
    # First try to get from metadata
    try:
        parquet_file = pq.ParquetFile(file_path)
        metadata = parquet_file.metadata
        if metadata and metadata.metadata:
            meta_bytes = metadata.metadata.get(b'expansion_stats')
            if meta_bytes:
                return json.loads(meta_bytes.decode('utf-8'))
    except Exception as e:
        print(f"Could not read expansion stats from Parquet metadata: {e}")
    
    # If not in metadata, try the companion JSON file
    json_path = file_path.replace('.parquet', '_expansion_stats.json')
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Could not read expansion stats from JSON file: {e}")
    
    # If no stats available, return default stats
    print("Warning: No expansion statistics found. Using default values.")
    return {
        'initial_commits': 1,
        'commit_parent_pairs': 1,
        'file_changes': 1,
        'final_file_changes': 1
    }

def filter_data(file_path, token_limit=16384, earliest_date=None, waterfall_chart_path=None, chart_format='html', **kwargs):
    # Load data
    print(f'Loading data {file_path}')
    df = pd.read_parquet(file_path)
    
    # Load expansion statistics
    expansion_stats = load_expansion_stats(file_path)
    print(f"Loaded expansion statistics: {expansion_stats}")
    
    # Display basic information
    display_data_info(df)
    
    # Filter data
    df, expansion_stages, filter_stages = filter_mathlib_data(df, expansion_stats, **kwargs)
    
    # Filter by token limit
    print("Processing unique content items...")
    prev_size = len(df)
    result_df = filter_by_token_limit(df, token_limit=token_limit)
    token_limit_filtered_size = len(result_df)
    
    # Track this filter stage
    filter_stages.append({
        'name': 'Token Limit',
        'before': prev_size,
        'after': token_limit_filtered_size,
        'description': f'Filter by token limit of {token_limit}'
    })
    print(f"After filtering by token limit: {token_limit_filtered_size} (removed {prev_size - token_limit_filtered_size})")

    result_df = result_df.sort_values('date', ascending=False, key=lambda x: pd.to_datetime(x, format='%Y-%m-%dT%H:%M:%S%z', utc=True))

    assert all(len(item['parent_commit_hash']) == 1 for _, item in result_df.iterrows())
    result_df['parent_commit_hash'] = result_df['parent_commit_hash'].apply(lambda x: x[0])

    if earliest_date:
        prev_size = len(result_df)
        result_df = result_df[result_df['date'] >= earliest_date]
        date_filtered_size = len(result_df)
        
        # Track this filter stage
        filter_stages.append({
            'name': 'Date',
            'before': prev_size,
            'after': date_filtered_size,
            'description': f'Filter by date >= {earliest_date}'
        })
        print(f"After filtering by {earliest_date}: {date_filtered_size} (removed {prev_size - date_filtered_size})")
    
    # Create and save the waterfall chart
    if waterfall_chart_path:
        create_waterfall_chart(expansion_stages, filter_stages, waterfall_chart_path, format=chart_format)
    
    return result_df, expansion_stages, filter_stages

def plot_histogram(values, title='Distribution', xlabel='Value', ylabel='Frequency', log_scale=False, save_path=None):
    """
    Plot a histogram of the provided values.
    
    Args:
        values: List of values to plot
        title: Title of the plot
        xlabel: X-axis label
        ylabel: Y-axis label
        log_scale: Whether to use log scale for y-axis
        save_path: Path to save the plot
    """
    plt.figure(figsize=(6, 4))
    
    # Using high contrast color scheme
    hist_color = colors['blue_colors'][1]  # Deep blue for histogram bars
    edge_color = colors['blue_colors'][3]  # Blue for edges
    bg_color = 'white'  # White background for contrast
    
    # Set background color
    plt.rcParams['figure.facecolor'] = bg_color
    plt.rcParams['axes.facecolor'] = bg_color
    
    # Plot histogram with clear edges
    plt.hist(values, bins=50, alpha=0.8, color=hist_color, edgecolor=edge_color, linewidth=0.8)
    
    # Add a subtle grid for better readability
    plt.grid(True, linestyle='--', alpha=0.3, color='#bbbbbb')
    
    # Mark the mean with bright red
    mean_value = sum(values) / len(values)
    plt.axvline(mean_value, color=colors['red_colors'][1], linestyle='dashed', linewidth=2, 
               label=f'Mean: {mean_value:.2f}')
    
    # Mark the median with bright green for contrast
    median_value = sorted(values)[len(values) // 2]
    plt.axvline(median_value, color=colors['green_colors'][3], linestyle='dotted', linewidth=2, 
               label=f'Median: {median_value:.2f}')
    
    # Add legend
    legend = plt.legend(loc='upper right', frameon=True, fancybox=True, framealpha=0.9, fontsize=12)
    legend.get_frame().set_facecolor('white')
    
    # Set title and labels with emphasis
    plt.title(title, fontsize=18)
    plt.xlabel(xlabel, fontsize=14)
    plt.ylabel(ylabel, fontsize=14)
    
    # Set tick label style
    plt.tick_params(axis='both', which='major', labelsize=12)
    
    # Set log scale if requested
    if log_scale:
        plt.yscale('log')
    
    # Use only bottom and left borders, remove top and right
    ax = plt.gca()
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_linewidth(1.5)
    ax.spines['left'].set_linewidth(1.5)
    
    # Tight layout for better spacing
    plt.tight_layout()
    
    # Save figure if path provided
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"Histogram saved to {save_path}")
    
    plt.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Filter MathLib4 data')
    parser.add_argument('--file_path', type=str, help='Path to the input data file')
    parser.add_argument('--repeat_threshold', type=float, default=0.8, help='Repeat threshold for filtering')
    parser.add_argument('--token_limit', type=int, default=16384, help='Token limit for filtering')
    parser.add_argument('--output_path', type=str, help='Path to the output data file')

    parser.add_argument('--min_changes', type=int, default=1, help='Minimum number of changes')
    parser.add_argument('--max_changes', type=int, default=100, help='Maximum number of changes')
    parser.add_argument('--min_edit_distance', type=int, default=10, help='Minimum edit distance for filtering')
    parser.add_argument('--scattered_threshold', type=int, default=1, help='Scattered threshold for filtering')
    parser.add_argument('--max_scattered_count', type=int, default=10, help='Maximum scattered count for filtering')
    parser.add_argument('--max_scattered_ratio', type=float, default=0.1, help='Maximum scattered ratio for filtering')
    parser.add_argument('--min_absolute_added_lines', type=int, default=5, help='Minimum absolute added lines for filtering')
    parser.add_argument('--max_more_removed_line_ratio', type=float, default=0.5, help='Maximum removed line ratio for filtering')
    parser.add_argument('--earliest_date', type=str, default='2023-08-01', help='Earliest date for filtering')

    parser.add_argument('--length_distribution_plot_path', default=None, help='Path to save the length distribution plot')
    parser.add_argument('--waterfall_chart_path', default=None, help='Path to save the waterfall chart')
    parser.add_argument('--chart_format', default='pdf', choices=['html', 'pdf'], help='Format for the waterfall chart (html or pdf)')
    
    args = parser.parse_args()
    
    # If no waterfall_chart_path is provided, use the output directory
    if args.waterfall_chart_path is None and args.output_path:
        output_dir = os.path.dirname(args.output_path)
        output_name = os.path.splitext(os.path.basename(args.output_path))[0]
        extension = '.pdf' if args.chart_format.lower() == 'pdf' else '.html'
        args.waterfall_chart_path = os.path.join(output_dir, f"{output_name}_waterfall{extension}")

    if args.length_distribution_plot_path is None and args.output_path:
        output_dir = os.path.dirname(args.output_path)
        output_name = os.path.splitext(os.path.basename(args.output_path))[0]
        args.length_distribution_plot_path = os.path.join(output_dir, f"{output_name}_length_distribution.png")
    
    filtered_df, expansion_stages, filter_stages = filter_data(**vars(args))
    
    # Save the filtered data
    filtered_df.to_parquet(args.output_path)
    
    print('Plotting length distribution to ', args.length_distribution_plot_path)
    plot_histogram([int(i) for i in filtered_df['filtered_pure_changes']], title='Distribution of Changes', xlabel='Number of Filtered Pure Changes', ylabel='Frequency', log_scale=False, save_path=args.length_distribution_plot_path)