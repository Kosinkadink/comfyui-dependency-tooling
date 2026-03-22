"""Requirements.txt fetching, parsing, updating, and cache management."""

import threading
import concurrent.futures
from pathlib import Path

import requests


def get_raw_file_url(repo_url, filename='requirements.txt'):
    """
    Convert a GitHub repository URL to a raw file URL.

    Returns:
        List of raw file URLs to try, or None if URL format is not recognized
    """
    if not repo_url or repo_url == 'N/A':
        return None

    repo_url = repo_url.rstrip('/').rstrip('.git')

    if 'github.com' in repo_url:
        parts = repo_url.replace('https://github.com/', '').replace('http://github.com/', '')
        return [
            f"https://raw.githubusercontent.com/{parts}/main/{filename}",
            f"https://raw.githubusercontent.com/{parts}/master/{filename}"
        ]

    return None


def fetch_requirements_txt(repo_url, timeout=10):
    """
    Fetch requirements.txt content from a repository.

    Returns:
        Tuple of (success, content, error_message)
    """
    raw_urls = get_raw_file_url(repo_url)

    if not raw_urls:
        return (False, None, "Unsupported repository host")

    for raw_url in raw_urls:
        try:
            response = requests.get(raw_url, timeout=timeout)
            if response.status_code == 200:
                return (True, response.text, None)
        except requests.exceptions.Timeout:
            continue
        except requests.exceptions.RequestException:
            continue

    return (False, None, "requirements.txt not found")


def parse_requirements_txt(content):
    """
    Parse requirements.txt content into a list of dependencies.

    Returns:
        List of dependency strings
    """
    if not content:
        return []

    dependencies = []
    for line in content.split('\n'):
        line = line.strip()

        if not line or line.startswith('#'):
            continue

        if line.startswith('-e '):
            continue

        dependencies.append(line)

    return dependencies


def save_requirements_cache(node_id, content):
    """Save requirements.txt content to cache directory."""
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
    """Load cached requirements.txt content."""
    try:
        cache_file = Path('updated_reqs') / node_id / 'requirements.txt'
        if cache_file.exists():
            with open(cache_file, 'r', encoding='utf-8') as f:
                content = f.read()
            return (True, content)
    except Exception:
        pass

    return (False, None)


def delete_requirements_cache(node_id):
    """Delete cached requirements.txt for a node."""
    try:
        cache_file = Path('updated_reqs') / node_id / 'requirements.txt'
        if cache_file.exists():
            cache_file.unlink()
            try:
                cache_file.parent.rmdir()
            except:
                pass
            return True
    except Exception:
        pass

    return False


def fetch_single_node_requirements(node_id, repo):
    """Fetch requirements.txt for a single node."""
    success, content, error = fetch_requirements_txt(repo)
    return (node_id, success, content, error)


def update_node_requirements(nodes_dict, node_ids, original_deps_backup, max_workers=20, progress_callback=None):
    """
    Fetch and update node dependencies from requirements.txt files concurrently.

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

    print_lock = threading.Lock()

    # Capture original dependencies BEFORE fetching
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
        future_to_node = {
            executor.submit(fetch_single_node_requirements, node_id, repo): node_id
            for node_id, repo in fetch_tasks
        }

        for future in concurrent.futures.as_completed(future_to_node):
            node_id, success, content, error = future.result()
            completed += 1

            ok = success or error == "requirements.txt not found"

            with print_lock:
                print(f"[{completed}/{stats['total']}] {node_id}...", end=' ')

                original_deps = original_json_deps.get(node_id, [])
                node_data = nodes_dict[node_id]

                if ok:
                    if success:
                        new_deps = parse_requirements_txt(content)
                        save_requirements_cache(node_id, content)
                    else:
                        new_deps = []
                        delete_requirements_cache(node_id)

                    if node_id not in original_deps_backup:
                        original_deps_backup[node_id] = {
                            'dependencies': original_deps.copy() if original_deps else []
                        }

                    if 'latest_version' in node_data and node_data['latest_version']:
                        node_data['latest_version']['dependencies'] = new_deps
                        node_data['latest_version']['_updated_from_requirements'] = True

                    stats['success'] += 1
                    stats['updated_nodes'].append(node_id)

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
                    if error == "Unsupported repository host":
                        stats['unsupported'] += 1
                        print(f"SKIP {error}")
                    else:
                        print(f"FAIL {error}")
                    stats['failed'] += 1

            # Call progress callback OUTSIDE the lock to avoid deadlocks with TUI
            if progress_callback:
                progress_callback(completed, stats['total'], node_id, ok)

    return stats
