"""
Shared utility functions for ComfyUI dependency analysis.
"""

import re
import csv
import json
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
    # Type 3: Dependencies with @ (without git+ prefix, e.g., package @ https://...)
    elif ' @ ' in cleaned:
        result['is_git_dep'] = True
        result['git_dep_type'] = '@ style'
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
    # Use a loop to merge sets from multiple CSV files for the same repo
    all_data = {}
    for csv_file in csv_files:
        csv_data = parse_python_files_csv(csv_file)
        for repo, files in csv_data.items():
            if repo in all_data:
                # Merge file sets if repo already exists
                all_data[repo].update(files)
            else:
                all_data[repo] = files

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


def load_all_node_stats(nodes_dict, stats_directory='node-stats'):
    """
    Auto-discover and load all node statistics from subdirectories.

    Each subdirectory in stats_directory represents a stat type (e.g., 'web-directories', 'routes').
    CSV files in each subdirectory are parsed and mapped to nodes.

    Args:
        nodes_dict: Dictionary of nodes to update (modified in-place)
        stats_directory: Base directory containing stat subdirectories

    Returns:
        Dictionary mapping stat names to number of nodes with that stat
    """
    stats_path = Path(stats_directory)

    # Initialize _stats dictionary for all nodes
    for node_data in nodes_dict.values():
        if '_stats' not in node_data:
            node_data['_stats'] = {}

    if not stats_path.exists():
        return {}

    # Discover all subdirectories (each is a stat type)
    stat_counts = {}
    stat_dirs = sorted([d for d in stats_path.iterdir() if d.is_dir()])

    for stat_dir in stat_dirs:
        stat_name = stat_dir.name

        # Find all CSV files in this stat directory
        csv_files = list(stat_dir.glob('*.csv'))
        if not csv_files:
            continue

        # Parse all CSV files and collect data
        all_data = {}
        for csv_file in csv_files:
            csv_data = parse_python_files_csv(csv_file)
            for repo, files in csv_data.items():
                if repo in all_data:
                    all_data[repo].update(files)
                else:
                    all_data[repo] = files

        # Map repository URLs to node IDs and add to nodes_dict
        count = 0
        for node_id, node_data in nodes_dict.items():
            repo = node_data.get('repository', '')
            if not repo or repo == 'N/A':
                continue

            repo_normalized = normalize_repository_url(repo)

            # Check if this repo has data for this stat
            for csv_repo, file_paths in all_data.items():
                csv_repo_normalized = normalize_repository_url(csv_repo)

                if csv_repo_normalized == repo_normalized:
                    node_data['_stats'][stat_name] = sorted(list(file_paths))
                    count += 1
                    break

        stat_counts[stat_name] = count

    return stat_counts


def get_node_stat_count(node_data, stat_name):
    """
    Get the count of files for a specific stat in a node.

    Args:
        node_data: Node data dictionary
        stat_name: Name of the stat to count

    Returns:
        Count of files for the stat (0 if stat not present)
    """
    stats = node_data.get('_stats', {})
    files = stats.get(stat_name, [])
    return len(files) if files else 0


def get_all_stat_names(nodes_dict):
    """
    Get all unique stat names that have been loaded across all nodes.

    Args:
        nodes_dict: Dictionary of all nodes

    Returns:
        Sorted list of stat names
    """
    stat_names = set()
    for node_data in nodes_dict.values():
        stats = node_data.get('_stats', {})
        stat_names.update(stats.keys())

    return sorted(stat_names)


def load_extension_node_map(nodes_dict, json_file_path='manager-files/extension-node-map.json'):
    """
    Load extension-node-map.json and map node IDs to node packs.
    Uses fuzzy matching to handle forks (matches by repo name if exact URL match fails).

    Args:
        nodes_dict: Dictionary of nodes to update (modified in-place)
        json_file_path: Path to the extension-node-map.json file

    Returns:
        Number of nodes updated with node ID data
    """
    json_path = Path(json_file_path)
    if not json_path.exists():
        return 0

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            extension_map = json.load(f)
    except Exception as e:
        print(f"Warning: Could not load {json_file_path}: {e}")
        return 0

    count = 0

    # Build a lookup for fuzzy matching by repository name
    repo_name_map = {}
    for map_repo, map_data in extension_map.items():
        map_repo_normalized = normalize_repository_url(map_repo)
        # Extract just the repo name (last part after /)
        if '/' in map_repo_normalized:
            repo_name = map_repo_normalized.split('/')[-1]
            if repo_name not in repo_name_map:
                repo_name_map[repo_name] = []
            repo_name_map[repo_name].append((map_repo, map_data))

    # Map repository URLs to node IDs
    for node_id, node_data in nodes_dict.items():
        repo = node_data.get('repository', '')
        if not repo or repo == 'N/A':
            continue

        # Normalize repository URL for matching
        repo_normalized = normalize_repository_url(repo)

        matched_data = None

        # Try exact match first
        for map_repo, map_data in extension_map.items():
            map_repo_normalized = normalize_repository_url(map_repo)

            if map_repo_normalized == repo_normalized:
                matched_data = map_data
                break

        # If no exact match, try fuzzy match by repo name (handles forks)
        if not matched_data and '/' in repo_normalized:
            repo_name = repo_normalized.split('/')[-1]
            if repo_name in repo_name_map:
                # Use the first matching repo with this name
                matched_data = repo_name_map[repo_name][0][1]

        # Extract and store node IDs if we found a match
        if matched_data:
            if isinstance(matched_data, list) and len(matched_data) > 0:
                node_ids = matched_data[0]
                if isinstance(node_ids, list):
                    node_data['_node_ids'] = node_ids

                    # Check if there's a nodename_pattern (indicates dynamic node matching)
                    if len(matched_data) > 1 and isinstance(matched_data[1], dict):
                        if 'nodename_pattern' in matched_data[1]:
                            node_data['_has_node_pattern'] = True
                            node_data['_nodename_pattern'] = matched_data[1]['nodename_pattern']

                    count += 1

    return count


def load_missing_nodes_csvs(csv_dir='missing-nodes'):
    """
    Load CSV files from the missing-nodes directory and extract node IDs.

    CSV format:
    - Column 1: content (quoted list of node IDs)
    - Column 2: metadata

    Args:
        csv_dir: Directory containing the CSV files

    Returns:
        List of node IDs found across all CSV files
    """
    import csv
    import ast

    csv_path = Path(csv_dir)
    if not csv_path.exists() or not csv_path.is_dir():
        return []

    all_node_ids = []

    # Find all CSV files in the directory
    csv_files = list(csv_path.glob('*.csv'))

    if not csv_files:
        return []

    for csv_file in csv_files:
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    content = row.get('content', '').strip()

                    if not content:
                        continue

                    # The content is a quoted list, so we need to parse it
                    # It might be a Python list literal like "['NodeA', 'NodeB']"
                    # or a JSON-style list like '["NodeA", "NodeB"]'
                    try:
                        # Try to evaluate it as a Python literal
                        node_list = ast.literal_eval(content)

                        if isinstance(node_list, list):
                            all_node_ids.extend(node_list)
                        elif isinstance(node_list, str):
                            # Single node ID
                            all_node_ids.append(node_list)
                    except (ValueError, SyntaxError):
                        # If that fails, try to parse it as a simple string
                        # Remove quotes and brackets if present
                        cleaned = content.strip('[]"\' ')
                        if cleaned:
                            all_node_ids.append(cleaned)

        except Exception as e:
            print(f"Warning: Could not load {csv_file}: {e}")
            continue

    return all_node_ids


def map_node_ids_to_packs(node_ids, nodes_dict):
    """
    Map node IDs to their corresponding node packs.
    Uses both direct matching and nodename_pattern matching.

    Args:
        node_ids: List of node IDs to map
        nodes_dict: Dictionary of node packs with _node_ids and _nodename_pattern data

    Returns:
        Dictionary mapping node_id -> node_pack_id
    """
    import re

    node_id_to_pack = {}

    # Build reverse lookup for fast direct matching
    pack_lookup = {}
    pattern_packs = []

    for pack_id, pack_data in nodes_dict.items():
        # Collect packs with explicit node ID lists
        if '_node_ids' in pack_data and pack_data['_node_ids']:
            for node_id in pack_data['_node_ids']:
                pack_lookup[node_id] = pack_id

        # Collect packs with nodename patterns for later matching
        if '_nodename_pattern' in pack_data:
            pattern_packs.append((pack_id, pack_data['_nodename_pattern']))

    # Map each node ID to a pack
    for node_id in node_ids:
        # Try direct lookup first
        if node_id in pack_lookup:
            node_id_to_pack[node_id] = pack_lookup[node_id]
        else:
            # Try pattern matching
            matched = False
            for pack_id, pattern in pattern_packs:
                try:
                    # The pattern might be a regex pattern
                    if re.search(pattern, node_id):
                        node_id_to_pack[node_id] = pack_id
                        matched = True
                        break
                except re.error:
                    # If regex fails, try simple string matching
                    if pattern in node_id or node_id in pattern:
                        node_id_to_pack[node_id] = pack_id
                        matched = True
                        break

            if not matched:
                # Store as unknown
                node_id_to_pack[node_id] = None

    return node_id_to_pack
