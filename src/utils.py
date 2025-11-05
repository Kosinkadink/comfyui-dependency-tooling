"""
Shared utility functions for ComfyUI dependency analysis.
"""

import re
import csv
from pathlib import Path
from datetime import datetime


def make_filename_safe(query):
    """Convert a query string to a filename-safe version."""
    # Remove &save suffix if present
    query = query.replace('&save', '').strip()
    # Replace asterisks with 'wildcard'
    query = query.replace('*', 'wildcard')
    # Replace non-alphanumeric characters with underscores
    safe_name = re.sub(r'[^\w\-_]', '_', query)
    # Remove multiple underscores
    safe_name = re.sub(r'_+', '_', safe_name)
    # Trim underscores from ends
    return safe_name.strip('_')


def parse_dependency_string(dep_str):
    """
    Parse a dependency string and extract normalized information.

    Args:
        dep_str: Dependency string to parse

    Returns:
        Dictionary with keys:
            - is_comment: True if line is a full comment
            - is_pip_command: True if line is a pip command (starts with --)
            - is_git_dep: True if it's a git-based dependency
            - git_dep_type: Type of git dependency ('git+ prefix' or '@ git+ style')
            - base_name: Normalized base package name (lowercase)
            - cleaned_str: Dependency string with inline comments removed
            - original_str: Original dependency string
            - skip: True if this line should be skipped entirely
    """
    result = {
        'is_comment': False,
        'is_pip_command': False,
        'is_git_dep': False,
        'git_dep_type': None,
        'base_name': None,
        'cleaned_str': None,
        'original_str': dep_str,
        'skip': False
    }

    dep_str = str(dep_str).strip()

    # Check for full line comments
    if dep_str.startswith('#'):
        result['is_comment'] = True
        result['skip'] = True
        return result

    # Check for pip commands
    if dep_str.startswith('--'):
        result['is_pip_command'] = True
        result['cleaned_str'] = dep_str
        return result

    # Strip inline comments
    cleaned = dep_str
    if '#' in dep_str:
        cleaned = dep_str.split('#')[0].strip()

    # Skip if empty after stripping comments
    if not cleaned:
        result['skip'] = True
        return result

    result['cleaned_str'] = cleaned

    # Check for git-based dependencies
    # Type 1: Dependencies starting with git+
    if cleaned.startswith('git+'):
        result['is_git_dep'] = True
        result['git_dep_type'] = 'git+ prefix'
        result['base_name'] = cleaned  # Use full git URL as identifier
    # Type 2: Dependencies with @ git+ (e.g., package @ git+https://...)
    elif ' @ git+' in cleaned:
        result['is_git_dep'] = True
        result['git_dep_type'] = '@ git+ style'
        result['base_name'] = cleaned.split(' @ ')[0].strip().lower()
    else:
        # Regular dependency - extract base package name
        dep_lower = cleaned.lower()
        result['base_name'] = re.split(r'[<>=!~]', dep_lower)[0].strip()

    return result


def normalize_repository_url(repo_url):
    """
    Normalize a repository URL for comparison.

    Args:
        repo_url: Repository URL to normalize

    Returns:
        Normalized URL string (lowercase, no protocol, no .git)
    """
    if not repo_url or repo_url == 'N/A':
        return ''

    normalized = repo_url.lower().strip('/')
    normalized = normalized.replace('https://github.com/', '')
    normalized = normalized.replace('http://github.com/', '')
    normalized = normalized.replace('github.com/', '')  # Handle CSV format
    normalized = normalized.replace('.git', '')

    return normalized


def create_timestamped_filepath(query_desc, extension, directory='results'):
    """
    Create a timestamped filepath for saving results.

    Args:
        query_desc: Query description to use in filename
        extension: File extension (e.g., '.txt', '.html')
        directory: Directory to save in (default: 'results')

    Returns:
        Path object for the timestamped file
    """
    # Create directory if it doesn't exist
    results_dir = Path(directory)
    results_dir.mkdir(exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_query = make_filename_safe(query_desc)

    # Ensure extension starts with a dot
    if not extension.startswith('.'):
        extension = '.' + extension

    filename = f"{timestamp}_{safe_query}{extension}"
    filepath = results_dir / filename

    return filepath


def parse_python_files_csv(csv_file_path, file_extension='.py'):
    """
    Parse a CSV file containing Python file information by repository.
    Only tracks unique files per repository with the specified extension.

    Args:
        csv_file_path: Path to the CSV file
        file_extension: File extension to filter (default: '.py')

    Returns:
        Dictionary mapping repository URLs to set of unique file paths
    """
    file_map = {}

    try:
        with open(csv_file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header

            for row in reader:
                if len(row) >= 4:
                    repo_url = row[1]  # Column 2: Repository
                    file_path = row[3]  # Column 4: File path

                    # Only track files with specified extension
                    if file_path.endswith(file_extension):
                        if repo_url not in file_map:
                            file_map[repo_url] = set()
                        file_map[repo_url].add(file_path)
    except Exception as e:
        print(f"Warning: Could not parse CSV {csv_file_path}: {e}")

    return file_map


def load_csv_data_to_nodes(nodes_dict, csv_directory, node_key):
    """
    Generic function to load CSV data and map to nodes.

    Args:
        nodes_dict: Dictionary of nodes to update (modified in-place)
        csv_directory: Path to directory containing CSV files
        node_key: Key to store data in (e.g., '_web_directories', '_routes')

    Returns:
        Number of nodes updated with data
    """
    csv_path = Path(csv_directory)
    if not csv_path.exists():
        return 0

    # Find all CSV files
    csv_files = list(csv_path.glob('*.csv'))
    if not csv_files:
        return 0

    # Parse all CSV files and collect data
    all_data = {}
    for csv_file in csv_files:
        csv_data = parse_python_files_csv(csv_file)
        all_data.update(csv_data)

    # Map repository URLs to node IDs and add to nodes_dict
    count = 0

    for node_id, node_data in nodes_dict.items():
        repo = node_data.get('repository', '')
        if not repo or repo == 'N/A':
            continue

        # Normalize repository URL for matching
        repo_normalized = normalize_repository_url(repo)

        # Check if this repo has data
        for csv_repo, file_paths in all_data.items():
            csv_repo_normalized = normalize_repository_url(csv_repo)

            if csv_repo_normalized == repo_normalized:
                node_data[node_key] = sorted(list(file_paths))
                count += 1
                break

    return count
