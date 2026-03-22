"""Dependency compilation and analysis logic."""

import re
import fnmatch
from collections import defaultdict

from .utils import parse_dependency_string



def compile_dependencies(nodes_dict):
    """
    Compile all dependencies from the latest version of each node.
    Groups all versions of the same package together for accurate statistics.

    Returns:
        Dictionary with dependency statistics and lists
    """
    all_dependencies_raw = []
    base_dependency_count = defaultdict(int)
    dependency_versions = defaultdict(set)
    nodes_with_deps = []
    nodes_without_deps = []
    nodes_with_commented_deps = []
    nodes_with_pip_commands = []
    nodes_with_git_deps = []
    commented_dependencies = []
    pip_commands = []
    pip_command_count = defaultdict(int)
    git_dependencies = []
    git_dependency_count = defaultdict(int)

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

                        if parsed['is_comment']:
                            commented_deps.append(parsed['original_str'])
                            commented_dependencies.append(parsed['original_str'])
                            continue

                        if parsed['is_pip_command']:
                            node_pip_commands.append(parsed['cleaned_str'])
                            pip_commands.append(parsed['cleaned_str'])
                            pip_command_count[parsed['cleaned_str']] += 1
                            continue

                        if parsed['skip']:
                            continue

                        if parsed['is_git_dep']:
                            node_git_deps.append(parsed['cleaned_str'])
                            git_dependencies.append(parsed['cleaned_str'])
                            git_dependency_count[parsed['git_dep_type']] += 1

                        active_deps.append(parsed['cleaned_str'])
                        all_dependencies_raw.append(parsed['cleaned_str'])

                        base_name = parsed['base_name']
                        base_dependency_count[base_name] += 1
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
                        nodes_without_deps.append(node_id)
                else:
                    nodes_without_deps.append(node_id)
            else:
                nodes_without_deps.append(node_id)
        else:
            nodes_without_deps.append(node_id)

    sorted_base_dependencies = sorted(base_dependency_count.items(), key=lambda x: x[1], reverse=True)
    unique_base_dependencies = list(base_dependency_count.keys())
    unique_dependencies_raw = list(set(all_dependencies_raw))
    unique_commented = list(set(commented_dependencies))
    sorted_pip_commands = sorted(pip_command_count.items(), key=lambda x: x[1], reverse=True)
    unique_pip_commands = list(pip_command_count.keys())
    unique_git_dependencies = list(set(git_dependencies))
    sorted_git_dependency_types = sorted(git_dependency_count.items(), key=lambda x: x[1], reverse=True)

    return {
        'all_dependencies': all_dependencies_raw,
        'unique_dependencies': unique_dependencies_raw,
        'dependency_count': base_dependency_count,
        'sorted_by_frequency': sorted_base_dependencies,
        'dependency_versions': dict(dependency_versions),
        'unique_base_dependencies': unique_base_dependencies,
        'nodes_with_dependencies': nodes_with_deps,
        'nodes_without_dependencies': nodes_without_deps,
        'nodes_with_commented_dependencies': nodes_with_commented_deps,
        'nodes_with_pip_commands': nodes_with_pip_commands,
        'nodes_with_git_dependencies': nodes_with_git_deps,
        'commented_dependencies': commented_dependencies,
        'unique_commented_dependencies': unique_commented,
        'pip_commands': pip_commands,
        'unique_pip_commands': unique_pip_commands,
        'pip_command_count': dict(pip_command_count),
        'sorted_pip_commands': sorted_pip_commands,
        'git_dependencies': git_dependencies,
        'unique_git_dependencies': unique_git_dependencies,
        'git_dependency_count': dict(git_dependency_count),
        'sorted_git_dependency_types': sorted_git_dependency_types,
        'total_dependencies': len(all_dependencies_raw),
        'unique_count': len(unique_base_dependencies),
        'unique_raw_count': len(unique_dependencies_raw),
        'nodes_with_deps_count': len(nodes_with_deps),
        'nodes_without_deps_count': len(nodes_without_deps),
        'nodes_with_commented_count': len(nodes_with_commented_deps),
        'nodes_with_pip_commands_count': len(nodes_with_pip_commands),
        'nodes_with_git_deps_count': len(nodes_with_git_deps)
    }


def analyze_specific_dependency(nodes_dict, dep_name):
    """
    Analyze a specific dependency across all nodes.

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
                    parsed = parse_dependency_string(dep)

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

                    if parsed['skip'] or parsed['is_pip_command']:
                        continue

                    base_name = parsed['base_name']
                    if base_name == dep_name_lower:
                        latest_version_info = node_data.get('latest_version', {})
                        latest_version_date = 'N/A'
                        if latest_version_info and 'createdAt' in latest_version_info:
                            date_str = latest_version_info['createdAt']
                            try:
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
                            'rank': node_data.get('_rank', 0),
                            'latest_version_date': latest_version_date
                        })

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


def analyze_wildcard_dependencies(nodes_dict, pattern):
    """
    Analyze multiple dependencies matching a wildcard pattern.

    Returns:
        Dictionary with info about all matching dependencies
    """
    pattern_lower = pattern.lower()
    matching_deps = {}

    all_base_deps = set()
    for node_id, node_data in nodes_dict.items():
        if 'latest_version' in node_data and node_data['latest_version']:
            latest_version = node_data['latest_version']
            if 'dependencies' in latest_version and latest_version['dependencies']:
                for dep in latest_version['dependencies']:
                    parsed = parse_dependency_string(dep)
                    if parsed['skip'] or parsed['is_pip_command']:
                        continue
                    if parsed['base_name']:
                        all_base_deps.add(parsed['base_name'])

    for base_dep in all_base_deps:
        if fnmatch.fnmatch(base_dep, pattern_lower):
            dep_info = analyze_specific_dependency(nodes_dict, base_dep)
            matching_deps[base_dep] = dep_info

    return matching_deps
