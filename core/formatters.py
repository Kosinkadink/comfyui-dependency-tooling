"""Plain-text output formatting for all commands."""

from datetime import datetime

from .utils import parse_dependency_string, get_all_stat_names, create_timestamped_filepath

from .dependencies import compile_dependencies


def save_results_to_file(query, results_text):
    """Save search results to a timestamped file in the results directory."""
    filepath = create_timestamped_filepath(query, '.txt')

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

        sorted_nodes = sorted(result['nodes_using'],
                            key=lambda x: x.get('downloads', 0),
                            reverse=True)

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


def display_node_dependencies(nodes_dict, node_id, original_deps_backup=None):
    """Display detailed dependency information for a specific node."""
    node_data = nodes_dict[node_id]

    rank = node_data.get('_rank', 'N/A')

    name = node_data.get('name', 'N/A')
    downloads = node_data.get('downloads', 0)
    stars = node_data.get('github_stars', 0)
    repo = node_data.get('repository', 'N/A')
    description = node_data.get('description', 'N/A')

    print(f"\n{'='*60}")
    print(f"Node: {name}")
    print(f"{'='*60}")
    print(f"ID: {node_id}")
    print(f"Rank: #{rank} | Downloads: {downloads:,} | Stars: {stars:,}")
    print(f"Repository: {repo}")
    print(f"Description: {description}")

    node_ids = node_data.get('_node_ids', [])
    has_pattern = node_data.get('_has_node_pattern', False)

    if node_ids or has_pattern:
        asterisk = '*' if has_pattern else ''
        node_count = len(node_ids) if node_ids else 0
        if has_pattern and node_count == 0:
            print(f"Individual Nodes: * (pattern-based)")
        else:
            print(f"Individual Nodes: {node_count}{asterisk}")

    latest_version_info = node_data.get('latest_version', {})
    if latest_version_info:
        version = latest_version_info.get('version', 'N/A')
        latest_date = 'N/A'
        if 'createdAt' in latest_version_info:
            date_str = latest_version_info['createdAt']
            latest_date = date_str[:10] if date_str else 'N/A'

        print(f"Latest Version: {version} | Released: {latest_date}")

        # Display all stats information
        node_stats = node_data.get('_stats', {})
        if node_stats:
            for stat_name in sorted(node_stats.keys()):
                stat_files = node_stats[stat_name]
                if stat_files:
                    display_name = stat_name.replace('-', ' ').replace('_', ' ').title()
                    print(f"\n{display_name}:")
                    print("-" * 60)
                    for file_path in stat_files:
                        print(f"  - {file_path}")

        # Check if dependencies were updated from requirements.txt
        is_updated = latest_version_info.get('_updated_from_requirements', False)

        if is_updated:
            print(f"\n[Dependencies updated from requirements.txt]")

            if original_deps_backup and node_id in original_deps_backup:
                original_deps = original_deps_backup[node_id].get('dependencies', [])
                current_deps = latest_version_info.get('dependencies', []) or []

                if set(original_deps) != set(current_deps):
                    orig_count = len(original_deps)
                    curr_count = len(current_deps)

                    if orig_count == 0 and curr_count > 0:
                        print(f"[MISMATCH: JSON had no dependencies, requirements.txt has {curr_count}]")
                    elif orig_count > 0 and curr_count == 0:
                        print(f"[MISMATCH: JSON had {orig_count} dependencies, requirements.txt has none]")
                    elif orig_count != curr_count:
                        print(f"[MISMATCH: JSON had {orig_count} dependencies, requirements.txt has {curr_count}]")
                    else:
                        print(f"[MISMATCH: Different dependencies (both have {orig_count})]")

        # Parse and display dependencies
        if 'dependencies' in latest_version_info and latest_version_info['dependencies']:
            deps = latest_version_info['dependencies']

            active_deps = []
            commented_deps = []
            pip_commands = []
            git_deps = []

            for dep in deps:
                parsed = parse_dependency_string(dep)

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

            if active_deps:
                print(f"\nActive Dependencies ({len(active_deps)}):")
                print("-" * 60)
                for i, dep in enumerate(active_deps, 1):
                    print(f"  {i}. {dep}")
            else:
                print(f"\nNo active dependencies")

            if git_deps:
                print(f"\nGit-based Dependencies ({len(git_deps)}):")
                print("-" * 60)
                for i, dep in enumerate(git_deps, 1):
                    print(f"  {i}. {dep}")

            if pip_commands:
                print(f"\nPip Command Flags ({len(pip_commands)}):")
                print("-" * 60)
                for i, cmd in enumerate(pip_commands, 1):
                    print(f"  {i}. {cmd}")

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


def format_node_list_entry(i, node_id, node_data, original_deps_backup=None):
    """
    Format a single node entry for the /nodes list display.

    Returns:
        List of output lines
    """
    lines = []

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

    # Get individual nodes count
    node_ids = node_data.get('_node_ids', [])
    node_count = len(node_ids) if node_ids else 0
    has_node_pattern = node_data.get('_has_node_pattern', False)

    # Build stat indicators dynamically
    stat_indicators = []
    node_stats = node_data.get('_stats', {})
    for stat_name in sorted(node_stats.keys()):
        stat_count = len(node_stats[stat_name])
        if stat_count > 0:
            display_name = stat_name.replace('-', ' ').replace('_', ' ').title()
            stat_indicators.append(f"{display_name}: {stat_count}")

    # Format output
    rank = node_data.get('_rank', 'N/A')
    asterisk = "*" if has_mismatch else ""
    stats_str = " | ".join(stat_indicators) if stat_indicators else ""
    stats_indicator = f" | {stats_str}" if stats_str else ""

    if node_count > 0 or has_node_pattern:
        node_pattern_asterisk = "*" if has_node_pattern else ""
        nodes_indicator = f" | Nodes: {node_count}{node_pattern_asterisk}"
    else:
        nodes_indicator = ""

    lines.append(f"\n{i}. {name} ({node_id})")
    lines.append(f"   Rank: #{rank} | Downloads: {downloads:,} | Stars: {stars:,} | Dependencies: {dep_count}{asterisk}{stats_indicator}{nodes_indicator}")
    lines.append(f"   Latest: {latest_date} | Version: {version}")
    if len(description) > 100:
        lines.append(f"   Description: {description[:100]}...")
    else:
        lines.append(f"   Description: {description}")
    lines.append(f"   Repository: {repo}")

    return lines


def display_summary(nodes_dict):
    """Display the summary of nodes and dependencies."""
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

    # Display statistics for all discovered stats
    all_stat_names = get_all_stat_names(nodes_dict)

    for stat_name in all_stat_names:
        nodes_with_stat = []

        for node_id, node_data in nodes_dict.items():
            stat_files = node_data.get('_stats', {}).get(stat_name, [])
            if stat_files:
                nodes_with_stat.append({
                    'id': node_id,
                    'name': node_data.get('name', 'N/A'),
                    'files': stat_files,
                    'downloads': node_data.get('downloads', 0)
                })

        if nodes_with_stat:
            nodes_with_stat.sort(key=lambda x: x['downloads'], reverse=True)
            display_name = stat_name.replace('-', ' ').replace('_', ' ').title()

            print(f"\n\n{display_name}: {len(nodes_with_stat)} nodes")

            print(f"\n  Example nodes with {display_name.lower()}:")
            for node_info in nodes_with_stat[:5]:
                print(f"\n    Node: {node_info['name']} ({node_info['id']})")
                print(f"    Files: {', '.join(node_info['files'])}")


def print_help():
    """Print help information for commands and modifiers."""
    print("\nCommands:")
    print("  /list  - Show all unique dependency names")
    print("  /top   - Show the most common dependencies")
    print("  /nodes - Show details about nodes (sorted by downloads)")
    print("  /nodes <node_id> - Show detailed dependency info for a specific node")
    print("  /nodes <search>! - Auto-select first matching node (fuzzy search)")
    print("  /update - Fetch latest nodes from registry and update cache")
    print("  /update-reqs - Fetch actual dependencies from requirements.txt")
    print("  /summary - Show overall dependency analysis summary")
    print("  /help  - Show this help message")
    print("  /quit  - Exit interactive mode")
    print("\nFilter modifiers (work on all commands):")
    print("  &top N - Filter to top N nodes by downloads")
    print("         Use negative for bottom N (e.g., &top -10)")
    print("         Use range for specific ranks (e.g., &top 10:20)")
    print("  &nodes - Filter by specific node IDs")
    print("         Comma-separated: &nodes id1,id2")
    print("         From file: &nodes file:nodelist.txt")
    print("  &stat <name> - Include only nodes with a stat")
    print("         Can repeat: &stat routes &stat web-dirs (AND logic)")
    print("  &!stat <name> - Exclude nodes with a stat")
    print("         Example: /nodes &!stat web-dirs &top 50")
    print("\nDisplay modifiers:")
    print("  &save - Save results to file")
    print("  &all - Show all results without limits")
    print("  &dupes - Show dependencies with version conflicts (with /list)")
    print("  &sort <stat> - Sort by stat count instead of downloads")
    print("  * - Wildcard search (e.g., torch*, *audio*)")
    print("\nExamples:")
    print("  numpy &top 50 &save")
    print("  /list &dupes &stat web-dirs &top 100")
    print("  /nodes &!stat pip-calls &top 20")
    print("  /top &stat routes")
    print("\nOr type a dependency name directly (e.g., numpy, torch)")
