"""Data loading, rank calculation, missing-nodes mapping, and cached requirements."""

import csv
import os
from pathlib import Path

from .utils import (
    load_extension_node_map,
    load_all_node_stats,
    map_node_ids_to_packs,
)
from .requirements import parse_requirements_txt, load_requirements_cache
from .cache import (
    load_nodes_cache,
    cache_status_str, is_stale,
)


def _nodes_list_to_dict(nodes_list):
    """Convert a list of node dicts to a dict keyed by 'id'."""
    nodes_dict = {}
    for node in nodes_list:
        if 'id' in node:
            nodes_dict[node['id']] = node
    return nodes_dict


def load_nodes_to_dict():
    """
    Load nodes data from cache.

    Returns:
        Dictionary where keys are node IDs and values are the node data
    """
    cached = load_nodes_cache()
    if cached and 'nodes' in cached:
        nodes_dict = _nodes_list_to_dict(cached['nodes'])
        status = cache_status_str()
        print(f"Successfully loaded {len(nodes_dict)} nodes (cache: {status})")
        if is_stale():
            print("[Warning: Data is stale — run /update to refresh]")
        return nodes_dict

    print("No cached data found. Run /update to fetch from registry.")
    return {}


def store_node_ranks(nodes_dict):
    """
    Calculate and store download ranks in each node's data structure.
    This allows graphs to show actual overall ranks even when filtering with &top.

    Args:
        nodes_dict: Dictionary of nodes (modified in-place)
    """
    sorted_nodes = sorted(nodes_dict.items(), key=lambda x: x[1].get('downloads', 0), reverse=True)

    for rank, (node_id, node_data) in enumerate(sorted_nodes, 1):
        node_data['_rank'] = rank


def load_node_ids_data(nodes_dict):
    """
    Load node IDs from extension-node-map cache.

    Returns:
        Number of nodes with node ID data
    """
    from .cache import EXT_MAP_CACHE
    cache_path = str(EXT_MAP_CACHE)
    return load_extension_node_map(nodes_dict, json_file_path=cache_path)


def load_missing_nodes_data(nodes_dict):
    """
    Load missing nodes from CSV files, map them to node packs, and create a
    node-stats compatible CSV file.

    Returns:
        Dictionary mapping node_id -> node_pack_id (or None if not found)
    """
    missing_nodes_path = Path('missing-nodes')
    if not missing_nodes_path.exists() or not missing_nodes_path.is_dir():
        return {}

    csv_files = list(missing_nodes_path.glob('*.csv'))
    if not csv_files:
        return {}

    # Process each CSV file and track which packs are referenced by each entry
    pack_to_entries = {}
    entry_index = 0
    node_id_to_pack = {}

    for csv_file in csv_files:
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    content = row.get('content', '').strip()
                    if not content:
                        continue

                    cleaned = content.strip('[]"\' ')
                    if not cleaned:
                        continue

                    entry_node_ids = [node_id.strip() for node_id in cleaned.split(',')]

                    entry_packs = set()
                    for node_id in entry_node_ids:
                        if node_id not in node_id_to_pack:
                            temp_mapping = map_node_ids_to_packs([node_id], nodes_dict)
                            pack_id = temp_mapping.get(node_id)
                            node_id_to_pack[node_id] = pack_id
                        else:
                            pack_id = node_id_to_pack[node_id]

                        if pack_id is not None:
                            entry_packs.add(pack_id)

                    entry_identifier = f"entry_{entry_index}.py"
                    for pack_id in entry_packs:
                        if pack_id not in pack_to_entries:
                            pack_to_entries[pack_id] = set()
                        pack_to_entries[pack_id].add(entry_identifier)

                    entry_index += 1

        except Exception as e:
            print(f"Warning: Could not process {csv_file}: {e}")
            continue

    if not pack_to_entries:
        return node_id_to_pack

    # Create node-stats/missing-nodes directory
    output_dir = Path('node-stats/missing-nodes')
    output_dir.mkdir(parents=True, exist_ok=True)

    # Delete old CSV files
    old_csv_files = list(output_dir.glob('*.csv'))
    deleted_count = 0
    for old_file in old_csv_files:
        try:
            os.remove(old_file)
            deleted_count += 1
        except Exception as e:
            print(f"Warning: Could not delete {old_file}: {e}")

    if deleted_count > 0:
        print(f"[Deleted {deleted_count} old CSV files from node-stats/missing-nodes/]")

    # Create new CSV file in node-stats format
    output_file = output_dir / 'missing-nodes.csv'

    try:
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['pack_id', 'repository', 'entry_count', 'entry_identifier'])

            for pack_id in sorted(pack_to_entries.keys()):
                pack_data = nodes_dict.get(pack_id, {})
                repo_url = pack_data.get('repository', 'N/A')
                entries = pack_to_entries[pack_id]
                entry_count = len(entries)

                for entry_id in sorted(entries):
                    writer.writerow([pack_id, repo_url, entry_count, entry_id])

        print(f"[Created node-stats CSV: {output_file} with {len(pack_to_entries)} packs]")
    except Exception as e:
        print(f"Warning: Could not create node-stats CSV: {e}")

    return node_id_to_pack


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
                    new_deps = parse_requirements_txt(content)

                    if node_id not in original_deps_backup:
                        node_data = nodes_dict[node_id]
                        if 'latest_version' in node_data and node_data['latest_version']:
                            original_deps_backup[node_id] = {
                                'dependencies': node_data['latest_version'].get('dependencies', []).copy() if node_data['latest_version'].get('dependencies') else []
                            }

                    node_data = nodes_dict[node_id]
                    if 'latest_version' in node_data and node_data['latest_version']:
                        node_data['latest_version']['dependencies'] = new_deps
                        node_data['latest_version']['_updated_from_requirements'] = True
                        count += 1

    return count


def initialize_session(nodes_dict):
    """
    Run all startup data loading steps and return session state.

    Args:
        nodes_dict: Dictionary of nodes (modified in-place with ranks, stats, etc.)

    Returns:
        dict with keys:
            - 'original_deps_backup': dict of original deps before requirements update
            - 'missing_node_mapping': dict mapping node_id -> pack_id
            - 'stat_counts': dict of stat_name -> count
    """
    original_deps_backup = {}

    # Load cached requirements.txt files
    cached_count = load_all_cached_requirements(nodes_dict, original_deps_backup)
    if cached_count > 0:
        print(f"\n[Loaded {cached_count} cached requirements.txt files]")

    # Load node IDs from extension-node-map.json
    node_ids_count = load_node_ids_data(nodes_dict)
    if node_ids_count > 0:
        print(f"[Loaded node IDs for {node_ids_count} nodes]")

    # Load missing nodes (must happen BEFORE load_all_node_stats)
    missing_node_mapping = load_missing_nodes_data(nodes_dict)
    if missing_node_mapping:
        matched_count = sum(1 for pack_id in missing_node_mapping.values() if pack_id is not None)
        unmatched_count = sum(1 for pack_id in missing_node_mapping.values() if pack_id is None)
        print(f"[Loaded {len(missing_node_mapping)} missing nodes: {matched_count} matched to packs, {unmatched_count} unmatched]")

    # Load all node statistics
    stat_counts = load_all_node_stats(nodes_dict, 'node-stats')
    if stat_counts:
        for stat_name, count in stat_counts.items():
            if count > 0:
                display_name = stat_name.replace('-', ' ').replace('_', ' ').title()
                print(f"[Loaded {display_name} data for {count} nodes]")

    return {
        'original_deps_backup': original_deps_backup,
        'missing_node_mapping': missing_node_mapping,
        'stat_counts': stat_counts,
    }
