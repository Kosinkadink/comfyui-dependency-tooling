"""Centralized modifier parsing and filter application.

Modifiers are split into two categories:
- **Filters** narrow the working dataset: top, nodes, include_stats, exclude_stats
- **Display** options affect output rendering: save, all, dupes, sort

The filter pipeline is universal — every command uses apply_all_filters().
"""

import re


def parse_modifiers(query):
    """
    Parse query modifiers and return structured filters + display options.

    Supports:
        &top N / &top -N / &top M:N
        &nodes id1,id2 / &nodes file:path
        &stat name          (include — can repeat)
        &!stat name         (exclude — can repeat)
        &save
        &all
        &dupes
        &sort stat_name

    Returns:
        dict with keys:
            - 'filters': dict with top, nodes, include_stats, exclude_stats
            - 'display': dict with save, all, dupes, sort
            - 'clean_query': str — query with all modifiers stripped
            - 'warnings': list of str — unknown modifier warnings
    """
    result = {
        'filters': {
            'top': None,
            'nodes': None,
            'include_stats': [],
            'exclude_stats': [],
        },
        'display': {
            'save': False,
            'all': False,
            'dupes': False,
            'sort': None,
        },
        'clean_query': query,
        'warnings': [],
    }

    clean = result['clean_query']

    # --- Display options ---

    if '&save' in clean.lower():
        result['display']['save'] = True
        clean = re.sub(r'&save', '', clean, flags=re.IGNORECASE).strip()

    if '&all' in clean.lower():
        result['display']['all'] = True
        clean = re.sub(r'&all', '', clean, flags=re.IGNORECASE).strip()

    if '&dupes' in clean.lower():
        result['display']['dupes'] = True
        clean = re.sub(r'&dupes', '', clean, flags=re.IGNORECASE).strip()

    sort_match = re.search(r'&sort\s+([^\s&]+)', clean, flags=re.IGNORECASE)
    if sort_match:
        result['display']['sort'] = sort_match.group(1).strip().lower()
        clean = re.sub(r'&sort\s+[^\s&]+', '', clean, flags=re.IGNORECASE).strip()

    # --- Filters ---

    # &top (N, -N, or start:end range)
    top_match = re.search(r'&top\s+((\d+):(\d+)|(-?\d+))', clean, flags=re.IGNORECASE)
    if top_match:
        if top_match.group(2):  # Range format
            start = int(top_match.group(2))
            end = int(top_match.group(3))
            result['filters']['top'] = (start, end)
        else:
            result['filters']['top'] = int(top_match.group(4))
        clean = re.sub(r'&top\s+((\d+:\d+)|(-?\d+))', '', clean, flags=re.IGNORECASE).strip()

    # &!stat name (exclude — must parse BEFORE &stat to avoid partial match)
    result['filters']['exclude_stats'] = re.findall(r'&!stat\s+([^\s&]+)', clean, flags=re.IGNORECASE)
    if result['filters']['exclude_stats']:
        result['filters']['exclude_stats'] = [s.lower() for s in result['filters']['exclude_stats']]
        clean = re.sub(r'&!stat\s+[^\s&]+', '', clean, flags=re.IGNORECASE).strip()

    # &stat name (include — can repeat)
    result['filters']['include_stats'] = re.findall(r'&stat\s+([^\s&]+)', clean, flags=re.IGNORECASE)
    if result['filters']['include_stats']:
        result['filters']['include_stats'] = [s.lower() for s in result['filters']['include_stats']]
        clean = re.sub(r'&stat\s+[^\s&]+', '', clean, flags=re.IGNORECASE).strip()

    # &nodes (comma-separated or file:path)
    nodes_match = re.search(r'&nodes\s+([^&]+)', clean, flags=re.IGNORECASE)
    if nodes_match:
        nodes_spec = nodes_match.group(1).strip()
        if nodes_spec.startswith('file:'):
            file_path = nodes_spec[5:].strip()
            try:
                with open(file_path, 'r') as f:
                    result['filters']['nodes'] = [line.strip() for line in f if line.strip()]
            except FileNotFoundError:
                result['warnings'].append(f"File not found: {file_path}")
                result['filters']['nodes'] = []
        else:
            result['filters']['nodes'] = [n.strip() for n in nodes_spec.split(',') if n.strip()]
        clean = re.sub(r'&nodes\s+[^&]+', '', clean, flags=re.IGNORECASE).strip()

    # --- Unknown modifier validation ---
    leftover_modifiers = re.findall(r'&([a-zA-Z!][a-zA-Z0-9_-]*)', clean)
    if leftover_modifiers:
        known = {'save', 'all', 'dupes', 'sort', 'top', 'nodes', 'stat', '!stat'}
        for mod in leftover_modifiers:
            if mod.lower() not in known:
                result['warnings'].append(f"Unknown modifier: &{mod}")
        # Strip unknown modifiers from clean_query so they don't pollute search
        clean = re.sub(r'&[a-zA-Z!][a-zA-Z0-9_-]*(\s+[^\s&]+)?', '', clean).strip()

    result['clean_query'] = clean
    return result


# ---------------------------------------------------------------------------
# Filter application
# ---------------------------------------------------------------------------

def apply_top_filter(nodes_dict, top_value):
    """
    Apply top N filtering to nodes dictionary.

    Returns:
        Tuple of (filtered dict, description string)
    """
    sorted_nodes = sorted(nodes_dict.items(), key=lambda x: x[1].get('downloads', 0), reverse=True)

    if isinstance(top_value, tuple):
        start, end = top_value
        filtered = dict(sorted_nodes[start-1:end])
        desc = f"nodes ranked {start}-{end} by downloads"
    elif top_value > 0:
        filtered = dict(sorted_nodes[:top_value])
        desc = f"top {top_value} nodes by downloads"
    else:
        filtered = dict(sorted_nodes[top_value:])
        desc = f"bottom {abs(top_value)} nodes by downloads"

    return filtered, desc


def apply_all_filters(nodes_dict, mods):
    """
    Apply all filters in the standard order: nodes → top → include_stats → exclude_stats.

    Args:
        nodes_dict: Dictionary of nodes to filter
        mods: Result from parse_modifiers() or build_filters_from_args()

    Returns:
        Tuple of (filtered dict, list of description strings)
    """
    filters = mods['filters']
    working = nodes_dict
    descriptions = []

    # 1. Filter to specific node IDs
    if filters['nodes']:
        working = {nid: ndata for nid, ndata in working.items() if nid in filters['nodes']}
        descriptions.append(f"[Filtering to {len(working)} specific nodes]")

    # 2. Filter to top/bottom/range by downloads
    if filters['top'] is not None:
        working, desc = apply_top_filter(working, filters['top'])
        descriptions.append(f"[Filtering to {desc}]")

    # 3. Include stats (nodes must have ALL specified stats)
    for stat_name in filters['include_stats']:
        working = {
            nid: ndata for nid, ndata in working.items()
            if ndata.get('_stats', {}).get(stat_name)
        }
        display_name = stat_name.replace('-', ' ').replace('_', ' ').title()
        descriptions.append(f"[Filtering to nodes with {display_name}: {len(working)} nodes]")

    # 4. Exclude stats (nodes must NOT have any specified stats)
    for stat_name in filters['exclude_stats']:
        working = {
            nid: ndata for nid, ndata in working.items()
            if not ndata.get('_stats', {}).get(stat_name)
        }
        display_name = stat_name.replace('-', ' ').replace('_', ' ').title()
        descriptions.append(f"[Excluding nodes with {display_name}: {len(working)} remaining]")

    return working, descriptions
