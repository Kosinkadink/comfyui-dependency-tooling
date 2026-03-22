"""
ComfyUI Dependency Analysis Tool - CLI entry point.

Thin wrapper that wires together the core library modules for interactive
and execute-mode usage.
"""

import argparse

from core.registry import get_registry_nodes, save_nodes_json, fetch_and_save_extension_node_map
from core.data import (
    load_nodes_to_dict, store_node_ranks,
    initialize_session,
)
from core.dependencies import compile_dependencies, analyze_specific_dependency, analyze_wildcard_dependencies
from core.modifiers import parse_modifiers, apply_all_filters
from core.requirements import update_node_requirements
from core.formatters import (
    save_results_to_file, format_dependency_details,
    display_node_dependencies, format_node_list_entry,
    display_summary, print_help,
)


def execute_single_command(nodes_dict, command):
    """Execute a single command directly (no REPL)."""
    session = initialize_session(nodes_dict)
    original_deps_backup = session['original_deps_backup']
    dep_analysis = compile_dependencies(nodes_dict)
    all_deps_lower = {dep.lower(): dep for dep in dep_analysis['unique_base_dependencies']}

    cmd = command.strip()
    if cmd.lower() == '/update':
        _handle_update(nodes_dict)
    elif cmd.lower() == '/summary':
        display_summary(nodes_dict)
    elif cmd.lower() == '/help':
        print_help()
    elif cmd.lower().startswith('/update-reqs'):
        _handle_update_reqs(cmd, nodes_dict, original_deps_backup)
    elif cmd.lower().startswith('/list'):
        _handle_list(cmd, nodes_dict, original_deps_backup)
    elif cmd.lower().startswith('/top'):
        _handle_top(cmd, nodes_dict)
    elif cmd.lower().startswith('/nodes'):
        _handle_nodes(cmd, nodes_dict, original_deps_backup, dep_analysis, all_deps_lower)
    elif cmd:
        _handle_search(cmd, nodes_dict, dep_analysis, all_deps_lower)


def interactive_mode(nodes_dict):
    """Interactive chat loop for dependency queries."""
    print("\n" + "="*60)
    print("INTERACTIVE DEPENDENCY ANALYZER")
    print("="*60)
    print("\nEnter a dependency name to analyze (or use /quit to exit)")

    print_help()

    # Run all startup data loading
    session = initialize_session(nodes_dict)
    original_deps_backup = session['original_deps_backup']

    # Pre-compile all dependencies for quick lookup
    dep_analysis = compile_dependencies(nodes_dict)
    all_deps_lower = {dep.lower(): dep for dep in dep_analysis['unique_base_dependencies']}

    while True:
        try:
            query = input("\n> ").strip()

            if query.lower() in ['/quit', '/exit', '/q']:
                print("Exiting interactive mode.")
                break

            elif query.lower() == '/update':
                _handle_update(nodes_dict)
                # Reload everything after update
                nodes_dict = load_nodes_to_dict()
                store_node_ranks(nodes_dict)
                session = initialize_session(nodes_dict)
                original_deps_backup = session['original_deps_backup']
                dep_analysis = compile_dependencies(nodes_dict)
                all_deps_lower = {dep.lower(): dep for dep in dep_analysis['unique_base_dependencies']}

            elif query.lower() == '/update-reqs' or query.lower().startswith('/update-reqs '):
                _handle_update_reqs(query, nodes_dict, original_deps_backup)

            elif query.lower() == '/summary':
                display_summary(nodes_dict)

            elif query.lower() == '/help':
                print_help()

            elif query.lower() == '/list' or query.lower().startswith('/list '):
                _handle_list(query, nodes_dict, original_deps_backup)

            elif query.lower() == '/top' or query.lower().startswith('/top '):
                _handle_top(query, nodes_dict)

            elif query.lower() == '/nodes' or query.lower().startswith('/nodes '):
                _handle_nodes(query, nodes_dict, original_deps_backup, dep_analysis, all_deps_lower)

            elif query:
                _handle_search(query, nodes_dict, dep_analysis, all_deps_lower)

        except KeyboardInterrupt:
            print("\n\nInterrupted. Exiting interactive mode.")
            break
        except Exception as e:
            print(f"Error: {e}")


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _handle_update(nodes_dict):
    """Handle the /update command."""
    print("\nFetching latest nodes from registry...")
    try:
        registry_data = get_registry_nodes(print_time=True)
        if save_nodes_json(registry_data):
            fetch_and_save_extension_node_map()
            print("Nodes data has been refreshed and is ready for analysis.")
        else:
            print("Failed to save nodes data")
    except Exception as e:
        print(f"Error updating nodes.json: {e}")


def _handle_update_reqs(query, nodes_dict, original_deps_backup):
    """Handle the /update-reqs command."""
    mods = parse_modifiers(query)
    _print_warnings(mods)
    working_nodes, descriptions = apply_all_filters(nodes_dict, mods)
    for desc in descriptions:
        print(f"\n{desc}")

    node_ids = list(working_nodes.keys())
    if not node_ids:
        print("\nNo nodes to update.")
        return

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


def _handle_list(query, nodes_dict, original_deps_backup):
    """Handle the /list command."""
    mods = parse_modifiers(query)
    _print_warnings(mods)
    working_nodes, descriptions = apply_all_filters(nodes_dict, mods)
    for desc in descriptions:
        print(f"\n{desc}")

    # Re-compile dependencies for the filtered set
    filtered_dep_analysis = compile_dependencies(working_nodes)

    if mods['display']['dupes']:
        _display_list_dupes(working_nodes, filtered_dep_analysis, mods, query)
    else:
        _display_list_normal(filtered_dep_analysis, mods, query)


def _display_list_dupes(working_nodes, filtered_dep_analysis, mods, original_query):
    """Display /list &dupes output."""
    dupes_only = []
    non_dupes = []

    for dep_name, versions in filtered_dep_analysis['dependency_versions'].items():
        count = filtered_dep_analysis['dependency_count'].get(dep_name, 0)
        if len(versions) > 1:
            dupes_only.append((dep_name, count, versions))
        else:
            non_dupes.append((dep_name, count, list(versions)[0] if versions else '*'))

    dupes_only.sort(key=lambda x: (-x[1], x[0].lower()))
    non_dupes.sort(key=lambda x: (-x[1], x[0].lower()))

    output_lines = []

    top_n = mods['filters']['top']
    qualifier = _top_qualifier(top_n)
    if qualifier:
        output_lines.append(f"\nDEPENDENCIES WITH MULTIPLE VERSIONS in {qualifier} ({len(dupes_only)} total):")
    else:
        output_lines.append(f"\nDEPENDENCIES WITH MULTIPLE VERSIONS ({len(dupes_only)} total):")

    output_lines.append("="*60)

    for dep_name, count, versions in dupes_only:
        output_lines.append(f"\n{dep_name} ({count} nodes total, {len(versions)} different specs):")
        version_list = list(versions)
        version_counts = []
        for v in version_list:
            v_count = sum(1 for node_id, node_data in working_nodes.items()
                        if 'latest_version' in node_data and node_data['latest_version']
                        and 'dependencies' in node_data['latest_version']
                        and any(str(d).strip() == v for d in node_data['latest_version']['dependencies']))
            version_counts.append((v, v_count))

        version_counts.sort(key=lambda x: -x[1])
        for v, v_count in version_counts:
            output_lines.append(f"  {v:40} ({v_count} nodes)")

    if non_dupes:
        output_lines.append("")
        if qualifier:
            output_lines.append(f"\nDEPENDENCIES WITH SINGLE VERSION in {qualifier} ({len(non_dupes)} total):")
        else:
            output_lines.append(f"\nDEPENDENCIES WITH SINGLE VERSION ({len(non_dupes)} total):")
        output_lines.append("="*60)

        for dep_name, count, version_spec in non_dupes:
            output_lines.append(f"{dep_name:40} ({count:3} nodes) - {version_spec}")

    output_text = '\n'.join(output_lines)
    print(output_text)

    if mods['display']['save']:
        save_results_to_file("list_dupes_" + original_query.replace('/list', '').strip(), output_text)


def _display_list_normal(filtered_dep_analysis, mods, original_query):
    """Display normal /list output."""
    deps_with_counts = [(dep, filtered_dep_analysis['dependency_count'].get(dep, 0))
                       for dep in filtered_dep_analysis['unique_base_dependencies']]
    deps_with_counts.sort(key=lambda x: x[0].lower())

    top_n = mods['filters']['top']
    qualifier = _top_qualifier(top_n)
    if qualifier:
        print(f"\nUnique package names in {qualifier} ({len(deps_with_counts)} total):")
    else:
        print(f"\nAll unique package names ({len(deps_with_counts)} total):")
    print("(Versions are grouped together under base package names)")
    print("(Number in parentheses shows how many nodes use this dependency)")

    for i in range(0, len(deps_with_counts), 2):
        row = deps_with_counts[i:i+2]
        print("  " + " | ".join(f"{dep:30} ({count:3})" for dep, count in row))

    if mods['display']['save']:
        output_lines = []
        if qualifier:
            output_lines.append(f"Unique package names in {qualifier} ({len(deps_with_counts)} total):")
        else:
            output_lines.append(f"All unique package names ({len(deps_with_counts)} total):")
        output_lines.append("(Versions are grouped together under base package names)")
        output_lines.append("(Number in parentheses shows how many nodes use this dependency)\n")

        for dep, count in deps_with_counts:
            output_lines.append(f"{dep:40} ({count:3})")

        save_text = '\n'.join(output_lines)
        save_results_to_file("list_" + original_query.replace('/list', '').strip(), save_text)


def _handle_top(query, nodes_dict):
    """Handle the /top command."""
    mods = parse_modifiers(query)
    _print_warnings(mods)
    working_nodes, descriptions = apply_all_filters(nodes_dict, mods)
    for desc in descriptions:
        print(f"\n{desc}")

    filtered_dep_analysis = compile_dependencies(working_nodes)

    qualifier = _top_qualifier(mods['filters']['top'])
    if qualifier:
        print(f"\nTop 20 most common dependencies in {qualifier}:")
    else:
        print("\nTop 20 most common dependencies:")
    for dep, count in filtered_dep_analysis['sorted_by_frequency'][:20]:
        print(f"  {dep:30} - {count} nodes")


def _handle_nodes(query, nodes_dict, original_deps_backup, dep_analysis, all_deps_lower):
    """Handle the /nodes command."""
    node_search = query[6:].strip() if len(query) > 6 else ""
    original_query = query

    mods = parse_modifiers(node_search)
    _print_warnings(mods)
    node_search = mods['clean_query']

    # If there's a node name/ID remaining after stripping modifiers, search for it
    if node_search:
        _handle_node_search(node_search, nodes_dict, original_deps_backup)
        return

    # No node name specified, show the list
    mods_full = parse_modifiers(query)
    working_nodes, descriptions = apply_all_filters(nodes_dict, mods_full)
    for desc in descriptions:
        print(f"\n{desc}")

    # Sort by custom stat or by downloads
    sort_stat = mods_full['display']['sort']
    if sort_stat:
        def get_stat_count(node_item):
            node_id, node_data = node_item
            stat_data = node_data.get('_stats', {}).get(sort_stat, [])
            return len(stat_data) if stat_data else 0

        sorted_nodes = sorted(working_nodes.items(), key=get_stat_count, reverse=True)
        sort_display = sort_stat.replace('-', ' ').replace('_', ' ').title()
        print(f"\n[Sorting by: {sort_display}]")
    else:
        sorted_nodes = sorted(working_nodes.items(), key=lambda x: x[1].get('downloads', 0), reverse=True)

    show_all = mods_full['display']['all']
    nodes_to_display = sorted_nodes if show_all else sorted_nodes[:20]

    # Build output
    output_lines = []
    sort_criteria = sort_stat.replace('-', ' ').replace('_', ' ').title() if sort_stat else "downloads"

    top_value = mods_full['filters']['top']
    if top_value:
        if isinstance(top_value, tuple):
            start, end = top_value
            output_lines.append(f"\nNodes ranked {start}-{end} by {sort_criteria}:")
        elif top_value > 0:
            output_lines.append(f"\nTop {min(len(nodes_to_display), top_value)} nodes by {sort_criteria}:")
        else:
            output_lines.append(f"\nBottom {min(len(nodes_to_display), abs(top_value))} nodes by {sort_criteria}:")
    elif show_all:
        output_lines.append(f"\nAll {len(nodes_to_display)} nodes by {sort_criteria}:")
    else:
        output_lines.append(f"\nTop {min(len(nodes_to_display), 20)} nodes by {sort_criteria}:")

    output_lines.append("="*60)

    for i, (node_id, node_data) in enumerate(nodes_to_display, 1):
        entry_lines = format_node_list_entry(i, node_id, node_data, original_deps_backup)
        output_lines.extend(entry_lines)

    if not show_all and len(sorted_nodes) > 20:
        output_lines.append(f"\n... and {len(sorted_nodes) - 20} more nodes")
        output_lines.append("Use &all to see all nodes")

    output_text = '\n'.join(output_lines)
    print(output_text)

    if mods_full['display']['save']:
        save_lines = []
        qualifier = _top_qualifier(top_value)
        if qualifier:
            save_lines.append(f"All {len(sorted_nodes)} nodes (filtered to {qualifier}):")
        else:
            save_lines.append(f"All {len(sorted_nodes)} nodes by downloads:")
        save_lines.append("="*60)

        for i, (node_id, node_data) in enumerate(sorted_nodes, 1):
            entry_lines = format_node_list_entry(i, node_id, node_data, original_deps_backup)
            save_lines.extend(entry_lines)

        save_text = '\n'.join(save_lines)
        save_results_to_file("nodes_" + original_query.replace('/nodes', '').strip(), save_text)


def _handle_node_search(node_search, nodes_dict, original_deps_backup):
    """Handle /nodes <search_term> - finding and displaying a specific node."""
    auto_select_first = node_search.endswith('!')
    if auto_select_first:
        node_search = node_search[:-1].strip()

    node_search_lower = node_search.lower()

    # Try exact match first
    if node_search_lower in nodes_dict:
        display_node_dependencies(nodes_dict, node_search_lower, original_deps_backup)
        return
    if node_search in nodes_dict:
        display_node_dependencies(nodes_dict, node_search, original_deps_backup)
        return

    # Try starts-with match
    starts_with_matches = [node_id for node_id in nodes_dict.keys()
                          if node_id.lower().startswith(node_search_lower)]

    if starts_with_matches:
        starts_with_sorted = sorted(starts_with_matches,
                                   key=lambda x: nodes_dict[x].get('downloads', 0),
                                   reverse=True)

        if auto_select_first:
            selected_node = starts_with_sorted[0]
            print(f"\n[Auto-selected: {selected_node}]")
            display_node_dependencies(nodes_dict, selected_node, original_deps_backup)
        else:
            print(f"\nNo exact match for '{node_search}'. Found {len(starts_with_matches)} nodes starting with '{node_search}':\n")
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
        return

    # Try substring match
    partial_matches = [node_id for node_id in nodes_dict.keys()
                      if node_search_lower in node_id.lower()]

    if partial_matches:
        partial_sorted = sorted(partial_matches,
                               key=lambda x: nodes_dict[x].get('downloads', 0),
                               reverse=True)

        if auto_select_first:
            selected_node = partial_sorted[0]
            print(f"\n[Auto-selected: {selected_node}]")
            display_node_dependencies(nodes_dict, selected_node, original_deps_backup)
        else:
            print(f"\nNo nodes starting with '{node_search}'. Found {len(partial_matches)} containing '{node_search}':\n")
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


def _handle_search(query, nodes_dict, dep_analysis, all_deps_lower):
    """Handle direct dependency search queries."""
    original_query = query
    mods = parse_modifiers(query)
    _print_warnings(mods)
    working_nodes = nodes_dict

    # Apply all filters uniformly
    working_nodes, descriptions = apply_all_filters(working_nodes, mods)
    for desc in descriptions:
        print(f"\n{desc}")

    # Re-compile if we filtered
    if mods['filters']['top'] is not None or mods['filters']['nodes'] or mods['filters']['include_stats'] or mods['filters']['exclude_stats']:
        dep_analysis = compile_dependencies(working_nodes)
        all_deps_lower = {dep.lower(): dep for dep in dep_analysis['unique_base_dependencies']}

    search_query = mods['clean_query']

    if '*' in search_query:
        _handle_wildcard_search(search_query, working_nodes, mods, original_query)
    else:
        _handle_exact_search(search_query, working_nodes, dep_analysis, all_deps_lower, mods, original_query)


def _handle_wildcard_search(pattern, working_nodes, mods, original_query):
    """Handle wildcard dependency searches."""
    print(f"\nSearching for dependencies matching pattern: {pattern}")
    wildcard_results = analyze_wildcard_dependencies(working_nodes, pattern)

    if not wildcard_results:
        print(f"\nNo dependencies found matching pattern '{pattern}'")
        return

    sorted_results = sorted(wildcard_results.items(),
                          key=lambda x: x[1]['total_nodes'],
                          reverse=True)

    output_lines = []
    output_lines.append(f"\nFound {len(wildcard_results)} dependencies matching '{pattern}':")
    output_lines.append("="*60)

    total_nodes = sum(info['total_nodes'] for _, info in wildcard_results.items())
    output_lines.append(f"Total nodes using any matching dependency: {total_nodes}")

    for dep_name, dep_info in sorted_results:
        if mods['display']['all']:
            output_lines.append(format_dependency_details(dep_info, show_all_nodes=True))
        else:
            output_lines.append(f"\n{'='*50}")
            output_lines.append(f"Dependency: {dep_name}")
            output_lines.append(f"{'='*50}")
            output_lines.append(f"Total nodes using this dependency: {dep_info['total_nodes']}")

            if dep_info['commented_count'] > 0:
                output_lines.append(f"Nodes with commented-out lines: {dep_info['commented_count']}")

            if dep_info['total_nodes'] > 0:
                if len(dep_info['sorted_versions']) > 0:
                    output_lines.append(f"\nVersion specifications found:")
                    for version, count in dep_info['sorted_versions'][:5]:
                        output_lines.append(f"  {version:20} - {count} nodes")
                    if len(dep_info['sorted_versions']) > 5:
                        output_lines.append(f"  ... and {len(dep_info['sorted_versions']) - 5} more versions")

                sorted_nodes = sorted(dep_info['nodes_using'],
                                    key=lambda x: x.get('downloads', 0),
                                    reverse=True)

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

    output_text = '\n'.join(output_lines)
    print(output_text)

    if mods['display']['save']:
        save_lines = []
        save_lines.append(f"Found {len(wildcard_results)} dependencies matching '{pattern}':")
        save_lines.append("="*60)
        save_lines.append(f"Total nodes using any matching dependency: {total_nodes}")

        for dep_name, dep_info in sorted_results:
            save_lines.append(format_dependency_details(dep_info, show_all_nodes=True))

        save_text = '\n'.join(save_lines)
        save_results_to_file(original_query, save_text)


def _handle_exact_search(search_query, working_nodes, dep_analysis, all_deps_lower, mods, original_query):
    """Handle exact dependency searches."""
    query_lower = search_query.lower()
    exact_match = all_deps_lower.get(query_lower)

    if exact_match:
        result = analyze_specific_dependency(working_nodes, exact_match)
        output_text = format_dependency_details(result, show_all_nodes=mods['display']['all'])
        print(output_text)

        if mods['display']['save']:
            full_output = format_dependency_details(result, show_all_nodes=True)
            save_results_to_file(original_query, full_output)
    else:
        # Try starts-with match
        starts_with_matches = [dep for dep_lower, dep in all_deps_lower.items()
                             if dep_lower.startswith(query_lower)]

        if starts_with_matches:
            print(f"\nNo exact match for '{search_query}'. Found {len(starts_with_matches)} dependencies starting with '{search_query}':\n")

            starts_with_sorted = sorted(starts_with_matches,
                                      key=lambda x: dep_analysis['dependency_count'].get(x, 0),
                                      reverse=True)

            show_limit = len(starts_with_sorted) if len(starts_with_sorted) <= 20 else 20

            for match in starts_with_sorted[:show_limit]:
                count = dep_analysis['dependency_count'].get(match, 0)
                print(f"  - {match:40} ({count} nodes)")

            if len(starts_with_sorted) > show_limit:
                print(f"\n  ... and {len(starts_with_sorted) - show_limit} more dependencies starting with '{search_query}'")
                print(f"  (Showing top {show_limit} by usage)")

            print(f"\nTo analyze any of these, type the full dependency name.")
        else:
            # Try substring match
            partial_matches = [dep for dep_lower, dep in all_deps_lower.items()
                             if query_lower in dep_lower]

            if partial_matches:
                print(f"\nNo dependencies starting with '{search_query}'. Found {len(partial_matches)} containing '{search_query}':")

                partial_sorted = sorted(partial_matches[:20],
                                      key=lambda x: dep_analysis['dependency_count'].get(x, 0),
                                      reverse=True)

                for match in partial_sorted[:10]:
                    count = dep_analysis['dependency_count'].get(match, 0)
                    print(f"  - {match:40} ({count} nodes)")
                if len(partial_matches) > 10:
                    print(f"  ... and {len(partial_matches) - 10} more matches containing '{search_query}'")
            else:
                print(f"\nNo dependency found matching '{search_query}'")
                print("Use 'list' to see all available dependencies")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_warnings(mods):
    """Print any modifier parsing warnings."""
    for warning in mods.get('warnings', []):
        print(f"[Warning: {warning}]")


def _top_qualifier(top_value):
    """Return a human-readable qualifier string for a top filter value, or None."""
    if top_value is None:
        return None
    if isinstance(top_value, tuple):
        start, end = top_value
        return f"nodes ranked {start}-{end} by downloads"
    if top_value > 0:
        return f"top {top_value} nodes by downloads"
    return f"bottom {abs(top_value)} nodes by downloads"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Analyze ComfyUI node dependencies')
    parser.add_argument('--execute', '-e', type=str,
                       help='Execute a single command')
    args = parser.parse_args()

    nodes_dict = load_nodes_to_dict()

    if not nodes_dict:
        print("No cached data. Fetching from registry...")
        registry_data = get_registry_nodes(print_time=True)
        if not save_nodes_json(registry_data):
            print("Failed to save nodes data")
            return
        fetch_and_save_extension_node_map()
        nodes_dict = load_nodes_to_dict()
        if not nodes_dict:
            print("Error: Failed to load nodes data")
            return

    store_node_ranks(nodes_dict)

    if args.execute:
        execute_single_command(nodes_dict, args.execute)
    else:
        interactive_mode(nodes_dict)


if __name__ == "__main__":
    main()
