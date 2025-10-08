import json
import argparse
import re
import fnmatch
from pathlib import Path
from collections import defaultdict


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
    commented_dependencies = []
    pip_commands = []
    pip_command_count = defaultdict(int)

    for node_id, node_data in nodes_dict.items():
        if 'latest_version' in node_data and node_data['latest_version']:
            latest_version = node_data['latest_version']

            if 'dependencies' in latest_version:
                deps = latest_version['dependencies']

                if deps and isinstance(deps, list) and len(deps) > 0:
                    active_deps = []
                    commented_deps = []
                    node_pip_commands = []

                    for dep in deps:
                        dep_str = str(dep).strip()

                        # Check for pip commands (starting with --)
                        if dep_str.startswith('--'):
                            node_pip_commands.append(dep_str)
                            pip_commands.append(dep_str)
                            pip_command_count[dep_str] += 1
                        # Check for commented dependencies
                        elif dep_str.startswith('#'):
                            commented_deps.append(dep_str)
                            commented_dependencies.append(dep_str)
                        else:
                            # Regular dependency
                            active_deps.append(dep_str)
                            all_dependencies_raw.append(dep_str)

                            # Extract base package name (before version specifiers)
                            dep_lower = dep_str.lower()
                            base_name = re.split(r'[<>=!~]', dep_lower)[0].strip()

                            # Count by base name
                            base_dependency_count[base_name] += 1

                            # Track the full version spec
                            dependency_versions[base_name].add(dep_str)

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
        'commented_dependencies': commented_dependencies,
        'unique_commented_dependencies': unique_commented,
        'total_dependencies': len(all_dependencies_raw),
        'unique_count': len(unique_base_dependencies),  # Count of unique base packages
        'unique_raw_count': len(unique_dependencies_raw),  # Count of unique raw specs
        'nodes_with_deps_count': len(nodes_with_deps),
        'nodes_without_deps_count': len(nodes_without_deps),
        'nodes_with_commented_count': len(nodes_with_commented_deps)
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
                    dep_str = str(dep).strip()
                    if not dep_str.startswith('#'):
                        dep_lower = dep_str.lower()
                        base_name = re.split(r'[<>=!~]', dep_lower)[0].strip()
                        all_base_deps.add(base_name)

    # Find dependencies matching the pattern
    for base_dep in all_base_deps:
        if fnmatch.fnmatch(base_dep, pattern_lower):
            # Analyze each matching dependency
            dep_info = analyze_specific_dependency(nodes_dict, base_dep)
            matching_deps[base_dep] = dep_info

    return matching_deps


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

    for node_id, node_data in nodes_dict.items():
        if 'latest_version' in node_data and node_data['latest_version']:
            latest_version = node_data['latest_version']

            if 'dependencies' in latest_version and latest_version['dependencies']:
                for dep in latest_version['dependencies']:
                    dep_str = str(dep).strip()

                    # Check if it's commented
                    if dep_str.startswith('#'):
                        # Check if this commented dependency matches our search
                        commented_content = dep_str[1:].strip()
                        commented_lower = commented_content.lower()
                        base_name = re.split(r'[<>=!~]', commented_lower)[0].strip()

                        if base_name == dep_name_lower:
                            nodes_with_commented.append({
                                'node_id': node_id,
                                'node_name': node_data.get('name', 'N/A'),
                                'commented_spec': dep_str
                            })
                        continue  # Skip commented dependencies for main analysis

                    # Parse dependency string (could be just name or name with version)
                    dep_lower = dep_str.lower()

                    # Extract base name (before any version specifier)
                    base_name = re.split(r'[<>=!~]', dep_lower)[0].strip()

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

                        nodes_using.append({
                            'node_id': node_id,
                            'node_name': node_data.get('name', 'N/A'),
                            'repository': node_data.get('repository', 'N/A'),
                            'dependency_spec': dep_str,
                            'stars': node_data.get('github_stars', 0),
                            'downloads': node_data.get('downloads', 0),
                            'latest_version_date': latest_version_date
                        })

                        # Extract version if present
                        version_match = re.search(r'[<>=!~]+(.+)', dep_str)
                        if version_match:
                            version_spec = dep_str[len(base_name):].strip()
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


def interactive_mode(nodes_dict):
    """
    Interactive chat loop for dependency queries.
    """
    print("\n" + "="*60)
    print("INTERACTIVE DEPENDENCY ANALYZER")
    print("="*60)
    print("\nEnter a dependency name to analyze (or 'quit' to exit)")
    print("You can also use 'list' to see all unique dependencies")
    print("or 'top' to see the most common dependencies\n")

    # Pre-compile all dependencies for quick lookup
    dep_analysis = compile_dependencies(nodes_dict)
    # Use unique base dependencies instead of raw unique dependencies
    all_deps_lower = {dep.lower(): dep for dep in dep_analysis['unique_base_dependencies']}

    while True:
        try:
            query = input("\n> ").strip()

            if query.lower() in ['quit', 'exit', 'q']:
                print("Exiting interactive mode.")
                break

            elif query.lower() == 'list':
                sorted_deps = sorted(dep_analysis['unique_base_dependencies'], key=str.lower)
                print(f"\nAll unique package names ({len(sorted_deps)} total):")
                print("(Versions are grouped together under base package names)")
                # Print in columns for readability
                for i in range(0, len(sorted_deps), 3):
                    row = sorted_deps[i:i+3]
                    print("  " + " | ".join(f"{dep:30}" for dep in row))

            elif query.lower() == 'top':
                print("\nTop 20 most common dependencies:")
                for dep, count in dep_analysis['sorted_by_frequency'][:20]:
                    print(f"  {dep:30} - {count} nodes")

            elif query:
                # Check if query contains wildcard
                if '*' in query:
                    print(f"\nSearching for dependencies matching pattern: {query}")
                    wildcard_results = analyze_wildcard_dependencies(nodes_dict, query)

                    if wildcard_results:
                        # Sort by total nodes using each dependency
                        sorted_results = sorted(wildcard_results.items(),
                                              key=lambda x: x[1]['total_nodes'],
                                              reverse=True)

                        print(f"\nFound {len(wildcard_results)} dependencies matching '{query}':")
                        print("="*60)

                        total_nodes = sum(info['total_nodes'] for _, info in wildcard_results.items())
                        print(f"Total nodes using any matching dependency: {total_nodes}")

                        for dep_name, dep_info in sorted_results:
                            print(f"\n{dep_name}: {dep_info['total_nodes']} nodes")
                            if dep_info['commented_count'] > 0:
                                print(f"  WARNING: {dep_info['commented_count']} nodes have it commented")

                            # Show version distribution for this dependency
                            if dep_info['sorted_versions'][:3]:
                                print(f"  Top versions:")
                                for version, count in dep_info['sorted_versions'][:3]:
                                    print(f"    {version:20} - {count} nodes")

                        print("\n" + "="*60)
                        print("To see details for a specific dependency, type its full name.")
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
                        result = analyze_specific_dependency(nodes_dict, exact_match)

                        print(f"\n{'='*50}")
                        print(f"Dependency: {result['dependency_name']}")
                        print(f"{'='*50}")
                        print(f"Total nodes using this dependency: {result['total_nodes']}")

                        if result['commented_count'] > 0:
                            print(f"WARNING: Nodes with COMMENTED (inactive) dependency: {result['commented_count']}")

                        if result['total_nodes'] > 0:
                            print(f"\nVersion specifications found:")
                            for version, count in result['sorted_versions']:
                                print(f"  {version:20} - {count} nodes")

                            # Sort nodes by downloads (most popular first)
                            sorted_nodes = sorted(result['nodes_using'],
                                                key=lambda x: x.get('downloads', 0),
                                                reverse=True)

                            print(f"\nNodes using {result['dependency_name']} (showing first 10 by popularity):")
                            for i, node in enumerate(sorted_nodes[:10], 1):
                                print(f"\n  {i}. {node['node_name']} ({node['node_id']})")
                                print(f"     Stars: {node.get('stars', 0):,} | Downloads: {node.get('downloads', 0):,} | Latest: {node.get('latest_version_date', 'N/A')}")
                                print(f"     Spec: {node['dependency_spec']}")
                                print(f"     Repo: {node['repository']}")

                            if result['total_nodes'] > 10:
                                print(f"\n  ... and {result['total_nodes'] - 10} more nodes")

                        if result['commented_count'] > 0:
                            print(f"\n\nWARNING: Nodes with COMMENTED {result['dependency_name']} (not active):")
                            for i, node in enumerate(result['nodes_with_commented'][:5], 1):
                                print(f"  {i}. {node['node_name']} ({node['node_id']})")
                                print(f"     Commented: {node['commented_spec']}")
                            if result['commented_count'] > 5:
                                print(f"  ... and {result['commented_count'] - 5} more nodes with commented {result['dependency_name']}")
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


def main():
    parser = argparse.ArgumentParser(description='Analyze ComfyUI node dependencies')
    parser.add_argument('--ask', action='store_true',
                       help='Enter interactive mode to query specific dependencies')
    args = parser.parse_args()

    nodes_dict = load_nodes_to_dict()

    if not nodes_dict:
        print("Failed to load nodes data")
        return

    if args.ask:
        interactive_mode(nodes_dict)
    else:
        # Original behavior - show summary
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
            print(f"WARNING: Nodes with COMMENTED dependencies: {dep_analysis['nodes_with_commented_count']}")
        print(f"\nTotal active dependency references: {dep_analysis['total_dependencies']}")
        print(f"Unique active packages (grouping versions): {dep_analysis['unique_count']}")
        print(f"Unique dependency specifications: {dep_analysis['unique_raw_count']}")
        if len(dep_analysis['unique_commented_dependencies']) > 0:
            print(f"Unique commented dependencies: {len(dep_analysis['unique_commented_dependencies'])}")

        print(f"\nTop 10 most common dependencies:")
        for dep, count in dep_analysis['sorted_by_frequency'][:10]:
            print(f"  - {dep}: {count} nodes")

        print(f"\nExample nodes with dependencies (first 3):")
        for node_info in dep_analysis['nodes_with_dependencies'][:3]:
            # Get full node data for additional info
            node_data = nodes_dict.get(node_info['id'], {})
            stars = node_data.get('github_stars', 0)
            downloads = node_data.get('downloads', 0)
            latest_version_info = node_data.get('latest_version', {})
            latest_date = 'N/A'
            if latest_version_info and 'createdAt' in latest_version_info:
                date_str = latest_version_info['createdAt']
                latest_date = date_str[:10] if date_str else 'N/A'

            print(f"\n  Node: {node_info['name']} ({node_info['id']})")
            print(f"  Stats: Stars: {stars:,} | Downloads: {downloads:,} | Latest: {latest_date}")
            print(f"  Dependencies: {', '.join(node_info['dependencies'][:5])}")
            if len(node_info['dependencies']) > 5:
                print(f"    ... and {len(node_info['dependencies']) - 5} more")

        if dep_analysis['nodes_with_commented_count'] > 0:
            print(f"\n\nWARNING: {dep_analysis['nodes_with_commented_count']} nodes have commented dependencies")
            print("  Commented dependencies are included in their dependency lists but prefixed with #")
            print("  These dependencies are NOT active and should not be installed.")
            print(f"\n  Example nodes with commented dependencies:")
            for node_info in dep_analysis['nodes_with_commented_dependencies'][:3]:
                print(f"\n    Node: {node_info['name']} ({node_info['id']})")
                print(f"    Commented deps: {', '.join(node_info['commented_deps'][:3])}")
                if len(node_info['commented_deps']) > 3:
                    print(f"      ... and {len(node_info['commented_deps']) - 3} more commented")


if __name__ == "__main__":
    main()