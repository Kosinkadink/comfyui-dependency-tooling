import json
import argparse
import re
import fnmatch
import os
import time
import requests
import csv
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# Import from src modules
from src.graph import create_cumulative_graph, create_downloads_graph, create_deps_graph, create_nodes_graph
from src.utils import (parse_dependency_string,
                       create_timestamped_filepath, load_csv_data_to_nodes,
                       load_extension_node_map)


import concurrent.futures
import threading

base_url = "https://api.comfy.org"

def get_registry_nodes_concurrent(print_time=True, max_workers=10):
    """
    Fetch all nodes from registry using concurrent requests for faster performance.

    Args:
        print_time: Whether to print the fetch time
        max_workers: Maximum number of concurrent threads

    Returns:
        Dictionary with 'nodes' key containing all nodes
    """
    nodes_dict = {}
    lock = threading.Lock()

    def fetch_page(page_num, retries=3):
        """Fetch a single page of nodes with retry logic."""
        sub_uri = f'{base_url}/nodes?page={page_num}&limit=30'

        for attempt in range(retries):
            try:
                response = requests.get(sub_uri, timeout=10)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.Timeout:
                if attempt < retries - 1:
                    print(f"Timeout on page {page_num}, attempt {attempt + 1}/{retries}, retrying...")
                    time.sleep(0.5 * (attempt + 1))  # Exponential backoff
                else:
                    print(f"Failed to fetch page {page_num} after {retries} attempts (timeout)")
                    return None
            except Exception as e:
                if attempt < retries - 1:
                    print(f"Error on page {page_num}, attempt {attempt + 1}/{retries}: {e}, retrying...")
                    time.sleep(0.5 * (attempt + 1))
                else:
                    print(f"Failed to fetch page {page_num} after {retries} attempts: {e}")
                    return None

        return None

    def process_page_results(json_obj):
        """Process the results from a page fetch."""
        if json_obj and 'nodes' in json_obj:
            with lock:
                for node in json_obj['nodes']:
                    if 'id' in node:  # Ensure node has an ID
                        nodes_dict[node['id']] = node
                    else:
                        print(f"Warning: Node without ID found: {node}")

    start_time = time.perf_counter()

    # First, fetch page 1 to get total pages
    print("Fetching first page to determine total pages...")
    first_page = fetch_page(1)
    if not first_page:
        print("Failed to fetch first page")
        return {'nodes': []}

    total_pages = first_page.get('totalPages', 1)
    print(f"Total pages to fetch: {total_pages}")

    # Process first page
    process_page_results(first_page)

    if total_pages > 1:
        # Fetch remaining pages concurrently
        print(f"Fetching remaining {total_pages - 1} pages concurrently with {max_workers} workers...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all page fetches
            future_to_page = {
                executor.submit(fetch_page, page): page
                for page in range(2, total_pages + 1)
            }

            # Process results as they complete
            completed = 0
            failed_pages = []
            for future in concurrent.futures.as_completed(future_to_page):
                page = future_to_page[future]
                try:
                    json_obj = future.result()
                    if json_obj:
                        process_page_results(json_obj)
                    else:
                        failed_pages.append(page)
                    completed += 1
                    if completed % 10 == 0:  # Progress update every 10 pages
                        print(f"  Processed {completed}/{total_pages - 1} pages...")
                except Exception as e:
                    print(f"Error processing page {page}: {e}")
                    failed_pages.append(page)

            if failed_pages:
                print(f"Warning: Failed to fetch {len(failed_pages)} pages: {failed_pages}")
                print("Attempting sequential retry for failed pages...")
                for page in failed_pages:
                    json_obj = fetch_page(page, retries=5)  # More retries for failed pages
                    if json_obj:
                        process_page_results(json_obj)
                        print(f"  Successfully recovered page {page}")
                    else:
                        print(f"  Could not recover page {page}")

    end_time = time.perf_counter()
    if print_time:
        print(f"Time taken to fetch all nodes (concurrent): {end_time - start_time:.2f} seconds")
        print(f"Total nodes fetched: {len(nodes_dict)}")

    # Add default latest_version for nodes without it
    for v in nodes_dict.values():
        if 'latest_version' not in v:
            v['latest_version'] = dict(version='nightly')

    return {'nodes': list(nodes_dict.values())}

def get_registry_nodes(print_time=True):
    # get all nodes from registry in a similar fashion as ComfyUI-Manager
    # this is a rare piece of code here that is not generated by Claude Code
    return get_registry_nodes_concurrent(print_time=print_time)
    
    nodes_dict = {}

    def fetch_all(print_time=False):
        remaining = True
        full_nodes = {}
        page = 1

        start_time = time.perf_counter()
        while remaining:
            sub_uri = f'{base_url}/nodes?page={page}&limit=4000'
            json_obj = requests.get(sub_uri).json()
            remaining = page < json_obj['totalPages']

            for x in json_obj['nodes']:
                full_nodes[x['id']] = x

            page += 1

        end_time = time.perf_counter()
        if print_time:
            print(f"Time taken to fetch all nodes: {end_time - start_time:.2f} seconds")

        return full_nodes

    nodes_dict = fetch_all(print_time=print_time)

    for v in nodes_dict.values():
        if 'latest_version' not in v:
            v['latest_version'] = dict(version='nightly')

    return {'nodes': list(nodes_dict.values())}



def save_nodes_json(registry_data, filepath='manager-files/nodes.json'):
    """
    Save registry data to nodes.json file.

    Args:
        registry_data: The data to save (should have 'nodes' key)
        filepath: Path to save the file to

    Returns:
        True if successful, False otherwise
    """
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # Save with indent=4 for readability
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(registry_data, f, indent=4)

        print(f"Successfully updated {filepath}")
        print(f"Total nodes saved: {len(registry_data['nodes'])}")
        return True
    except Exception as e:
        print(f"Error saving nodes.json: {e}")
        return False


def fetch_and_save_extension_node_map(filepath='manager-files/extension-node-map.json'):
    """
    Fetch extension-node-map.json from ComfyUI-Manager repository and save it.

    Args:
        filepath: Path to save the file to

    Returns:
        True if successful, False otherwise
    """
    url = "https://raw.githubusercontent.com/ltdrdata/ComfyUI-Manager/main/extension-node-map.json"

    try:
        print(f"Fetching extension-node-map.json from {url}...")
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        # Parse JSON to validate it
        node_map_data = response.json()

        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # Save with indent=4 for readability
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(node_map_data, f, indent=4)

        print(f"Successfully updated {filepath}")
        print(f"Total extensions mapped: {len(node_map_data)}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error fetching extension-node-map.json: {e}")
        return False
    except Exception as e:
        print(f"Error saving extension-node-map.json: {e}")
        return False


def load_nodes_to_dict(filepath='manager-files/nodes.json'):
    """
    Load nodes.json and convert to a dictionary with 'id' as keys.

    Args:
        filepath: Path to the nodes.json file

    Returns:
        Dictionary where keys are node IDs and values are the node data
    """
    nodes_dict = {}

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if 'nodes' in data:
            for node in data['nodes']:
                if 'id' in node:
                    node_id = node['id']
                    nodes_dict[node_id] = node
                else:
                    print(f"Warning: Node without 'id' field found and skipped")

        print(f"Successfully loaded {len(nodes_dict)} nodes")
        return nodes_dict

    except FileNotFoundError:
        print(f"Error: File '{filepath}' not found")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse JSON - {e}")
        return {}
    except Exception as e:
        print(f"Error: {e}")
        return {}


def compile_dependencies(nodes_dict):
    """
    Compile all dependencies from the latest version of each node.
    Groups all versions of the same package together for accurate statistics.
    Excludes commented dependencies (starting with #) and pip commands (starting with --).
    Tracks nodes that have commented deps or pip commands.

    Args:
        nodes_dict: Dictionary of nodes with IDs as keys

    Returns:
        Dictionary with dependency statistics and lists
    """
    all_dependencies_raw = []  # Keep raw versions for backward compatibility
    base_dependency_count = defaultdict(int)  # Count by base package name
    dependency_versions = defaultdict(set)  # Track all version specs per base package
    nodes_with_deps = []
    nodes_without_deps = []
    nodes_with_commented_deps = []
    nodes_with_pip_commands = []
    nodes_with_git_deps = []  # Track nodes with git-based dependencies
    commented_dependencies = []
    pip_commands = []
    pip_command_count = defaultdict(int)
    git_dependencies = []  # All git-based dependencies
    git_dependency_count = defaultdict(int)  # Count by type of git dep

    for node_id, node_data in nodes_dict.items():
        if 'latest_version' in node_data and node_data['latest_version']:
            latest_version = node_data['latest_version']

            if 'dependencies' in latest_version:
                deps = latest_version['dependencies']

                if deps and isinstance(deps, list) and len(deps) > 0:
                    active_deps = []
                    commented_deps = []
                    node_pip_commands = []
                    node_git_deps = []

                    for dep in deps:
                        parsed = parse_dependency_string(dep)

                        # Handle comments
                        if parsed['is_comment']:
                            commented_deps.append(parsed['original_str'])
                            commented_dependencies.append(parsed['original_str'])
                            continue

                        # Handle pip commands
                        if parsed['is_pip_command']:
                            node_pip_commands.append(parsed['cleaned_str'])
                            pip_commands.append(parsed['cleaned_str'])
                            pip_command_count[parsed['cleaned_str']] += 1
                            continue

                        # Skip empty lines
                        if parsed['skip']:
                            continue

                        # Handle git dependencies
                        if parsed['is_git_dep']:
                            node_git_deps.append(parsed['cleaned_str'])
                            git_dependencies.append(parsed['cleaned_str'])
                            git_dependency_count[parsed['git_dep_type']] += 1

                        # Add to active dependencies
                        active_deps.append(parsed['cleaned_str'])
                        all_dependencies_raw.append(parsed['cleaned_str'])

                        # Count by base name
                        base_name = parsed['base_name']
                        base_dependency_count[base_name] += 1

                        # Track the full version spec
                        dependency_versions[base_name].add(parsed['cleaned_str'])

                    if node_pip_commands:
                        nodes_with_pip_commands.append({
                            'id': node_id,
                            'name': node_data.get('name', 'N/A'),
                            'pip_commands': node_pip_commands,
                            'active_deps': active_deps
                        })

                    if commented_deps:
                        nodes_with_commented_deps.append({
                            'id': node_id,
                            'name': node_data.get('name', 'N/A'),
                            'commented_deps': commented_deps,
                            'active_deps': active_deps
                        })

                    if node_git_deps:
                        nodes_with_git_deps.append({
                            'id': node_id,
                            'name': node_data.get('name', 'N/A'),
                            'git_deps': node_git_deps,
                            'active_deps': active_deps
                        })

                    if active_deps:
                        nodes_with_deps.append({
                            'id': node_id,
                            'name': node_data.get('name', 'N/A'),
                            'dependencies': active_deps
                        })
                    else:
                        # Node has only commented dependencies
                        nodes_without_deps.append(node_id)
                else:
                    nodes_without_deps.append(node_id)
            else:
                nodes_without_deps.append(node_id)
        else:
            nodes_without_deps.append(node_id)

    # Create sorted list by base package frequency
    sorted_base_dependencies = sorted(base_dependency_count.items(), key=lambda x: x[1], reverse=True)

    # Get unique base package names
    unique_base_dependencies = list(base_dependency_count.keys())

    # Keep raw unique dependencies for backward compatibility
    unique_dependencies_raw = list(set(all_dependencies_raw))
    unique_commented = list(set(commented_dependencies))

    # Sort pip commands by frequency
    sorted_pip_commands = sorted(pip_command_count.items(), key=lambda x: x[1], reverse=True)
    unique_pip_commands = list(pip_command_count.keys())

    # Process git dependencies
    unique_git_dependencies = list(set(git_dependencies))
    sorted_git_dependency_types = sorted(git_dependency_count.items(), key=lambda x: x[1], reverse=True)

    return {
        'all_dependencies': all_dependencies_raw,
        'unique_dependencies': unique_dependencies_raw,  # Raw unique deps for compatibility
        'dependency_count': base_dependency_count,  # Now counts by base package name
        'sorted_by_frequency': sorted_base_dependencies,  # Sorted by base package frequency
        'dependency_versions': dict(dependency_versions),  # All version specs per package
        'unique_base_dependencies': unique_base_dependencies,  # Unique base package names
        'nodes_with_dependencies': nodes_with_deps,
        'nodes_without_dependencies': nodes_without_deps,
        'nodes_with_commented_dependencies': nodes_with_commented_deps,
        'nodes_with_pip_commands': nodes_with_pip_commands,
        'nodes_with_git_dependencies': nodes_with_git_deps,  # Nodes with git-based deps
        'commented_dependencies': commented_dependencies,
        'unique_commented_dependencies': unique_commented,
        'pip_commands': pip_commands,
        'unique_pip_commands': unique_pip_commands,
        'pip_command_count': dict(pip_command_count),
        'sorted_pip_commands': sorted_pip_commands,
        'git_dependencies': git_dependencies,  # All git-based dependencies
        'unique_git_dependencies': unique_git_dependencies,  # Unique git deps
        'git_dependency_count': dict(git_dependency_count),  # Count by type
        'sorted_git_dependency_types': sorted_git_dependency_types,  # Sorted by count
        'total_dependencies': len(all_dependencies_raw),
        'unique_count': len(unique_base_dependencies),  # Count of unique base packages
        'unique_raw_count': len(unique_dependencies_raw),  # Count of unique raw specs
        'nodes_with_deps_count': len(nodes_with_deps),
        'nodes_without_deps_count': len(nodes_without_deps),
        'nodes_with_commented_count': len(nodes_with_commented_deps),
        'nodes_with_pip_commands_count': len(nodes_with_pip_commands),
        'nodes_with_git_deps_count': len(nodes_with_git_deps)  # Count of nodes with git deps
    }


def analyze_wildcard_dependencies(nodes_dict, pattern):
    """
    Analyze multiple dependencies matching a wildcard pattern.

    Args:
        nodes_dict: Dictionary of nodes
        pattern: Wildcard pattern (e.g., "torch*")

    Returns:
        Dictionary with info about all matching dependencies
    """
    pattern_lower = pattern.lower()
    matching_deps = {}

    # First, collect all unique base dependencies
    all_base_deps = set()
    for node_id, node_data in nodes_dict.items():
        if 'latest_version' in node_data and node_data['latest_version']:
            latest_version = node_data['latest_version']
            if 'dependencies' in latest_version and latest_version['dependencies']:
                for dep in latest_version['dependencies']:
                    parsed = parse_dependency_string(dep)

                    # Skip comments, pip commands, and empty lines
                    if parsed['skip'] or parsed['is_pip_command']:
                        continue

                    if parsed['base_name']:
                        all_base_deps.add(parsed['base_name'])

    # Find dependencies matching the pattern
    for base_dep in all_base_deps:
        if fnmatch.fnmatch(base_dep, pattern_lower):
            # Analyze each matching dependency
            dep_info = analyze_specific_dependency(nodes_dict, base_dep)
            matching_deps[base_dep] = dep_info

    return matching_deps


def calculate_node_ranks(nodes_dict):
    """
    Calculate download ranks for all nodes.

    Args:
        nodes_dict: Dictionary of nodes

    Returns:
        Dictionary mapping node_id to rank (1-based)
    """
    # Sort all nodes by downloads
    sorted_nodes = sorted(nodes_dict.items(), key=lambda x: x[1].get('downloads', 0), reverse=True)

    # Create rank mapping
    rank_map = {}
    for rank, (node_id, _) in enumerate(sorted_nodes, 1):
        rank_map[node_id] = rank

    return rank_map


def analyze_specific_dependency(nodes_dict, dep_name):
    """
    Analyze a specific dependency across all nodes.
    Excludes commented dependencies but notes if the dependency appears commented.

    Args:
        nodes_dict: Dictionary of nodes
        dep_name: Name of dependency to analyze

    Returns:
        Dictionary with detailed info about the dependency
    """
    dep_name_lower = dep_name.lower()
    nodes_using = []
    all_versions = []
    version_count = defaultdict(int)
    nodes_with_commented = []

    # Calculate ranks for all nodes
    rank_map = calculate_node_ranks(nodes_dict)

    for node_id, node_data in nodes_dict.items():
        if 'latest_version' in node_data and node_data['latest_version']:
            latest_version = node_data['latest_version']

            if 'dependencies' in latest_version and latest_version['dependencies']:
                for dep in latest_version['dependencies']:
                    parsed = parse_dependency_string(dep)

                    # Check if commented line mentions our dependency
                    if parsed['is_comment']:
                        commented_content = parsed['original_str'][1:].strip()
                        parsed_comment = parse_dependency_string(commented_content)
                        if parsed_comment['base_name'] == dep_name_lower:
                            nodes_with_commented.append({
                                'node_id': node_id,
                                'node_name': node_data.get('name', 'N/A'),
                                'commented_spec': parsed['original_str']
                            })
                        continue

                    # Skip pip commands and empty lines
                    if parsed['skip'] or parsed['is_pip_command']:
                        continue

                    base_name = parsed['base_name']
                    if base_name == dep_name_lower:
                        # Extract additional node information
                        latest_version_info = node_data.get('latest_version', {})
                        latest_version_date = 'N/A'
                        if latest_version_info and 'createdAt' in latest_version_info:
                            # Parse and format the date
                            date_str = latest_version_info['createdAt']
                            try:
                                # Extract just the date portion (YYYY-MM-DD)
                                latest_version_date = date_str[:10] if date_str else 'N/A'
                            except:
                                latest_version_date = 'N/A'

                        dep_spec = parsed['cleaned_str']
                        nodes_using.append({
                            'node_id': node_id,
                            'node_name': node_data.get('name', 'N/A'),
                            'repository': node_data.get('repository', 'N/A'),
                            'dependency_spec': dep_spec,
                            'stars': node_data.get('github_stars', 0),
                            'downloads': node_data.get('downloads', 0),
                            'rank': rank_map.get(node_id, 0),
                            'latest_version_date': latest_version_date
                        })

                        # Extract version if present
                        version_match = re.search(r'[<>=!~]+(.+)', dep_spec)
                        if version_match:
                            version_spec = dep_spec[len(base_name):].strip()
                            all_versions.append(version_spec)
                            version_count[version_spec] += 1
                        else:
                            all_versions.append('*')
                            version_count['*'] += 1

    return {
        'dependency_name': dep_name,
        'nodes_using': nodes_using,
        'total_nodes': len(nodes_using),
        'all_versions': all_versions,
        'unique_versions': list(set(all_versions)),
        'version_count': dict(version_count),
        'sorted_versions': sorted(version_count.items(), key=lambda x: x[1], reverse=True),
        'nodes_with_commented': nodes_with_commented,
        'commented_count': len(nodes_with_commented)
    }


def save_results_to_file(query, results_text):
    """Save search results to a timestamped file in the results directory."""
    filepath = create_timestamped_filepath(query, '.txt')

    # Write results to file
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"Query: {query}\n")
            f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*60 + "\n\n")
            f.write(results_text)
        print(f"\n[Results saved to: {filepath}]")
        return True
    except Exception as e:
        print(f"\n[Error saving results: {e}]")
        return False


def format_dependency_details(result, show_all_nodes=False):
    """Format detailed dependency information for display and saving."""
    lines = []
    lines.append(f"\n{'='*50}")
    lines.append(f"Dependency: {result['dependency_name']}")
    lines.append(f"{'='*50}")
    lines.append(f"Total nodes using this dependency: {result['total_nodes']}")

    if result['commented_count'] > 0:
        lines.append(f"Nodes with commented-out lines: {result['commented_count']}")

    if result['total_nodes'] > 0:
        lines.append(f"\nVersion specifications found:")
        for version, count in result['sorted_versions']:
            lines.append(f"  {version:20} - {count} nodes")

        # Sort nodes by downloads (most popular first)
        sorted_nodes = sorted(result['nodes_using'],
                            key=lambda x: x.get('downloads', 0),
                            reverse=True)

        # Show all nodes if requested, otherwise limit to 10
        nodes_to_show = sorted_nodes if show_all_nodes else sorted_nodes[:10]

        lines.append(f"\nNodes using {result['dependency_name']} ({'all' if show_all_nodes else 'showing first 10 by popularity'}):")
        for i, node in enumerate(nodes_to_show, 1):
            lines.append(f"\n  {i}. {node['node_name']} ({node['node_id']})")
            lines.append(f"     Rank: #{node.get('rank', 'N/A')} | Downloads: {node.get('downloads', 0):,} | Stars: {node.get('stars', 0):,} | Latest: {node.get('latest_version_date', 'N/A')}")
            lines.append(f"     Spec: {node['dependency_spec']}")
            lines.append(f"     Repo: {node['repository']}")

        if not show_all_nodes and result['total_nodes'] > 10:
            lines.append(f"\n  ... and {result['total_nodes'] - 10} more nodes")

    if result['commented_count'] > 0:
        lines.append(f"\n\nNodes with commented-out {result['dependency_name']} lines:")
        for i, node in enumerate(result['nodes_with_commented'], 1):
            lines.append(f"  {i}. {node['node_name']} ({node['node_id']})")
            lines.append(f"     Commented line: {node['commented_spec']}")

    return '\n'.join(lines)


def get_raw_file_url(repo_url, filename='requirements.txt'):
    """
    Convert a GitHub repository URL to a raw file URL.

    Args:
        repo_url: Repository URL (e.g., https://github.com/user/repo)
        filename: Name of the file to fetch (default: requirements.txt)

    Returns:
        List of raw file URLs to try, or None if URL format is not recognized
    """
    if not repo_url or repo_url == 'N/A':
        return None

    # Remove trailing slash and .git
    repo_url = repo_url.rstrip('/').rstrip('.git')

    # Handle GitHub URLs
    if 'github.com' in repo_url:
        # Convert https://github.com/user/repo to https://raw.githubusercontent.com/user/repo/main/requirements.txt
        parts = repo_url.replace('https://github.com/', '').replace('http://github.com/', '')
        # Try main branch first, then master
        return [
            f"https://raw.githubusercontent.com/{parts}/main/{filename}",
            f"https://raw.githubusercontent.com/{parts}/master/{filename}"
        ]

    return None


def fetch_requirements_txt(repo_url, timeout=10):
    """
    Fetch requirements.txt content from a repository.

    Args:
        repo_url: Repository URL
        timeout: Request timeout in seconds

    Returns:
        Tuple of (success, content, error_message)
    """
    raw_urls = get_raw_file_url(repo_url)

    if not raw_urls:
        return (False, None, "Unsupported repository host")

    # Try each URL (main and master branches)
    for raw_url in raw_urls:
        try:
            response = requests.get(raw_url, timeout=timeout)
            if response.status_code == 200:
                return (True, response.text, None)
        except requests.exceptions.Timeout:
            continue
        except requests.exceptions.RequestException as e:
            continue

    return (False, None, "requirements.txt not found")


def parse_requirements_txt(content):
    """
    Parse requirements.txt content into a list of dependencies.

    Args:
        content: Content of requirements.txt file

    Returns:
        List of dependency strings
    """
    if not content:
        return []

    dependencies = []
    for line in content.split('\n'):
        line = line.strip()

        # Skip empty lines and comments
        if not line or line.startswith('#'):
            continue

        # Skip editable installs (-e)
        if line.startswith('-e '):
            continue

        # Include pip commands (--extra-index-url, etc.)
        # Include all other dependencies
        dependencies.append(line)

    return dependencies


def save_requirements_cache(node_id, content):
    """
    Save requirements.txt content to cache directory.

    Args:
        node_id: ID of the node
        content: Requirements.txt content to save

    Returns:
        True if successful, False otherwise
    """
    try:
        cache_dir = Path('updated_reqs') / node_id
        cache_dir.mkdir(parents=True, exist_ok=True)

        cache_file = cache_dir / 'requirements.txt'
        with open(cache_file, 'w', encoding='utf-8') as f:
            f.write(content)

        return True
    except Exception as e:
        print(f"Warning: Could not cache requirements for {node_id}: {e}")
        return False


def load_requirements_cache(node_id):
    """
    Load cached requirements.txt content.

    Args:
        node_id: ID of the node

    Returns:
        Tuple of (success, content)
    """
    try:
        cache_file = Path('updated_reqs') / node_id / 'requirements.txt'
        if cache_file.exists():
            with open(cache_file, 'r', encoding='utf-8') as f:
                content = f.read()
            return (True, content)
    except Exception as e:
        pass

    return (False, None)


def delete_requirements_cache(node_id):
    """
    Delete cached requirements.txt for a node.

    Args:
        node_id: ID of the node

    Returns:
        True if deleted, False otherwise
    """
    try:
        cache_file = Path('updated_reqs') / node_id / 'requirements.txt'
        if cache_file.exists():
            cache_file.unlink()
            # Try to remove the directory if it's now empty
            try:
                cache_file.parent.rmdir()
            except:
                pass  # Directory not empty or other error
            return True
    except Exception as e:
        pass

    return False


# parse_web_directory_csv has been replaced by parse_python_files_csv in src/utils.py


def load_web_directory_data(nodes_dict):
    """
    Load web directory data from CSV files in web-directories folder.
    Maps repository URLs to node IDs and adds web directory info directly to nodes_dict.

    Args:
        nodes_dict: Dictionary of all nodes (modified in place)

    Returns:
        Number of nodes with web directory data
    """
    return load_csv_data_to_nodes(nodes_dict, 'web-directories', '_web_directories')


# parse_routes_csv has been replaced by parse_python_files_csv in src/utils.py


def load_routes_data(nodes_dict):
    """
    Load routes data from CSV files in route-any folder.
    Maps repository URLs to node IDs and adds routes info directly to nodes_dict.

    Args:
        nodes_dict: Dictionary of all nodes (modified in place)

    Returns:
        Number of nodes with routes data
    """
    return load_csv_data_to_nodes(nodes_dict, 'route-any', '_routes')


def load_pip_nonos_data(nodes_dict):
    """
    Load pip direct call data from CSV files in pip-nonos folder.
    Maps repository URLs to node IDs and adds pip call info directly to nodes_dict.

    Args:
        nodes_dict: Dictionary of all nodes (modified in place)

    Returns:
        Number of nodes with pip-nonos data
    """
    return load_csv_data_to_nodes(nodes_dict, 'pip-nonos', '_pip_nonos')


def load_node_ids_data(nodes_dict):
    """
    Load node IDs from extension-node-map.json in manager-files folder.
    Maps repository URLs to node IDs and adds node ID list to nodes_dict.

    Args:
        nodes_dict: Dictionary of all nodes (modified in place)

    Returns:
        Number of nodes with node ID data
    """
    return load_extension_node_map(nodes_dict)


def load_all_cached_requirements(nodes_dict, original_deps_backup):
    """
    Load all cached requirements.txt files on startup.

    Args:
        nodes_dict: Dictionary of nodes (will be modified in-place)
        original_deps_backup: Dictionary to store original dependencies

    Returns:
        Number of nodes updated from cache
    """
    cache_dir = Path('updated_reqs')
    if not cache_dir.exists():
        return 0

    count = 0
    for node_dir in cache_dir.iterdir():
        if node_dir.is_dir():
            node_id = node_dir.name
            if node_id in nodes_dict:
                success, content = load_requirements_cache(node_id)
                if success:
                    # Parse and update dependencies
                    new_deps = parse_requirements_txt(content)

                    # Backup original if not already backed up
                    if node_id not in original_deps_backup:
                        node_data = nodes_dict[node_id]
                        if 'latest_version' in node_data and node_data['latest_version']:
                            original_deps_backup[node_id] = {
                                'dependencies': node_data['latest_version'].get('dependencies', []).copy() if node_data['latest_version'].get('dependencies') else []
                            }

                    # Update dependencies
                    node_data = nodes_dict[node_id]
                    if 'latest_version' in node_data and node_data['latest_version']:
                        node_data['latest_version']['dependencies'] = new_deps
                        node_data['latest_version']['_updated_from_requirements'] = True
                        count += 1

    return count


def fetch_single_node_requirements(node_id, repo):
    """
    Fetch requirements.txt for a single node.

    Args:
        node_id: ID of the node
        repo: Repository URL

    Returns:
        Tuple of (node_id, success, content, error)
    """
    success, content, error = fetch_requirements_txt(repo)
    return (node_id, success, content, error)


def update_node_requirements(nodes_dict, node_ids, original_deps_backup, max_workers=20):
    """
    Fetch and update node dependencies from requirements.txt files concurrently.

    Args:
        nodes_dict: Dictionary of nodes (will be modified in-place)
        node_ids: List of node IDs to update
        original_deps_backup: Dictionary to store original dependencies
        max_workers: Maximum number of concurrent threads (default: 20)

    Returns:
        Dictionary with update statistics
    """
    stats = {
        'total': len(node_ids),
        'success': 0,
        'failed': 0,
        'unsupported': 0,
        'updated_nodes': []
    }

    # Thread-safe lock for printing and stats updates
    print_lock = threading.Lock()

    # Capture original dependencies BEFORE fetching (since we update in-place)
    original_json_deps = {}
    for node_id in node_ids:
        if node_id in nodes_dict:
            node_data = nodes_dict[node_id]
            if 'latest_version' in node_data and node_data['latest_version']:
                deps = node_data['latest_version'].get('dependencies', []) or []
                original_json_deps[node_id] = deps.copy() if deps else []
            else:
                original_json_deps[node_id] = []

    # Prepare fetch tasks
    fetch_tasks = []
    for node_id in node_ids:
        if node_id not in nodes_dict:
            with print_lock:
                stats['failed'] += 1
            continue

        node_data = nodes_dict[node_id]
        repo = node_data.get('repository', 'N/A')
        fetch_tasks.append((node_id, repo))

    # Fetch concurrently
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_node = {
            executor.submit(fetch_single_node_requirements, node_id, repo): node_id
            for node_id, repo in fetch_tasks
        }

        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_node):
            node_id, success, content, error = future.result()
            completed += 1

            with print_lock:
                print(f"[{completed}/{stats['total']}] {node_id}...", end=' ')

                # Get original dependencies from captured snapshot (before any updates)
                original_deps = original_json_deps.get(node_id, [])
                node_data = nodes_dict[node_id]

                if success or error == "requirements.txt not found":
                    # Parse dependencies (empty list if no file)
                    if success:
                        new_deps = parse_requirements_txt(content)
                        # Save to cache for next startup
                        save_requirements_cache(node_id, content)
                    else:
                        # No requirements.txt found - that's OK, means no dependencies
                        new_deps = []
                        # Delete stale cache if it exists
                        delete_requirements_cache(node_id)

                    # Backup original dependencies if not already backed up
                    # Use the captured snapshot, not current node_data (which may be updated)
                    if node_id not in original_deps_backup:
                        original_deps_backup[node_id] = {
                            'dependencies': original_deps.copy() if original_deps else []
                        }

                    # Update the node's dependencies in-place
                    if 'latest_version' in node_data and node_data['latest_version']:
                        node_data['latest_version']['dependencies'] = new_deps
                        node_data['latest_version']['_updated_from_requirements'] = True

                    stats['success'] += 1
                    stats['updated_nodes'].append(node_id)

                    # Compare with original to show if they match
                    if set(original_deps) == set(new_deps):
                        print(f"OK ({len(new_deps)} deps) [matches JSON]")
                    else:
                        if len(original_deps) == 0 and len(new_deps) == 0:
                            print(f"OK ({len(new_deps)} deps) [matches JSON]")
                        elif len(original_deps) == 0:
                            print(f"OK ({len(new_deps)} deps) [JSON had none]")
                        elif len(new_deps) == 0:
                            print(f"OK ({len(new_deps)} deps) [JSON had {len(original_deps)}]")
                        else:
                            print(f"OK ({len(new_deps)} deps) [differs from JSON: {len(original_deps)}]")
                else:
                    # Actual errors (network issues, unsupported hosts, etc.)
                    if error == "Unsupported repository host":
                        stats['unsupported'] += 1
                        print(f"SKIP {error}")
                    else:
                        print(f"FAIL {error}")
                    stats['failed'] += 1

    return stats


def display_node_dependencies(nodes_dict, node_id, original_deps_backup=None):
    """
    Display detailed dependency information for a specific node.

    Args:
        nodes_dict: Dictionary of all nodes
        node_id: ID of the node to display
        original_deps_backup: Dictionary with original dependencies (if updated)
    """
    node_data = nodes_dict[node_id]

    # Calculate rank
    rank_map = calculate_node_ranks(nodes_dict)
    rank = rank_map.get(node_id, 'N/A')

    # Extract node information
    name = node_data.get('name', 'N/A')
    downloads = node_data.get('downloads', 0)
    stars = node_data.get('github_stars', 0)
    repo = node_data.get('repository', 'N/A')
    description = node_data.get('description', 'N/A')

    # Print header
    print(f"\n{'='*60}")
    print(f"Node: {name}")
    print(f"{'='*60}")
    print(f"ID: {node_id}")
    print(f"Rank: #{rank} | Downloads: {downloads:,} | Stars: {stars:,}")
    print(f"Repository: {repo}")
    print(f"Description: {description}")

    # Display number of individual nodes if available
    node_ids = node_data.get('_node_ids', [])
    has_pattern = node_data.get('_has_node_pattern', False)

    # Show node count if we have node IDs or a pattern
    if node_ids or has_pattern:
        asterisk = '*' if has_pattern else ''
        node_count = len(node_ids) if node_ids else 0
        # If pattern exists but no explicit nodes, show just the asterisk
        if has_pattern and node_count == 0:
            print(f"Individual Nodes: * (pattern-based)")
        else:
            print(f"Individual Nodes: {node_count}{asterisk}")

    # Get latest version info
    latest_version_info = node_data.get('latest_version', {})
    if latest_version_info:
        version = latest_version_info.get('version', 'N/A')
        latest_date = 'N/A'
        if 'createdAt' in latest_version_info:
            date_str = latest_version_info['createdAt']
            latest_date = date_str[:10] if date_str else 'N/A'

        print(f"Latest Version: {version} | Released: {latest_date}")

        # Display web directory information if available
        web_dirs = node_data.get('_web_directories', [])
        if web_dirs:
            print(f"\nWeb Directories:")
            print("-" * 60)
            for file_path in web_dirs:
                print(f"  - {file_path}")

        # Display routes information if available
        routes = node_data.get('_routes', [])
        if routes:
            print(f"\nRoutes:")
            print("-" * 60)
            for file_path in routes:
                print(f"  - {file_path}")

        # Check if dependencies were updated from requirements.txt
        is_updated = latest_version_info.get('_updated_from_requirements', False)
        has_mismatch = False

        if is_updated:
            print(f"\n[Dependencies updated from requirements.txt]")

            # Check for mismatch with original JSON dependencies
            if original_deps_backup and node_id in original_deps_backup:
                original_deps = original_deps_backup[node_id].get('dependencies', [])
                current_deps = latest_version_info.get('dependencies', []) or []

                # Compare using sets to ignore order
                if set(original_deps) != set(current_deps):
                    has_mismatch = True
                    orig_count = len(original_deps)
                    curr_count = len(current_deps)

                    if orig_count == 0 and curr_count > 0:
                        print(f"[MISMATCH: JSON had no dependencies, requirements.txt has {curr_count}]")
                    elif orig_count > 0 and curr_count == 0:
                        print(f"[MISMATCH: JSON had {orig_count} dependencies, requirements.txt has none]")
                    elif orig_count != curr_count:
                        print(f"[MISMATCH: JSON had {orig_count} dependencies, requirements.txt has {curr_count}]")
                    else:
                        # Same count but different deps
                        print(f"[MISMATCH: Different dependencies (both have {orig_count})]")

        # Parse dependencies
        if 'dependencies' in latest_version_info and latest_version_info['dependencies']:
            deps = latest_version_info['dependencies']

            active_deps = []
            commented_deps = []
            pip_commands = []
            git_deps = []

            for dep in deps:
                parsed = parse_dependency_string(dep)

                # Categorize dependencies
                if parsed['is_comment']:
                    commented_deps.append(parsed['original_str'])
                elif parsed['is_pip_command']:
                    pip_commands.append(parsed['cleaned_str'])
                elif parsed['skip']:
                    continue
                elif parsed['is_git_dep']:
                    git_deps.append(parsed['cleaned_str'])
                    active_deps.append(parsed['cleaned_str'])
                else:
                    active_deps.append(parsed['cleaned_str'])

            # Display active dependencies
            if active_deps:
                print(f"\nActive Dependencies ({len(active_deps)}):")
                print("-" * 60)
                for i, dep in enumerate(active_deps, 1):
                    print(f"  {i}. {dep}")
            else:
                print(f"\nNo active dependencies")

            # Display git dependencies separately if present
            if git_deps:
                print(f"\nGit-based Dependencies ({len(git_deps)}):")
                print("-" * 60)
                for i, dep in enumerate(git_deps, 1):
                    print(f"  {i}. {dep}")

            # Display pip commands if present
            if pip_commands:
                print(f"\nPip Command Flags ({len(pip_commands)}):")
                print("-" * 60)
                for i, cmd in enumerate(pip_commands, 1):
                    print(f"  {i}. {cmd}")

            # Display commented dependencies if present
            if commented_deps:
                print(f"\nCommented Dependencies ({len(commented_deps)}):")
                print("-" * 60)
                for i, dep in enumerate(commented_deps, 1):
                    print(f"  {i}. {dep}")
        else:
            print(f"\nNo dependencies listed")
    else:
        print(f"\nNo version information available")

    print("="*60)


def parse_nodes_modifier(query, nodes_dict):
    """
    Parse the &nodes modifier to filter nodes by specific IDs.

    Args:
        query: Query string containing the modifier
        nodes_dict: Full dictionary of nodes

    Returns:
        Filtered nodes dictionary or original if no modifier
    """
    # Check if &nodes modifier is present
    nodes_match = re.search(r'&nodes\s+([^&]+)', query, re.IGNORECASE)
    if not nodes_match:
        return nodes_dict

    nodes_spec = nodes_match.group(1).strip()

    # Check if it's a file specification
    if nodes_spec.startswith('file:'):
        filepath = nodes_spec[5:].strip()
        try:
            with open(filepath, 'r') as f:
                node_ids = [line.strip() for line in f if line.strip()]
            print(f"\n[Loaded {len(node_ids)} node IDs from {filepath}]")
        except FileNotFoundError:
            print(f"\n[Error: File not found: {filepath}]")
            return nodes_dict
        except Exception as e:
            print(f"\n[Error reading file: {e}]")
            return nodes_dict
    else:
        # Parse comma-separated list
        node_ids = [id.strip() for id in nodes_spec.split(',') if id.strip()]
        print(f"\n[Filtering to {len(node_ids)} specific nodes]")

    # Filter nodes dictionary
    filtered_nodes = {}
    missing_ids = []

    for node_id in node_ids:
        if node_id in nodes_dict:
            filtered_nodes[node_id] = nodes_dict[node_id]
        else:
            missing_ids.append(node_id)

    if missing_ids:
        print(f"[Warning: {len(missing_ids)} node IDs not found: {', '.join(missing_ids[:5])}{'...' if len(missing_ids) > 5 else ''}]")

    return filtered_nodes if filtered_nodes else nodes_dict


def print_help():
    """Print help information for commands and modifiers."""
    print("\nCommands:")
    print("  /list  - Show all unique dependency names")
    print("         Use &dupes to show only deps with version conflicts")
    print("  /top   - Show the most common dependencies")
    print("  /nodes - Show details about nodes (sorted by downloads)")
    print("  /nodes <node_id> - Show detailed dependency info for a specific node")
    print("  /nodes <search>! - Auto-select first matching node (fuzzy search)")
    print("  /update - Fetch latest nodes from registry and update nodes.json")
    print("  /graph cumulative - Create cumulative dependencies visualization")
    print("  /graph downloads - Create total downloads visualization (linear scale)")
    print("  /graph downloads log - Create total downloads visualization (log scale)")
    print("  /graph downloads indicators - Show with percentage milestones (50%, 75%, 90%, 99%)")
    print("  /graph downloads log indicators - Log scale with percentage milestones")
    print("  /graph deps - Create dependency count visualization")
    print("  /graph nodes - Create individual node count visualization")
    print("  /summary - Show overall dependency analysis summary")
    print("  /help  - Show this help message")
    print("  /quit  - Exit interactive mode")
    print("\nSearch modifiers:")
    print("  * - Wildcard (e.g., torch*, *audio*)")
    print("  &save - Save results to file")
    print("  &all - Show all results without limits")
    print("  &top N - Only analyze top N nodes by downloads")
    print("         Use negative for bottom N (e.g., &top -10)")
    print("  &nodes - Filter by specific node IDs")
    print("         Comma-separated: &nodes id1,id2")
    print("         From file: &nodes file:nodelist.txt")
    print("  &web-dir - Filter to nodes with web directories")
    print("         Works with /nodes command")
    print("         Example: /nodes &web-dir &top 20")
    print("  &routes - Filter to nodes with routes")
    print("         Works with /nodes command")
    print("         Example: /nodes &routes &top 20")
    print("  &update-reqs - Fetch actual dependencies from requirements.txt")
    print("         Works with /nodes command and node searches")
    print("         Example: /nodes &top 10 &update-reqs")
    print("  Combine: numpy &top 50 &save")
    print("\nOr type a dependency name directly (e.g., numpy, torch)")


def execute_command(nodes_dict, command):
    """
    Execute a single command from the command line.

    Args:
        nodes_dict: Dictionary of nodes
        command: Command to execute
    """
    # Mock stdin with our command followed by quit
    import io
    import sys

    # Save the original stdin
    original_stdin = sys.stdin

    # Create a mock stdin with our command and quit
    sys.stdin = io.StringIO(f"{command}\n/quit\n")

    try:
        # Run interactive mode with our mocked input
        interactive_mode(nodes_dict)
    finally:
        # Restore original stdin
        sys.stdin = original_stdin


def interactive_mode(nodes_dict):
    """
    Interactive chat loop for dependency queries.
    """
    print("\n" + "="*60)
    print("INTERACTIVE DEPENDENCY ANALYZER")
    print("="*60)
    print("\nEnter a dependency name to analyze (or use /quit to exit)")

    # Print help information
    print_help()

    # Dictionary to store original dependencies when updated from requirements.txt
    original_deps_backup = {}

    # Load cached requirements.txt files from previous sessions
    cached_count = load_all_cached_requirements(nodes_dict, original_deps_backup)
    if cached_count > 0:
        print(f"\n[Loaded {cached_count} cached requirements.txt files]")

    # Load web directory data from CSV files
    web_dir_count = load_web_directory_data(nodes_dict)
    if web_dir_count > 0:
        print(f"[Loaded web directory data for {web_dir_count} nodes]")

    # Load routes data from CSV files
    routes_count = load_routes_data(nodes_dict)
    if routes_count > 0:
        print(f"[Loaded routes data for {routes_count} nodes]")

    # Load pip-nonos data from CSV files
    pip_nonos_count = load_pip_nonos_data(nodes_dict)
    if pip_nonos_count > 0:
        print(f"[Loaded pip direct call data for {pip_nonos_count} nodes]")

    # Load node IDs from extension-node-map.json
    node_ids_count = load_node_ids_data(nodes_dict)
    if node_ids_count > 0:
        print(f"[Loaded node IDs for {node_ids_count} nodes]")

    # Pre-compile all dependencies for quick lookup
    dep_analysis = compile_dependencies(nodes_dict)
    # Use unique base dependencies instead of raw unique dependencies
    all_deps_lower = {dep.lower(): dep for dep in dep_analysis['unique_base_dependencies']}

    while True:
        try:
            query = input("\n> ").strip()

            # Handle exit commands
            if query.lower() in ['/quit', '/exit', '/q']:
                print("Exiting interactive mode.")
                break

            elif query.lower() == '/update':
                # Update nodes.json from the registry
                print("\nFetching latest nodes from registry...")
                try:
                    registry_data = get_registry_nodes(print_time=True)

                    # Save using the shared function
                    if save_nodes_json(registry_data):
                        # Also fetch and save extension-node-map.json
                        fetch_and_save_extension_node_map()

                        # Reload the nodes dictionary with the updated data
                        nodes_dict = load_nodes_to_dict()

                        # Reload all data sources
                        web_dir_count = load_web_directory_data(nodes_dict)
                        routes_count = load_routes_data(nodes_dict)
                        pip_nonos_count = load_pip_nonos_data(nodes_dict)
                        node_ids_count = load_node_ids_data(nodes_dict)

                        # Re-compile dependencies for the new data
                        dep_analysis = compile_dependencies(nodes_dict)
                        all_deps_lower = {dep.lower(): dep for dep in dep_analysis['unique_base_dependencies']}

                        print("Nodes data has been refreshed and is ready for analysis.")
                    else:
                        print("Failed to save nodes data")
                except Exception as e:
                    print(f"Error updating nodes.json: {e}")

            elif query.lower() == '/summary':
                # Display the default summary
                display_summary(nodes_dict)

            elif query.lower() == '/graph' or query.lower().startswith('/graph '):
                # Parse modifiers for /graph command
                query_words = query.lower().split()

                # Require a graph type (cumulative, downloads, deps, or nodes)
                if query.lower().strip() == '/graph':
                    print("Error: /graph requires a type (cumulative, downloads, deps, or nodes)")
                    print("Usage:")
                    print("  /graph cumulative - Cumulative dependencies graph")
                    print("  /graph downloads - Downloads graph")
                    print("  /graph deps - Dependency count graph")
                    print("  /graph nodes - Individual node count graph")
                    print("See /help for more options")
                    continue

                save_results = False
                top_n = None
                working_nodes = nodes_dict
                original_query = query

                # Check graph type
                graph_type = None
                use_log_scale = False
                show_indicators = False

                if 'cumulative' in query_words:
                    graph_type = 'dependencies'
                elif 'downloads' in query_words:
                    graph_type = 'downloads'
                    # Check for log scale option
                    if 'log' in query_words:
                        use_log_scale = True
                    # Check for indicators option
                    if 'indicators' in query_words:
                        show_indicators = True
                elif 'deps' in query_words:
                    graph_type = 'deps'
                elif 'nodes' in query_words:
                    graph_type = 'nodes'
                else:
                    print("Error: Unknown graph type. Use 'cumulative', 'downloads', 'deps', or 'nodes'")
                    print("Usage:")
                    print("  /graph cumulative - Cumulative dependencies graph")
                    print("  /graph downloads - Downloads graph")
                    print("  /graph deps - Dependency count graph")
                    print("  /graph nodes - Individual node count graph")
                    continue

                # Parse &nodes modifier first to filter by specific nodes
                working_nodes = parse_nodes_modifier(query, working_nodes)

                # Track if we filtered by specific nodes (for percentile calculation)
                is_nodes_filter = '&nodes' in query.lower()

                # Parse &save modifier
                if '&save' in query.lower():
                    save_results = True

                # Parse &top modifier if present
                # Keep reference to full dataset before &top filtering (for percentile calculation)
                full_nodes_for_percentiles = working_nodes if not is_nodes_filter else None
                if '&top' in query.lower():
                    top_match = re.search(r'&top\s+(-?\d+)', query.lower())
                    if top_match:
                        top_n = int(top_match.group(1))
                        # Filter to top N nodes by downloads
                        sorted_nodes = sorted(working_nodes.items(), key=lambda x: x[1].get('downloads', 0), reverse=True)
                        if top_n > 0:
                            working_nodes = dict(sorted_nodes[:top_n])
                            print(f"\n[Filtering to top {top_n} nodes by downloads]")
                        else:
                            # Negative number means bottom N nodes
                            working_nodes = dict(sorted_nodes[top_n:])
                            print(f"\n[Filtering to bottom {abs(top_n)} nodes by downloads]")

                # Create the appropriate graph type
                if graph_type == 'downloads':
                    create_downloads_graph(working_nodes, save_to_file=save_results, query_desc=original_query, log_scale=use_log_scale, show_indicators=show_indicators, full_nodes_for_percentiles=full_nodes_for_percentiles)
                elif graph_type == 'deps':
                    create_deps_graph(working_nodes, save_to_file=save_results, query_desc=original_query, full_nodes_for_percentiles=full_nodes_for_percentiles)
                elif graph_type == 'nodes':
                    create_nodes_graph(working_nodes, save_to_file=save_results, query_desc=original_query, full_nodes_for_percentiles=full_nodes_for_percentiles)
                else:
                    create_cumulative_graph(working_nodes, save_to_file=save_results, query_desc=original_query)

            elif query.lower() == '/help':
                print_help()

            elif query.lower() == '/list' or query.lower().startswith('/list '):
                # Check for modifiers in /list command
                working_nodes = nodes_dict
                top_n = None
                show_dupes = False
                save_results = False
                original_query = query

                # Parse &nodes modifier first to filter by specific nodes
                working_nodes = parse_nodes_modifier(query, working_nodes)

                # Parse &dupes modifier
                if '&dupes' in query.lower():
                    show_dupes = True

                # Parse &save modifier
                if '&save' in query.lower():
                    save_results = True

                # Parse &top modifier if present
                if '&top' in query.lower():
                    top_match = re.search(r'&top\s+(-?\d+)', query.lower())
                    if top_match:
                        top_n = int(top_match.group(1))
                        # Filter to top N nodes by downloads
                        sorted_nodes = sorted(working_nodes.items(), key=lambda x: x[1].get('downloads', 0), reverse=True)
                        if top_n > 0:
                            working_nodes = dict(sorted_nodes[:top_n])
                            print(f"\n[Filtering to top {top_n} nodes by downloads]")
                        else:
                            # Negative number means bottom N nodes
                            working_nodes = dict(sorted_nodes[top_n:])
                            print(f"\n[Filtering to bottom {abs(top_n)} nodes by downloads]")

                # Re-compile dependencies for the filtered set
                filtered_dep_analysis = compile_dependencies(working_nodes)

                if show_dupes:
                    # Separate dependencies into duplicates and non-duplicates
                    dupes_only = []
                    non_dupes = []

                    for dep_name, versions in filtered_dep_analysis['dependency_versions'].items():
                        count = filtered_dep_analysis['dependency_count'].get(dep_name, 0)
                        if len(versions) > 1:
                            dupes_only.append((dep_name, count, versions))
                        else:
                            # Non-duplicates have only one version
                            non_dupes.append((dep_name, count, list(versions)[0] if versions else '*'))

                    # Sort by count (most used first), then alphabetically
                    dupes_only.sort(key=lambda x: (-x[1], x[0].lower()))
                    non_dupes.sort(key=lambda x: (-x[1], x[0].lower()))

                    output_lines = []

                    # Header for duplicates section
                    if top_n:
                        if top_n > 0:
                            output_lines.append(f"\nDEPENDENCIES WITH MULTIPLE VERSIONS in top {top_n} nodes ({len(dupes_only)} total):")
                        else:
                            output_lines.append(f"\nDEPENDENCIES WITH MULTIPLE VERSIONS in bottom {abs(top_n)} nodes ({len(dupes_only)} total):")
                    else:
                        output_lines.append(f"\nDEPENDENCIES WITH MULTIPLE VERSIONS ({len(dupes_only)} total):")

                    output_lines.append("="*60)

                    for dep_name, count, versions in dupes_only:
                        output_lines.append(f"\n{dep_name} ({count} nodes total, {len(versions)} different specs):")
                        # Sort versions by frequency
                        version_list = list(versions)
                        version_counts = []
                        for v in version_list:
                            # Count how many nodes use this specific version
                            v_count = sum(1 for node_id, node_data in working_nodes.items()
                                        if 'latest_version' in node_data and node_data['latest_version']
                                        and 'dependencies' in node_data['latest_version']
                                        and any(str(d).strip() == v for d in node_data['latest_version']['dependencies']))
                            version_counts.append((v, v_count))

                        version_counts.sort(key=lambda x: -x[1])
                        for v, v_count in version_counts:  # Show all versions
                            output_lines.append(f"  {v:40} ({v_count} nodes)")

                    # Add non-duplicates section
                    if non_dupes:
                        output_lines.append("")
                        if top_n:
                            if top_n > 0:
                                output_lines.append(f"\nDEPENDENCIES WITH SINGLE VERSION in top {top_n} nodes ({len(non_dupes)} total):")
                            else:
                                output_lines.append(f"\nDEPENDENCIES WITH SINGLE VERSION in bottom {abs(top_n)} nodes ({len(non_dupes)} total):")
                        else:
                            output_lines.append(f"\nDEPENDENCIES WITH SINGLE VERSION ({len(non_dupes)} total):")
                        output_lines.append("="*60)

                        for dep_name, count, version_spec in non_dupes:
                            output_lines.append(f"{dep_name:40} ({count:3} nodes) - {version_spec}")

                    # Print output
                    output_text = '\n'.join(output_lines)
                    print(output_text)

                    # Save if requested
                    if save_results:
                        save_results_to_file("list_dupes_" + original_query.replace('/list', '').strip(), output_text)

                else:
                    # Normal /list behavior
                    # Sort dependencies alphabetically but include counts
                    deps_with_counts = [(dep, filtered_dep_analysis['dependency_count'].get(dep, 0))
                                       for dep in filtered_dep_analysis['unique_base_dependencies']]
                    deps_with_counts.sort(key=lambda x: x[0].lower())

                    if top_n:
                        if top_n > 0:
                            print(f"\nUnique package names in top {top_n} nodes ({len(deps_with_counts)} total):")
                        else:
                            print(f"\nUnique package names in bottom {abs(top_n)} nodes ({len(deps_with_counts)} total):")
                    else:
                        print(f"\nAll unique package names ({len(deps_with_counts)} total):")
                    print("(Versions are grouped together under base package names)")
                    print("(Number in parentheses shows how many nodes use this dependency)")

                    # Print in columns for readability with counts
                    for i in range(0, len(deps_with_counts), 2):
                        row = deps_with_counts[i:i+2]
                        print("  " + " | ".join(f"{dep:30} ({count:3})" for dep, count in row))

                    # Save if requested
                    if save_results:
                        output_lines = []
                        if top_n:
                            if top_n > 0:
                                output_lines.append(f"Unique package names in top {top_n} nodes ({len(deps_with_counts)} total):")
                            else:
                                output_lines.append(f"Unique package names in bottom {abs(top_n)} nodes ({len(deps_with_counts)} total):")
                        else:
                            output_lines.append(f"All unique package names ({len(deps_with_counts)} total):")
                        output_lines.append("(Versions are grouped together under base package names)")
                        output_lines.append("(Number in parentheses shows how many nodes use this dependency)\n")

                        for dep, count in deps_with_counts:
                            output_lines.append(f"{dep:40} ({count:3})")

                        save_text = '\n'.join(output_lines)
                        save_results_to_file("list_" + original_query.replace('/list', '').strip(), save_text)

            elif query.lower() == '/top' or query.lower().startswith('/top '):
                # Check for &top modifier in /top command
                working_nodes = nodes_dict
                top_n = None

                # Parse &nodes modifier first to filter by specific nodes
                working_nodes = parse_nodes_modifier(query, working_nodes)

                # Parse &top modifier if present
                if '&top' in query.lower():
                    top_match = re.search(r'&top\s+(-?\d+)', query.lower())
                    if top_match:
                        top_n = int(top_match.group(1))
                        # Filter to top N nodes by downloads
                        sorted_nodes = sorted(working_nodes.items(), key=lambda x: x[1].get('downloads', 0), reverse=True)
                        if top_n > 0:
                            working_nodes = dict(sorted_nodes[:top_n])
                            print(f"\n[Filtering to top {top_n} nodes by downloads]")
                        else:
                            # Negative number means bottom N nodes
                            working_nodes = dict(sorted_nodes[top_n:])
                            print(f"\n[Filtering to bottom {abs(top_n)} nodes by downloads]")

                # Re-compile dependencies for the filtered set
                filtered_dep_analysis = compile_dependencies(working_nodes)

                if top_n:
                    if top_n > 0:
                        print(f"\nTop 20 most common dependencies in top {top_n} nodes:")
                    else:
                        print(f"\nTop 20 most common dependencies in bottom {abs(top_n)} nodes:")
                else:
                    print("\nTop 20 most common dependencies:")
                for dep, count in filtered_dep_analysis['sorted_by_frequency'][:20]:
                    print(f"  {dep:30} - {count} nodes")

            elif query.lower() == '/nodes' or query.lower().startswith('/nodes '):
                # Extract the node name/ID after /nodes (if provided)
                node_search = query[6:].strip() if len(query) > 6 else ""  # Remove '/nodes'
                original_query = query

                # Parse and strip modifiers to see if a node name remains
                save_results = False
                show_all = False
                top_n = None
                update_reqs = False
                web_dir_only = False

                # Strip modifiers from node_search to get the actual node name
                if '&update-reqs' in node_search.lower():
                    update_reqs = True
                    node_search = re.sub(r'&update-reqs', '', node_search, flags=re.IGNORECASE).strip()

                if '&save' in node_search.lower():
                    save_results = True
                    node_search = re.sub(r'&save', '', node_search, flags=re.IGNORECASE).strip()

                if '&all' in node_search.lower():
                    show_all = True
                    node_search = re.sub(r'&all', '', node_search, flags=re.IGNORECASE).strip()

                if '&web-dir' in node_search.lower():
                    web_dir_only = True
                    node_search = re.sub(r'&web-dir', '', node_search, flags=re.IGNORECASE).strip()

                routes_only = False
                if '&routes' in node_search.lower():
                    routes_only = True
                    node_search = re.sub(r'&routes', '', node_search, flags=re.IGNORECASE).strip()

                if '&top' in node_search.lower():
                    top_match = re.search(r'&top\s+(-?\d+)', node_search.lower())
                    if top_match:
                        top_n = int(top_match.group(1))
                        node_search = re.sub(r'&top\s+-?\d+', '', node_search, flags=re.IGNORECASE).strip()

                # Remove &nodes modifier if present
                if '&nodes' in node_search.lower():
                    node_search = re.sub(r'&nodes\s+[^&]+', '', node_search, flags=re.IGNORECASE).strip()

                # If there's a node name/ID remaining after stripping modifiers, search for it
                if node_search:
                    # Check if search ends with ! (auto-select first match)
                    auto_select_first = node_search.endswith('!')
                    if auto_select_first:
                        node_search = node_search[:-1].strip()  # Remove the !

                    node_search_lower = node_search.lower()

                    # If &update-reqs is specified, update dependencies first
                    if update_reqs:
                        # Determine which node(s) to update
                        node_to_update = None
                        if node_search_lower in nodes_dict:
                            node_to_update = node_search_lower
                        elif node_search in nodes_dict:
                            node_to_update = node_search

                        if node_to_update:
                            print(f"\nUpdating dependencies for {node_to_update}...")
                            update_node_requirements(nodes_dict, [node_to_update], original_deps_backup)
                            print()

                    # Try exact match first (case-insensitive)
                    if node_search_lower in nodes_dict:
                        display_node_dependencies(nodes_dict, node_search_lower, original_deps_backup)
                    elif node_search in nodes_dict:
                        display_node_dependencies(nodes_dict, node_search, original_deps_backup)
                    else:
                        # Try to find nodes that start with the search string
                        starts_with_matches = [node_id for node_id in nodes_dict.keys()
                                              if node_id.lower().startswith(node_search_lower)]

                        if starts_with_matches:
                            # Sort by downloads
                            starts_with_sorted = sorted(starts_with_matches,
                                                       key=lambda x: nodes_dict[x].get('downloads', 0),
                                                       reverse=True)

                            # Auto-select first match if ! was used
                            if auto_select_first:
                                selected_node = starts_with_sorted[0]
                                print(f"\n[Auto-selected: {selected_node}]")
                                display_node_dependencies(nodes_dict, selected_node, original_deps_backup)
                            else:
                                print(f"\nNo exact match for '{node_search}'. Found {len(starts_with_matches)} nodes starting with '{node_search}':\n")

                                # Show up to 20 matches
                                show_limit = min(len(starts_with_sorted), 20)

                                for i, node_id in enumerate(starts_with_sorted[:show_limit], 1):
                                    node = nodes_dict[node_id]
                                    name = node.get('name', 'N/A')
                                    downloads = node.get('downloads', 0)
                                    print(f"  {i}. {node_id:40} - {name} ({downloads:,} downloads)")

                                if len(starts_with_sorted) > show_limit:
                                    print(f"\n  ... and {len(starts_with_sorted) - show_limit} more nodes")

                                print(f"\nTo see details for a specific node, type: /nodes <node_id>")
                                print(f"Or use /nodes {node_search}! to auto-select the first match")
                        else:
                            # Try substring match
                            partial_matches = [node_id for node_id in nodes_dict.keys()
                                             if node_search_lower in node_id.lower()]

                            if partial_matches:
                                # Sort by downloads
                                partial_sorted = sorted(partial_matches,
                                                       key=lambda x: nodes_dict[x].get('downloads', 0),
                                                       reverse=True)

                                # Auto-select first match if ! was used
                                if auto_select_first:
                                    selected_node = partial_sorted[0]
                                    print(f"\n[Auto-selected: {selected_node}]")
                                    display_node_dependencies(nodes_dict, selected_node, original_deps_backup)
                                else:
                                    print(f"\nNo nodes starting with '{node_search}'. Found {len(partial_matches)} containing '{node_search}':\n")

                                    # Show up to 10 matches
                                    for i, node_id in enumerate(partial_sorted[:10], 1):
                                        node = nodes_dict[node_id]
                                        name = node.get('name', 'N/A')
                                        downloads = node.get('downloads', 0)
                                        print(f"  {i}. {node_id:40} - {name} ({downloads:,} downloads)")

                                    if len(partial_matches) > 10:
                                        print(f"\n  ... and {len(partial_matches) - 10} more matches")

                                    print(f"\nTo see details for a specific node, type: /nodes <node_id>")
                                    print(f"Or use /nodes {node_search}! to auto-select the first match")
                            else:
                                print(f"\nNo node found matching '{node_search}'")
                                print("Use /nodes to see all available nodes")
                    continue

                # No node name specified, show the list
                working_nodes = nodes_dict

                # Parse &nodes modifier first to filter by specific nodes
                working_nodes = parse_nodes_modifier(query, working_nodes)

                # Parse modifiers
                if '&save' in query.lower():
                    save_results = True

                if '&all' in query.lower():
                    show_all = True

                if '&top' in query.lower():
                    top_match = re.search(r'&top\s+(-?\d+)', query.lower())
                    if top_match:
                        top_n = int(top_match.group(1))
                        # Filter to top N nodes by downloads
                        sorted_nodes = sorted(working_nodes.items(), key=lambda x: x[1].get('downloads', 0), reverse=True)
                        if top_n > 0:
                            working_nodes = dict(sorted_nodes[:top_n])
                            print(f"\n[Filtering to top {top_n} nodes by downloads]")
                        else:
                            # Negative number means bottom N nodes
                            working_nodes = dict(sorted_nodes[top_n:])
                            print(f"\n[Filtering to bottom {abs(top_n)} nodes by downloads]")

                # Filter by web directories if requested
                if '&web-dir' in query.lower():
                    web_dir_nodes = {node_id: node_data for node_id, node_data in working_nodes.items()
                                    if node_data.get('_web_directories')}
                    working_nodes = web_dir_nodes
                    print(f"\n[Filtering to nodes with web directories: {len(working_nodes)} nodes]")

                # Filter by routes if requested
                if '&routes' in query.lower():
                    routes_nodes = {node_id: node_data for node_id, node_data in working_nodes.items()
                                   if node_data.get('_routes')}
                    working_nodes = routes_nodes
                    print(f"\n[Filtering to nodes with routes: {len(working_nodes)} nodes]")

                # Handle &update-reqs modifier
                if '&update-reqs' in query.lower():
                    node_ids = list(working_nodes.keys())
                    print(f"\nUpdating requirements for {len(node_ids)} nodes...")
                    print("="*60)
                    stats = update_node_requirements(nodes_dict, node_ids, original_deps_backup)
                    print("="*60)
                    print(f"\nUpdate Summary:")
                    print(f"  Total: {stats['total']}")
                    print(f"  Success: {stats['success']}")
                    print(f"  Failed: {stats['failed']}")
                    if stats['unsupported'] > 0:
                        print(f"    - Unsupported host: {stats['unsupported']}")
                    print()

                    # Recompile dependencies after update
                    dep_analysis = compile_dependencies(nodes_dict)
                    all_deps_lower = {dep.lower(): dep for dep in dep_analysis['unique_base_dependencies']}

                # Calculate ranks for ALL nodes (not just working_nodes)
                full_rank_map = calculate_node_ranks(nodes_dict)

                # Sort all nodes by downloads
                sorted_nodes = sorted(working_nodes.items(), key=lambda x: x[1].get('downloads', 0), reverse=True)

                # Determine how many to show
                nodes_to_display = sorted_nodes if show_all else sorted_nodes[:20]

                # Build output
                output_lines = []
                if top_n:
                    if top_n > 0:
                        output_lines.append(f"\nTop {min(len(nodes_to_display), top_n)} nodes by downloads:")
                    else:
                        output_lines.append(f"\nBottom {min(len(nodes_to_display), abs(top_n))} nodes by downloads:")
                elif show_all:
                    output_lines.append(f"\nAll {len(nodes_to_display)} nodes by downloads:")
                else:
                    output_lines.append(f"\nTop {min(len(nodes_to_display), 20)} nodes by downloads:")

                output_lines.append("="*60)

                for i, (node_id, node_data) in enumerate(nodes_to_display, 1):
                    # Extract node information
                    name = node_data.get('name', 'N/A')
                    downloads = node_data.get('downloads', 0)
                    stars = node_data.get('github_stars', 0)
                    repo = node_data.get('repository', 'N/A')
                    description = node_data.get('description', 'N/A')

                    # Get latest version info
                    latest_version_info = node_data.get('latest_version', {})
                    latest_date = 'N/A'
                    version = 'N/A'
                    dep_count = 0

                    if latest_version_info:
                        if 'createdAt' in latest_version_info:
                            date_str = latest_version_info['createdAt']
                            latest_date = date_str[:10] if date_str else 'N/A'

                        version = latest_version_info.get('version', 'N/A')

                        if 'dependencies' in latest_version_info:
                            deps = latest_version_info['dependencies']
                            if deps and isinstance(deps, list):
                                # Count only active dependencies (not commented or pip commands)
                                dep_count = sum(1 for d in deps if not str(d).strip().startswith('#') and not str(d).strip().startswith('--'))

                    # Check for mismatch with original JSON
                    has_mismatch = False
                    if latest_version_info and latest_version_info.get('_updated_from_requirements', False):
                        if original_deps_backup and node_id in original_deps_backup:
                            original_deps = original_deps_backup[node_id].get('dependencies', [])
                            current_deps = latest_version_info.get('dependencies', []) or []
                            if set(original_deps) != set(current_deps):
                                has_mismatch = True

                    # Check if node has web directory
                    has_web_dir = bool(node_data.get('_web_directories'))
                    has_routes = bool(node_data.get('_routes'))

                    # Get individual nodes count
                    node_ids = node_data.get('_node_ids', [])
                    node_count = len(node_ids) if node_ids else 0
                    has_node_pattern = node_data.get('_has_node_pattern', False)

                    # Format output
                    rank = full_rank_map.get(node_id, 'N/A')
                    asterisk = "*" if has_mismatch else ""
                    web_indicator = " | Web: Yes" if has_web_dir else ""
                    routes_indicator = " | Routes: Yes" if has_routes else ""

                    # Show nodes indicator if we have explicit nodes or a pattern
                    if node_count > 0 or has_node_pattern:
                        node_pattern_asterisk = "*" if has_node_pattern else ""
                        nodes_indicator = f" | Nodes: {node_count}{node_pattern_asterisk}"
                    else:
                        nodes_indicator = ""

                    output_lines.append(f"\n{i}. {name} ({node_id})")
                    output_lines.append(f"   Rank: #{rank} | Downloads: {downloads:,} | Stars: {stars:,} | Dependencies: {dep_count}{asterisk}{web_indicator}{routes_indicator}{nodes_indicator}")
                    output_lines.append(f"   Latest: {latest_date} | Version: {version}")
                    if len(description) > 100:
                        output_lines.append(f"   Description: {description[:100]}...")
                    else:
                        output_lines.append(f"   Description: {description}")
                    output_lines.append(f"   Repository: {repo}")

                if not show_all and len(sorted_nodes) > 20:
                    output_lines.append(f"\n... and {len(sorted_nodes) - 20} more nodes")
                    output_lines.append("Use &all to see all nodes")

                # Print output
                output_text = '\n'.join(output_lines)
                print(output_text)

                # Save if requested
                if save_results:
                    # For saved file, always show all nodes in the working set
                    save_lines = []
                    if top_n:
                        if top_n > 0:
                            save_lines.append(f"All {len(sorted_nodes)} nodes (filtered to top {top_n} by downloads):")
                        else:
                            save_lines.append(f"All {len(sorted_nodes)} nodes (filtered to bottom {abs(top_n)} by downloads):")
                    else:
                        save_lines.append(f"All {len(sorted_nodes)} nodes by downloads:")
                    save_lines.append("="*60)

                    for i, (node_id, node_data) in enumerate(sorted_nodes, 1):
                        name = node_data.get('name', 'N/A')
                        downloads = node_data.get('downloads', 0)
                        stars = node_data.get('github_stars', 0)
                        repo = node_data.get('repository', 'N/A')
                        description = node_data.get('description', 'N/A')

                        latest_version_info = node_data.get('latest_version', {})
                        latest_date = 'N/A'
                        version = 'N/A'
                        dep_count = 0

                        if latest_version_info:
                            if 'createdAt' in latest_version_info:
                                date_str = latest_version_info['createdAt']
                                latest_date = date_str[:10] if date_str else 'N/A'

                            version = latest_version_info.get('version', 'N/A')

                            if 'dependencies' in latest_version_info:
                                deps = latest_version_info['dependencies']
                                if deps and isinstance(deps, list):
                                    dep_count = sum(1 for d in deps if not str(d).strip().startswith('#') and not str(d).strip().startswith('--'))

                        # Check for mismatch with original JSON
                        has_mismatch = False
                        if latest_version_info and latest_version_info.get('_updated_from_requirements', False):
                            if original_deps_backup and node_id in original_deps_backup:
                                original_deps = original_deps_backup[node_id].get('dependencies', [])
                                current_deps = latest_version_info.get('dependencies', []) or []
                                if set(original_deps) != set(current_deps):
                                    has_mismatch = True

                        # Check if node has web directory
                        has_web_dir = bool(node_data.get('_web_directories'))
                        has_routes = bool(node_data.get('_routes'))

                        # Get individual nodes count
                        node_ids = node_data.get('_node_ids', [])
                        node_count = len(node_ids) if node_ids else 0
                        has_node_pattern = node_data.get('_has_node_pattern', False)

                        rank = full_rank_map.get(node_id, 'N/A')
                        asterisk = "*" if has_mismatch else ""
                        web_indicator = " | Web: Yes" if has_web_dir else ""
                        routes_indicator = " | Routes: Yes" if has_routes else ""

                        # Show nodes indicator if we have explicit nodes or a pattern
                        if node_count > 0 or has_node_pattern:
                            node_pattern_asterisk = "*" if has_node_pattern else ""
                            nodes_indicator = f" | Nodes: {node_count}{node_pattern_asterisk}"
                        else:
                            nodes_indicator = ""

                        save_lines.append(f"\n{i}. {name} ({node_id})")
                        save_lines.append(f"   Rank: #{rank} | Downloads: {downloads:,} | Stars: {stars:,} | Dependencies: {dep_count}{asterisk}{web_indicator}{routes_indicator}{nodes_indicator}")
                        save_lines.append(f"   Latest: {latest_date} | Version: {version}")
                        save_lines.append(f"   Description: {description}")
                        save_lines.append(f"   Repository: {repo}")

                    save_text = '\n'.join(save_lines)
                    save_results_to_file("nodes_" + original_query.replace('/nodes', '').strip(), save_text)

            elif query:
                # Check for modifiers
                save_results = False
                show_all = False
                top_n = None
                working_nodes = nodes_dict
                original_query = query

                # Parse modifiers (case-insensitive)
                query_lower = query.lower()

                # Parse &nodes modifier first and remove it from query
                if '&nodes' in query_lower:
                    working_nodes = parse_nodes_modifier(original_query, working_nodes)
                    # Remove &nodes specification from query
                    query = re.sub(r'&nodes\s+[^&]+', '', query, flags=re.IGNORECASE).strip()
                    query_lower = query.lower()

                # Parse &top N modifier
                if '&top' in query_lower:
                    top_match = re.search(r'&top\s+(-?\d+)', query_lower)
                    if top_match:
                        top_n = int(top_match.group(1))
                        # Remove the &top N from the query
                        query = re.sub(r'&top\s+-?\d+', '', query, flags=re.IGNORECASE).strip()
                        query_lower = query.lower()

                        # Filter to top N nodes by downloads
                        sorted_nodes = sorted(working_nodes.items(), key=lambda x: x[1].get('downloads', 0), reverse=True)
                        if top_n > 0:
                            working_nodes = dict(sorted_nodes[:top_n])
                            print(f"\n[Filtering to top {top_n} nodes by downloads]")
                        else:
                            # Negative number means bottom N nodes
                            working_nodes = dict(sorted_nodes[top_n:])
                            print(f"\n[Filtering to bottom {abs(top_n)} nodes by downloads]")

                if '&save' in query_lower:
                    save_results = True
                    query = query.replace('&save', '').replace('&SAVE', '').replace('&Save', '').strip()
                    query_lower = query.lower()

                if '&all' in query_lower:
                    show_all = True
                    query = query.replace('&all', '').replace('&ALL', '').replace('&All', '').strip()

                # Capture output for saving if needed
                output_lines = []

                # Re-compile dependencies for the filtered set if using &top
                if top_n:
                    dep_analysis = compile_dependencies(working_nodes)
                    all_deps_lower = {dep.lower(): dep for dep in dep_analysis['unique_base_dependencies']}

                # Check if query contains wildcard
                if '*' in query:
                    print(f"\nSearching for dependencies matching pattern: {query}")
                    wildcard_results = analyze_wildcard_dependencies(working_nodes, query)

                    if wildcard_results:
                        # Sort by total nodes using each dependency
                        sorted_results = sorted(wildcard_results.items(),
                                              key=lambda x: x[1]['total_nodes'],
                                              reverse=True)

                        # Build output for display and saving
                        output_lines = []
                        output_lines.append(f"\nFound {len(wildcard_results)} dependencies matching '{query}':")
                        output_lines.append("="*60)

                        total_nodes = sum(info['total_nodes'] for _, info in wildcard_results.items())
                        output_lines.append(f"Total nodes using any matching dependency: {total_nodes}")

                        # Format each dependency's details
                        for dep_name, dep_info in sorted_results:
                            # Use show_all flag for display
                            if show_all:
                                output_lines.append(format_dependency_details(dep_info, show_all_nodes=True))
                            else:
                                # Create limited version for display
                                output_lines.append(f"\n{'='*50}")
                                output_lines.append(f"Dependency: {dep_name}")
                                output_lines.append(f"{'='*50}")
                                output_lines.append(f"Total nodes using this dependency: {dep_info['total_nodes']}")

                                if dep_info['commented_count'] > 0:
                                    output_lines.append(f"Nodes with commented-out lines: {dep_info['commented_count']}")

                                if dep_info['total_nodes'] > 0:
                                    # Show version distribution
                                    if len(dep_info['sorted_versions']) > 0:
                                        output_lines.append(f"\nVersion specifications found:")
                                        # Show up to 5 versions for wildcard results
                                        for version, count in dep_info['sorted_versions'][:5]:
                                            output_lines.append(f"  {version:20} - {count} nodes")
                                        if len(dep_info['sorted_versions']) > 5:
                                            output_lines.append(f"  ... and {len(dep_info['sorted_versions']) - 5} more versions")

                                    # Sort nodes by downloads (most popular first)
                                    sorted_nodes = sorted(dep_info['nodes_using'],
                                                        key=lambda x: x.get('downloads', 0),
                                                        reverse=True)

                                    # Show top 5 nodes for wildcard results
                                    output_lines.append(f"\nTop nodes using {dep_name} (showing up to 5 by popularity):")
                                    for i, node in enumerate(sorted_nodes[:5], 1):
                                        output_lines.append(f"\n  {i}. {node['node_name']} ({node['node_id']})")
                                        output_lines.append(f"     Rank: #{node.get('rank', 'N/A')} | Downloads: {node.get('downloads', 0):,} | Stars: {node.get('stars', 0):,} | Latest: {node.get('latest_version_date', 'N/A')}")
                                        output_lines.append(f"     Spec: {node['dependency_spec']}")
                                        output_lines.append(f"     Repo: {node['repository']}")

                                    if dep_info['total_nodes'] > 5:
                                        output_lines.append(f"\n  ... and {dep_info['total_nodes'] - 5} more nodes using {dep_name}")

                                if dep_info['commented_count'] > 0 and dep_info['nodes_with_commented']:
                                    output_lines.append(f"\n  Nodes with commented-out {dep_name} lines:")
                                    for i, node in enumerate(dep_info['nodes_with_commented'][:2], 1):
                                        output_lines.append(f"    {i}. {node['node_name']} ({node['node_id']})")
                                    if dep_info['commented_count'] > 2:
                                        output_lines.append(f"    ... and {dep_info['commented_count'] - 2} more with commented {dep_name}")

                        output_lines.append("\n" + "="*60)
                        output_lines.append("To see details for a specific dependency, type its full name.")

                        # Print output
                        output_text = '\n'.join(output_lines)
                        print(output_text)

                        # Save if requested
                        if save_results:
                            # For saved file, regenerate with all nodes shown
                            save_lines = []
                            save_lines.append(f"Found {len(wildcard_results)} dependencies matching '{query}':")
                            save_lines.append("="*60)
                            save_lines.append(f"Total nodes using any matching dependency: {total_nodes}")

                            for dep_name, dep_info in sorted_results:
                                save_lines.append(format_dependency_details(dep_info, show_all_nodes=True))

                            save_text = '\n'.join(save_lines)
                            save_results_to_file(original_query, save_text)
                    else:
                        print(f"\nNo dependencies found matching pattern '{query}'")

                # Regular non-wildcard query
                else:
                    # Look for exact match first (case-insensitive)
                    query_lower = query.lower()
                    exact_match = None

                    # Check for exact match
                    if query_lower in all_deps_lower:
                        exact_match = all_deps_lower[query_lower]

                    if exact_match:
                        result = analyze_specific_dependency(working_nodes, exact_match)

                        # Format output for display (use show_all flag)
                        output_text = format_dependency_details(result, show_all_nodes=show_all)
                        print(output_text)

                        # Save if requested
                        if save_results:
                            # Always save with all nodes shown
                            full_output = format_dependency_details(result, show_all_nodes=True)
                            save_results_to_file(original_query, full_output)
                    else:
                        # Try to find dependencies starting with the search string
                        starts_with_matches = [dep for dep_lower, dep in all_deps_lower.items()
                                             if dep_lower.startswith(query_lower)]

                        if starts_with_matches:
                            print(f"\nNo exact match for '{query}'. Found {len(starts_with_matches)} dependencies starting with '{query}':\n")

                            # Sort by frequency (most used first)
                            starts_with_sorted = sorted(starts_with_matches,
                                                      key=lambda x: dep_analysis['dependency_count'].get(x, 0),
                                                      reverse=True)

                            # Show all matches if 20 or fewer, otherwise show top 20
                            show_limit = len(starts_with_sorted) if len(starts_with_sorted) <= 20 else 20

                            for match in starts_with_sorted[:show_limit]:
                                count = dep_analysis['dependency_count'].get(match, 0)
                                print(f"  - {match:40} ({count} nodes)")

                            if len(starts_with_sorted) > show_limit:
                                print(f"\n  ... and {len(starts_with_sorted) - show_limit} more dependencies starting with '{query}'")
                                print(f"  (Showing top {show_limit} by usage)")

                            print(f"\nTo analyze any of these, type the full dependency name.")
                        else:
                            # If no starts-with matches, try substring match anywhere
                            partial_matches = [dep for dep_lower, dep in all_deps_lower.items()
                                             if query_lower in dep_lower]

                            if partial_matches:
                                print(f"\nNo dependencies starting with '{query}'. Found {len(partial_matches)} containing '{query}':")

                                # Sort by frequency
                                partial_sorted = sorted(partial_matches[:20],
                                                      key=lambda x: dep_analysis['dependency_count'].get(x, 0),
                                                      reverse=True)

                                for match in partial_sorted[:10]:
                                    count = dep_analysis['dependency_count'].get(match, 0)
                                    print(f"  - {match:40} ({count} nodes)")
                                if len(partial_matches) > 10:
                                    print(f"  ... and {len(partial_matches) - 10} more matches containing '{query}'")
                            else:
                                print(f"\nNo dependency found matching '{query}'")
                                print("Use 'list' to see all available dependencies")

        except KeyboardInterrupt:
            print("\n\nInterrupted. Exiting interactive mode.")
            break
        except Exception as e:
            print(f"Error: {e}")


def display_summary(nodes_dict):
    """
    Display the summary of nodes and dependencies.
    This is the default output when not using --ask.
    """
    print(f"\nFirst 3 node IDs in the dictionary:")
    for i, node_id in enumerate(list(nodes_dict.keys())[:3]):
        print(f"  - {node_id}")

    print(f"\nExample node data for first ID:")
    first_id = list(nodes_dict.keys())[0]
    first_node = nodes_dict[first_id]
    print(f"ID: {first_id}")
    print(f"Name: {first_node.get('name', 'N/A')}")
    print(f"Repository: {first_node.get('repository', 'N/A')}")
    print(f"Description: {first_node.get('description', 'N/A')[:100]}...")

    print("\n" + "="*60)
    print("DEPENDENCY ANALYSIS")
    print("="*60)

    dep_analysis = compile_dependencies(nodes_dict)

    print(f"\nTotal nodes analyzed: {len(nodes_dict)}")
    print(f"Nodes with active dependencies: {dep_analysis['nodes_with_deps_count']}")
    print(f"Nodes without active dependencies: {dep_analysis['nodes_without_deps_count']}")
    if dep_analysis['nodes_with_commented_count'] > 0:
        print(f"Nodes with commented-out lines: {dep_analysis['nodes_with_commented_count']}")
    if dep_analysis['nodes_with_pip_commands_count'] > 0:
        print(f"INFO: Nodes with pip commands (--): {dep_analysis['nodes_with_pip_commands_count']}")
    if dep_analysis['nodes_with_git_deps_count'] > 0:
        print(f"Nodes with git-based dependencies: {dep_analysis['nodes_with_git_deps_count']}")
    print(f"\nTotal active dependency references: {dep_analysis['total_dependencies']}")
    print(f"Unique active packages (grouping versions): {dep_analysis['unique_count']}")
    print(f"Unique dependency specifications: {dep_analysis['unique_raw_count']}")
    if len(dep_analysis['unique_commented_dependencies']) > 0:
        print(f"Unique commented dependencies: {len(dep_analysis['unique_commented_dependencies'])}")

    print(f"\nTop 10 most common dependencies:")
    for dep, count in dep_analysis['sorted_by_frequency'][:10]:
        print(f"  - {dep}: {count} nodes")

    if dep_analysis['nodes_with_commented_count'] > 0:
        print(f"\n\nNOTE: {dep_analysis['nodes_with_commented_count']} nodes have commented-out lines")
        print("  Lines starting with # are comments and are not active dependencies")
        print(f"\n  Example nodes with commented lines:")
        for node_info in dep_analysis['nodes_with_commented_dependencies'][:3]:
            print(f"\n    Node: {node_info['name']} ({node_info['id']})")
            print(f"    Commented deps: {', '.join(node_info['commented_deps'][:3])}")
            if len(node_info['commented_deps']) > 3:
                print(f"      ... and {len(node_info['commented_deps']) - 3} more commented")

    if dep_analysis['nodes_with_pip_commands_count'] > 0:
        print(f"\n\nINFO: {dep_analysis['nodes_with_pip_commands_count']} nodes use pip command flags")
        print("  These are special pip installation flags (starting with --)")
        print("  Common pip commands found:")
        for cmd, count in dep_analysis['sorted_pip_commands'][:5]:
            print(f"    {cmd}: {count} nodes")
        if len(dep_analysis['sorted_pip_commands']) > 5:
            print(f"    ... and {len(dep_analysis['sorted_pip_commands']) - 5} more unique pip commands")

        print(f"\n  Example nodes with pip commands:")
        for node_info in dep_analysis['nodes_with_pip_commands'][:3]:
            print(f"\n    Node: {node_info['name']} ({node_info['id']})")
            print(f"    Pip commands: {', '.join(node_info['pip_commands'][:2])}")
            if len(node_info['pip_commands']) > 2:
                print(f"      ... and {len(node_info['pip_commands']) - 2} more commands")

    if dep_analysis['nodes_with_git_deps_count'] > 0:
        print(f"\n\nGit-based Dependencies: {dep_analysis['nodes_with_git_deps_count']} nodes")
        print("  These dependencies are installed directly from git repositories")

        if dep_analysis['sorted_git_dependency_types']:
            print("  Breakdown by type:")
            for dep_type, count in dep_analysis['sorted_git_dependency_types']:
                print(f"    {dep_type}: {count} dependencies")

        print(f"  Total unique git dependencies: {len(dep_analysis['unique_git_dependencies'])}")

        print(f"\n  Example nodes with git dependencies:")
        for node_info in dep_analysis['nodes_with_git_dependencies'][:3]:
            print(f"\n    Node: {node_info['name']} ({node_info['id']})")
            for git_dep in node_info['git_deps'][:2]:
                print(f"    Git dep: {git_dep}")
            if len(node_info['git_deps']) > 2:
                print(f"      ... and {len(node_info['git_deps']) - 2} more git dependencies")

    # Web directory statistics
    nodes_with_web_dirs = []

    for node_id, node_data in nodes_dict.items():
        web_dirs = node_data.get('_web_directories', [])
        if web_dirs:
            nodes_with_web_dirs.append({
                'id': node_id,
                'name': node_data.get('name', 'N/A'),
                'files': web_dirs,
                'downloads': node_data.get('downloads', 0)
            })

    if nodes_with_web_dirs:
        # Sort by downloads for examples
        nodes_with_web_dirs.sort(key=lambda x: x['downloads'], reverse=True)

        print(f"\n\nWeb Directories: {len(nodes_with_web_dirs)} nodes")
        print("  These nodes have .py files with WEB_DIRECTORY variable")

        print(f"\n  Example nodes with web directories:")
        for node_info in nodes_with_web_dirs[:5]:
            print(f"\n    Node: {node_info['name']} ({node_info['id']})")
            print(f"    Files: {', '.join(node_info['files'])}")

    # Routes statistics
    nodes_with_routes = []

    for node_id, node_data in nodes_dict.items():
        routes = node_data.get('_routes', [])
        if routes:
            nodes_with_routes.append({
                'id': node_id,
                'name': node_data.get('name', 'N/A'),
                'files': routes,
                'downloads': node_data.get('downloads', 0)
            })

    if nodes_with_routes:
        # Sort by downloads for examples
        nodes_with_routes.sort(key=lambda x: x['downloads'], reverse=True)

        print(f"\n\nRoutes: {len(nodes_with_routes)} nodes")
        print("  These nodes have .py files with route-any decorator")

        print(f"\n  Example nodes with routes:")
        for node_info in nodes_with_routes[:5]:
            print(f"\n    Node: {node_info['name']} ({node_info['id']})")
            print(f"    Files: {', '.join(node_info['files'])}")


def main():
    parser = argparse.ArgumentParser(description='Analyze ComfyUI node dependencies')
    parser.add_argument('--execute', '-e', type=str,
                       help='Execute a command as if in interactive mode (e.g., --execute "/summary")')
    args = parser.parse_args()

    # Special handling for /update command when nodes.json doesn't exist
    if args.execute and args.execute.lower() in ['/update', '//update']:
        # Try to run update directly without loading nodes first
        print("\nFetching latest nodes from registry...")
        try:
            registry_data = get_registry_nodes(print_time=True)

            # Save using the shared function
            if not save_nodes_json(registry_data):
                print("Failed to save nodes data")
                return

            # Also fetch and save extension-node-map.json
            fetch_and_save_extension_node_map()
            return
        except Exception as e:
            print(f"Error updating nodes.json: {e}")
            return

    nodes_dict = load_nodes_to_dict()

    if not nodes_dict:
        print("nodes.json not found. Fetching from registry...")
        try:
            registry_data = get_registry_nodes(print_time=True)

            # Save using the shared function
            if save_nodes_json(registry_data):
                # Reload the nodes dictionary
                nodes_dict = load_nodes_to_dict()

                if not nodes_dict:
                    print("Error: Failed to load nodes data even after update")
                    return
            else:
                print("Failed to save nodes data")
                return
        except Exception as e:
            print(f"Error fetching nodes from registry: {e}")
            return

    if args.execute:
        # Execute the command in a modified interactive mode
        execute_command(nodes_dict, args.execute)
    else:
        # Default behavior - interactive mode
        interactive_mode(nodes_dict)


if __name__ == "__main__":
    main()