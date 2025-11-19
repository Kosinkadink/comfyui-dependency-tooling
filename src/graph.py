"""
Graph visualization functionality for ComfyUI dependency analysis.
"""

import re
from datetime import datetime
from pathlib import Path
from .utils import parse_dependency_string, create_timestamped_filepath, get_all_stat_names, get_node_stat_count

# Try to import plotly for graph visualization
try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


def build_graph_title(base_title, query_desc):
    """
    Build a graph title with query modifiers like &top and &nodes.

    Args:
        base_title: Base title string
        query_desc: Query description to parse for modifiers

    Returns:
        Complete title string with modifiers
    """
    title_parts = [base_title]

    if '&top' in query_desc.lower():
        top_match = re.search(r'&top\s+(-?\d+)', query_desc.lower())
        if top_match:
            n = int(top_match.group(1))
            if n > 0:
                title_parts.append(f'(Top {n} nodes)')
            else:
                title_parts.append(f'(Bottom {abs(n)} nodes)')

    if '&nodes' in query_desc.lower():
        title_parts.append('(Filtered nodes)')

    return ' '.join(title_parts)


def calculate_cumulative_dependencies(nodes_dict):
    """
    Calculate cumulative unique dependencies as nodes are added by rank.

    Args:
        nodes_dict: Dictionary of nodes

    Returns:
        Tuple of (node_counts, cumulative_deps, node_names, node_dep_counts)
    """
    # Sort nodes by downloads (rank)
    sorted_nodes = sorted(nodes_dict.items(), key=lambda x: x[1].get('downloads', 0), reverse=True)

    node_counts = []
    cumulative_deps = []
    node_names = []
    node_dep_counts = []
    unique_deps = set()

    for i, (node_id, node_data) in enumerate(sorted_nodes, 1):
        node_unique_deps = set()

        # Get dependencies for this node
        if 'latest_version' in node_data and node_data['latest_version']:
            if 'dependencies' in node_data['latest_version']:
                deps = node_data['latest_version']['dependencies']
                if deps and isinstance(deps, list):
                    for dep in deps:
                        parsed = parse_dependency_string(dep)

                        # Skip comments, pip commands, and empty lines
                        if parsed['skip'] or parsed['is_pip_command']:
                            continue

                        if parsed['base_name']:
                            node_unique_deps.add(parsed['base_name'])
                            unique_deps.add(parsed['base_name'])

        node_counts.append(i)
        cumulative_deps.append(len(unique_deps))
        node_names.append(f"{node_data.get('name', 'N/A')} ({node_id})")
        node_dep_counts.append(len(node_unique_deps))

    return node_counts, cumulative_deps, node_names, node_dep_counts


def create_cumulative_graph(nodes_dict, save_to_file=False, query_desc="/graph cumulative"):
    """
    Create and display a cumulative dependencies graph using plotly.

    Args:
        nodes_dict: Dictionary of nodes
        save_to_file: Whether to save the graph to a file
        query_desc: Query description for file naming and title

    Returns:
        True if successful, False otherwise
    """
    if not PLOTLY_AVAILABLE:
        print("Error: plotly is not installed. Install it with: pip install plotly")
        return False

    try:
        print("Calculating cumulative dependencies...")
        node_counts, cumulative_deps, node_names, node_dep_counts = calculate_cumulative_dependencies(nodes_dict)

        # Create hover text with dependency counts
        hover_texts = []
        for i in range(len(node_names)):
            hover_texts.append(f"{node_names[i]}<br>Node dependencies: {node_dep_counts[i]}")

        # Create the figure
        fig = go.Figure()

        # Add the main trace
        fig.add_trace(go.Scatter(
            x=node_counts,
            y=cumulative_deps,
            mode='lines',
            name='Cumulative Dependencies',
            line=dict(color='blue', width=2),
            hovertemplate='<b>Node %{x}</b><br>' +
                         'Total unique dependencies: %{y}<br>' +
                         '%{text}<br>' +
                         '<extra></extra>',
            text=hover_texts
        ))

        # Add markers for every 100 nodes
        marker_indices = [i-1 for i in range(100, len(node_counts)+1, 100)]
        marker_x = [node_counts[i] for i in marker_indices if i < len(node_counts)]
        marker_y = [cumulative_deps[i] for i in marker_indices if i < len(cumulative_deps)]
        marker_hover_texts = [hover_texts[i] for i in marker_indices if i < len(hover_texts)]

        fig.add_trace(go.Scatter(
            x=marker_x,
            y=marker_y,
            mode='markers',
            name='Every 100 nodes',
            marker=dict(color='red', size=8),
            hovertemplate='<b>Node %{x}</b><br>' +
                         'Total dependencies: %{y}<br>' +
                         '%{text}<br>' +
                         '<extra></extra>',
            text=marker_hover_texts
        ))

        # Build title based on query
        title = build_graph_title('Cumulative Unique Dependencies by Node Rank', query_desc)

        # Update layout
        fig.update_layout(
            title=title,
            xaxis_title='Number of Node Packs (sorted by popularity)',
            yaxis_title='Total Unique Dependencies',
            hovermode='closest',
            showlegend=True,
            template='plotly_white',
            width=1200,
            height=700
        )

        # Add grid
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')

        # Save to file if requested
        if save_to_file:
            filepath = create_timestamped_filepath(query_desc, '.html')
            fig.write_html(str(filepath))
            print(f"\n[Graph saved to: {filepath}]")

        # Open in browser using plotly's show method
        fig.show()

        # Also show some statistics
        print(f"\nStatistics:")
        print(f"  Top 10 nodes: {cumulative_deps[9] if len(cumulative_deps) > 9 else 'N/A'} unique dependencies")
        print(f"  Top 50 nodes: {cumulative_deps[49] if len(cumulative_deps) > 49 else 'N/A'} unique dependencies")
        print(f"  Top 100 nodes: {cumulative_deps[99] if len(cumulative_deps) > 99 else 'N/A'} unique dependencies")
        print(f"  Top 500 nodes: {cumulative_deps[499] if len(cumulative_deps) > 499 else 'N/A'} unique dependencies")
        print(f"  All {len(node_counts)} nodes: {cumulative_deps[-1] if cumulative_deps else 'N/A'} unique dependencies")

        return True

    except Exception as e:
        print(f"Error creating graph: {e}")
        return False


def create_downloads_graph(nodes_dict, save_to_file=False, query_desc="/graph downloads", log_scale=False, show_indicators=False, full_nodes_for_percentiles=None, metric='downloads'):
    """
    Create and display a graph showing downloads or dependency counts using plotly.

    Args:
        nodes_dict: Dictionary of nodes to display
        save_to_file: Whether to save the graph to a file
        query_desc: Query description for file naming and title
        log_scale: Whether to use logarithmic scale for y-axis (downloads only)
        show_indicators: Whether to show percentage milestone indicators (downloads only)
        full_nodes_for_percentiles: Full dataset for calculating percentiles (when using &top filter, downloads only)
        metric: 'downloads' or 'deps' - which metric to display on y-axis

    Returns:
        True if successful, False otherwise
    """
    if not PLOTLY_AVAILABLE:
        print("Error: plotly is not installed. Install it with: pip install plotly")
        return False

    try:
        if metric == 'deps':
            print("Creating dependency count graph...")
        elif metric == 'nodes':
            print("Creating node count graph...")
        else:
            print("Creating downloads graph...")

        # Calculate dependency counts for all nodes (needed for sorting if metric='deps')
        node_dep_counts = {}
        for node_id, node_data in nodes_dict.items():
            dep_count = 0
            if 'latest_version' in node_data and node_data['latest_version']:
                if 'dependencies' in node_data['latest_version']:
                    deps = node_data['latest_version']['dependencies']
                    if deps and isinstance(deps, list):
                        for dep in deps:
                            parsed = parse_dependency_string(dep)
                            # Only count actual dependencies (not comments or pip commands)
                            if not parsed['skip'] and not parsed['is_pip_command']:
                                dep_count += 1
            node_dep_counts[node_id] = dep_count

        # Calculate individual node counts for all nodes (needed if metric='nodes')
        node_individual_counts = {}
        for node_id, node_data in nodes_dict.items():
            node_ids = node_data.get('_node_ids', [])
            node_individual_counts[node_id] = len(node_ids) if node_ids else 0

        # Always sort nodes by downloads (popularity ranking)
        sorted_nodes = sorted(nodes_dict.items(), key=lambda x: x[1].get('downloads', 0), reverse=True)

        # Get all available stat names
        all_stat_names = sorted(get_all_stat_names(nodes_dict))

        # Primary categorization stat (defaults to 'web-directories' if available)
        primary_stat = 'web-directories' if 'web-directories' in all_stat_names else (all_stat_names[0] if all_stat_names else None)

        # Separate lists for nodes with and without the primary stat
        # Note: *_downloads lists contain y-axis values (downloads or deps based on metric)
        has_primary_ranks = []
        has_primary_downloads = []  # y-axis values
        has_primary_names = []
        has_primary_ids = []
        has_primary_dep_counts = []
        has_primary_download_counts = []  # actual downloads for hover
        has_primary_node_counts = []
        has_primary_stats = []  # List of stat count dicts

        no_primary_ranks = []
        no_primary_downloads = []  # y-axis values
        no_primary_names = []
        no_primary_ids = []
        no_primary_dep_counts = []
        no_primary_download_counts = []  # actual downloads for hover
        no_primary_node_counts = []
        no_primary_stats = []  # List of stat count dicts

        cumulative_downloads = []

        total_downloads = sum(node[1].get('downloads', 0) for node in sorted_nodes)
        running_total = 0

        for i, (node_id, node_data) in enumerate(sorted_nodes, 1):
            download_count = node_data.get('downloads', 0)
            dep_count = node_dep_counts.get(node_id, 0)
            individual_node_count = node_individual_counts.get(node_id, 0)

            # Use the appropriate metric for y-axis values
            if metric == 'deps':
                y_value = dep_count
            elif metric == 'nodes':
                y_value = individual_node_count
            else:
                y_value = download_count

            running_total += download_count
            cumulative_downloads.append(running_total)

            # Collect all stat counts for this node dynamically
            node_stat_counts = {}
            for stat_name in all_stat_names:
                node_stat_counts[stat_name] = get_node_stat_count(node_data, stat_name)

            # Check if node has the primary stat
            has_primary_stat = node_stat_counts.get(primary_stat, 0) > 0 if primary_stat else False

            # Get individual nodes count
            node_ids = node_data.get('_node_ids', [])
            individual_node_count = len(node_ids) if node_ids else 0
            has_node_pattern = node_data.get('_has_node_pattern', False)

            # Format node count string with optional asterisk for pattern-based matching
            node_count_str = f"{individual_node_count}*" if has_node_pattern else str(individual_node_count)

            # Append to appropriate lists based on primary stat
            if has_primary_stat:
                has_primary_ranks.append(i)
                has_primary_downloads.append(y_value)
                has_primary_names.append(node_data.get('name', node_id))
                has_primary_ids.append(node_id)
                has_primary_dep_counts.append(dep_count)
                has_primary_download_counts.append(download_count)
                has_primary_node_counts.append(node_count_str)
                has_primary_stats.append(node_stat_counts)
            else:
                no_primary_ranks.append(i)
                no_primary_downloads.append(y_value)
                no_primary_names.append(node_data.get('name', node_id))
                no_primary_ids.append(node_id)
                no_primary_dep_counts.append(dep_count)
                no_primary_download_counts.append(download_count)
                no_primary_node_counts.append(node_count_str)
                no_primary_stats.append(node_stat_counts)

        # Calculate percentage milestones based on full dataset if provided
        # This ensures that when using &top filter, percentiles are relative to ALL downloads
        if full_nodes_for_percentiles is not None:
            total_downloads_for_percentiles = sum(node.get('downloads', 0) for node in full_nodes_for_percentiles.values())
        else:
            total_downloads_for_percentiles = total_downloads

        milestones = {
            50: None,
            75: None,
            90: None,
            99: None
        }

        for i, cum_downloads in enumerate(cumulative_downloads):
            percentage = (cum_downloads / total_downloads_for_percentiles * 100) if total_downloads_for_percentiles > 0 else 0
            for milestone in milestones:
                if milestones[milestone] is None and percentage >= milestone:
                    milestones[milestone] = i

        # Create the figure
        fig = go.Figure()

        # Build unified hover template dynamically - shows all information regardless of metric
        # Note: Nodes field shows count + optional * for pattern-based matching
        hover_parts = [
            '<b>Rank #%{x}</b><br>',
            'Name: %{text}<br>',
            'ID: %{customdata[0]}<br>',
            'Downloads: %{customdata[1]:,.0f}<br>',
            'Dependencies: %{customdata[2]}<br>',
            'Nodes: %{customdata[3]}<br>'
        ]

        # Add all stats dynamically to hover template
        customdata_index = 4  # Next available index in customdata
        for stat_name in all_stat_names:
            display_name = stat_name.replace('-', ' ').replace('_', ' ').title()
            hover_parts.append(f'{display_name}: %{{customdata[{customdata_index}]}}<br>')
            customdata_index += 1

        hover_parts.append('<extra></extra>')
        hover_template = ''.join(hover_parts)

        # Helper function to build customdata tuple for a node
        def build_customdata(node_id, download_count, dep_count, node_count, stat_counts):
            """Build customdata tuple with dynamic stats."""
            data = [
                node_id,
                download_count,
                dep_count,
                node_count
            ]
            # Add all stat counts in the same order as hover template
            for stat_name in all_stat_names:
                data.append(stat_counts.get(stat_name, 0))
            return tuple(data)

        # Add visual indicators for zero-value bars (small circles at bottom)
        # Only add indicators for zeros in the metric being displayed
        # These are added FIRST so they appear behind everything else
        if metric == 'downloads':
            zero_no_primary_indices = [i for i in range(len(no_primary_download_counts)) if no_primary_download_counts[i] == 0]
        elif metric == 'deps':
            zero_no_primary_indices = [i for i in range(len(no_primary_dep_counts)) if no_primary_dep_counts[i] == 0]
        else:  # metric == 'nodes'
            # Note: node_counts are strings like "0" or "0*", so strip asterisk and compare
            zero_no_primary_indices = [i for i in range(len(no_primary_node_counts)) if no_primary_node_counts[i].rstrip('*') == '0']

        if zero_no_primary_indices:
            zero_no_primary_ranks = [no_primary_ranks[i] for i in zero_no_primary_indices]
            zero_no_primary_names = [no_primary_names[i] for i in zero_no_primary_indices]
            zero_customdata = [
                build_customdata(
                    no_primary_ids[i],
                    no_primary_download_counts[i],
                    no_primary_dep_counts[i],
                    no_primary_node_counts[i],
                    no_primary_stats[i]
                )
                for i in zero_no_primary_indices
            ]

            primary_label = primary_stat.replace('-', ' ').replace('_', ' ').title() if primary_stat else "Primary"
            fig.add_trace(go.Scatter(
                x=zero_no_primary_ranks,
                y=[0] * len(zero_no_primary_ranks),  # Position at y=0
                mode='markers',
                name=f'Zero Value (No {primary_label})',
                marker=dict(
                    symbol='circle',
                    size=6,
                    color='#3498db',  # Blue
                    line=dict(width=1, color='#2c3e50')
                ),
                customdata=zero_customdata,
                hovertemplate=hover_template,
                text=zero_no_primary_names,
                showlegend=False  # Don't clutter legend
            ))

        # Check for zero values in nodes with primary stat
        if metric == 'downloads':
            zero_primary_indices = [i for i in range(len(has_primary_download_counts)) if has_primary_download_counts[i] == 0]
        elif metric == 'deps':
            zero_primary_indices = [i for i in range(len(has_primary_dep_counts)) if has_primary_dep_counts[i] == 0]
        else:  # metric == 'nodes'
            # Note: node_counts are strings like "0" or "0*", so strip asterisk and compare
            zero_primary_indices = [i for i in range(len(has_primary_node_counts)) if has_primary_node_counts[i].rstrip('*') == '0']

        if zero_primary_indices:
            zero_primary_ranks = [has_primary_ranks[i] for i in zero_primary_indices]
            zero_primary_names = [has_primary_names[i] for i in zero_primary_indices]
            zero_customdata = [
                build_customdata(
                    has_primary_ids[i],
                    has_primary_download_counts[i],
                    has_primary_dep_counts[i],
                    has_primary_node_counts[i],
                    has_primary_stats[i]
                )
                for i in zero_primary_indices
            ]

            fig.add_trace(go.Scatter(
                x=zero_primary_ranks,
                y=[0] * len(zero_primary_ranks),  # Position at y=0
                mode='markers',
                name=f'Zero Value (Has {primary_label})',
                marker=dict(
                    symbol='circle',
                    size=6,
                    color='#2ecc71',  # Green
                    line=dict(width=1, color='#27ae60')
                ),
                customdata=zero_customdata,
                hovertemplate=hover_template,
                text=zero_primary_names,
                showlegend=False  # Don't clutter legend
            ))

        # Add bar charts after zero-value indicators
        # Add trace for nodes without primary stat (blue)
        if no_primary_ranks:
            no_primary_customdata = [
                build_customdata(
                    no_primary_ids[i],
                    no_primary_download_counts[i],
                    no_primary_dep_counts[i],
                    no_primary_node_counts[i],
                    no_primary_stats[i]
                )
                for i in range(len(no_primary_ranks))
            ]

            fig.add_trace(go.Bar(
                x=no_primary_ranks,
                y=no_primary_downloads,
                name=f'No {primary_label}',
                marker=dict(
                    color='#3498db',  # Blue
                    line=dict(width=0.5, color='#2c3e50')
                ),
                text=no_primary_names,
                textposition='auto',
                customdata=no_primary_customdata,
                hovertemplate=hover_template
            ))

        # Add trace for nodes with primary stat (green)
        if has_primary_ranks:
            has_primary_customdata = [
                build_customdata(
                    has_primary_ids[i],
                    has_primary_download_counts[i],
                    has_primary_dep_counts[i],
                    has_primary_node_counts[i],
                    has_primary_stats[i]
                )
                for i in range(len(has_primary_ranks))
            ]

            fig.add_trace(go.Bar(
                x=has_primary_ranks,
                y=has_primary_downloads,
                name=f'Has {primary_label}',
                marker=dict(
                    color='#2ecc71',  # Green
                    line=dict(width=0.5, color='#27ae60')
                ),
                text=has_primary_names,
                textposition='auto',
                customdata=has_primary_customdata,
                hovertemplate=hover_template
            ))

        # Build title and axis labels based on metric
        if metric == 'deps':
            title = build_graph_title('Dependency Count by Node Rank', query_desc)
            xaxis_title = 'Node Rank (sorted by popularity)'
            yaxis_title = 'Number of Dependencies'
        elif metric == 'nodes':
            title = build_graph_title('Individual Node Count by Node Pack Rank', query_desc)
            xaxis_title = 'Node Pack Rank (sorted by popularity)'
            yaxis_title = 'Number of Individual Nodes'
        else:
            title = build_graph_title('Total Downloads by Node Rank', query_desc)
            xaxis_title = 'Node Rank (sorted by popularity)'
            yaxis_title = 'Total Downloads' + (' (log scale)' if log_scale else '')

        # Update layout
        layout_params = {
            'title': title,
            'xaxis_title': xaxis_title,
            'yaxis_title': yaxis_title,
            'hovermode': 'closest',
            'showlegend': True,
            'legend': dict(
                x=1.0,
                y=1.0,
                xanchor='right',
                yanchor='top',
                bgcolor='rgba(255, 255, 255, 0.8)',
                bordercolor='rgba(0, 0, 0, 0.2)',
                borderwidth=1
            ),
            'template': 'plotly_white',
            'width': 1200,
            'height': 700
        }

        # Only apply log scale for downloads metric
        if log_scale and metric == 'downloads':
            layout_params['yaxis_type'] = 'log'

        fig.update_layout(**layout_params)

        # Add percentage milestone annotations if requested (based on download percentages)
        if show_indicators:
            # Create a mapping of rank to downloads for milestone lookup
            rank_to_downloads = {}
            for rank, download in zip(has_primary_ranks, has_primary_downloads):
                rank_to_downloads[rank] = download
            for rank, download in zip(no_primary_ranks, no_primary_downloads):
                rank_to_downloads[rank] = download

            for percentage, node_index in milestones.items():
                if node_index is not None and node_index < len(sorted_nodes):
                    rank = node_index + 1  # Convert index to rank (1-based)
                    if rank in rank_to_downloads:
                        download_count = rank_to_downloads[rank]

                        # Add vertical line at milestone
                        fig.add_shape(
                            type="line",
                            x0=rank, y0=0,
                            x1=rank, y1=download_count,
                            line=dict(
                                color="red",
                                width=2,
                                dash="dash"
                            )
                        )

                        # Add annotation
                        fig.add_annotation(
                            x=rank,
                            y=download_count,
                            text=f"{percentage}% of downloads<br>Rank #{rank}",
                            showarrow=True,
                            arrowhead=2,
                            arrowsize=1,
                            arrowwidth=2,
                            arrowcolor="red",
                            ax=30,
                            ay=-40,
                            bgcolor="white",
                            bordercolor="red",
                            borderwidth=1
                        )

        # Add grid
        fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')

        # Save to file if requested
        if save_to_file:
            filepath = create_timestamped_filepath(query_desc, '.html')
            fig.write_html(str(filepath))
            print(f"\n[Graph saved to: {filepath}]")

        # Open in browser using plotly's show method
        fig.show()

        # Also show some statistics
        total_nodes = len(sorted_nodes)
        total_downloads_sum = sum(node[1].get('downloads', 0) for node in sorted_nodes)
        total_deps_sum = sum(node_dep_counts.get(node[0], 0) for node in sorted_nodes)
        web_dir_count = len(web_dir_ranks)
        no_web_dir_count = len(no_web_dir_ranks)
        routes_count = len(routes_ranks)
        pip_nonos_count = len(pip_nonos_ranks)
        zero_deps_count = sum(1 for node in sorted_nodes if node_dep_counts.get(node[0], 0) == 0)

        print(f"\nStatistics:")
        print(f"  Total nodes: {total_nodes:,}")
        print(f"  Nodes with web directories: {web_dir_count:,} ({web_dir_count * 100 // total_nodes if total_nodes > 0 else 0}%)")
        print(f"  Nodes without web directories: {no_web_dir_count:,} ({no_web_dir_count * 100 // total_nodes if total_nodes > 0 else 0}%)")
        print(f"  Nodes with routes: {routes_count:,} ({routes_count * 100 // total_nodes if total_nodes > 0 else 0}%)")
        print(f"  Nodes with pip calls: {pip_nonos_count:,} ({pip_nonos_count * 100 // total_nodes if total_nodes > 0 else 0}%)")
        print(f"  Nodes with zero dependencies: {zero_deps_count:,} ({zero_deps_count * 100 // total_nodes if total_nodes > 0 else 0}%)")

        if metric == 'deps':
            print(f"  Total dependencies across all nodes: {total_deps_sum:,}")
            print(f"  Average dependencies per node: {total_deps_sum // total_nodes:,}" if total_nodes > 0 else "N/A")
            if sorted_nodes:
                print(f"  Highest dependency count (rank #1): {node_dep_counts.get(sorted_nodes[0][0], 0):,}")
                if len(sorted_nodes) >= 10:
                    print(f"  Top 10 nodes total dependencies: {sum(node_dep_counts.get(node[0], 0) for node in sorted_nodes[:10]):,}")
                if len(sorted_nodes) >= 100:
                    print(f"  Top 100 nodes total dependencies: {sum(node_dep_counts.get(node[0], 0) for node in sorted_nodes[:100]):,}")
        elif metric == 'nodes':
            total_individual_nodes_sum = sum(node_individual_counts.get(node[0], 0) for node in sorted_nodes)
            zero_individual_nodes_count = sum(1 for node in sorted_nodes if node_individual_counts.get(node[0], 0) == 0)
            print(f"  Total individual nodes across all packs: {total_individual_nodes_sum:,}")
            print(f"  Average individual nodes per pack: {total_individual_nodes_sum // total_nodes:,}" if total_nodes > 0 else "N/A")
            print(f"  Packs with zero individual nodes: {zero_individual_nodes_count:,} ({zero_individual_nodes_count * 100 // total_nodes if total_nodes > 0 else 0}%)")
            if sorted_nodes:
                print(f"  Highest individual node count (rank #1): {node_individual_counts.get(sorted_nodes[0][0], 0):,}")
                if len(sorted_nodes) >= 10:
                    print(f"  Top 10 packs total individual nodes: {sum(node_individual_counts.get(node[0], 0) for node in sorted_nodes[:10]):,}")
                if len(sorted_nodes) >= 100:
                    print(f"  Top 100 packs total individual nodes: {sum(node_individual_counts.get(node[0], 0) for node in sorted_nodes[:100]):,}")
        else:
            print(f"  Total downloads across all nodes: {total_downloads_sum:,}")
            print(f"  Average downloads per node: {total_downloads_sum // total_nodes:,}" if total_nodes > 0 else "N/A")
            if sorted_nodes:
                print(f"  Highest downloads (rank #1): {sorted_nodes[0][1].get('downloads', 0):,}")
                if len(sorted_nodes) >= 10:
                    print(f"  Top 10 nodes downloads: {sum(node[1].get('downloads', 0) for node in sorted_nodes[:10]):,}")
                if len(sorted_nodes) >= 100:
                    print(f"  Top 100 nodes downloads: {sum(node[1].get('downloads', 0) for node in sorted_nodes[:100]):,}")

        # Show download percentage milestones if indicators were shown
        if show_indicators:
            if full_nodes_for_percentiles is not None:
                print(f"\nDownload percentage milestones (relative to total {total_downloads_for_percentiles:,} downloads across all nodes):")
            else:
                print(f"\nDownload percentage milestones:")
            for percentage, node_index in sorted(milestones.items()):
                if node_index is not None:
                    print(f"  {percentage}% of downloads: Top {node_index + 1} nodes")
                else:
                    print(f"  {percentage}% of downloads: Not reached")

        return True

    except Exception as e:
        print(f"Error creating downloads graph: {e}")
        return False


def create_deps_graph(nodes_dict, save_to_file=False, query_desc="/graph deps", full_nodes_for_percentiles=None):
    """
    Create and display a dependency count graph using plotly.
    This is a convenience wrapper around create_downloads_graph() with metric='deps'.

    Args:
        nodes_dict: Dictionary of nodes to display
        save_to_file: Whether to save the graph to a file
        query_desc: Query description for file naming and title
        full_nodes_for_percentiles: Full dataset for calculating percentiles (when using &top filter)

    Returns:
        True if successful, False otherwise
    """
    return create_downloads_graph(
        nodes_dict=nodes_dict,
        save_to_file=save_to_file,
        query_desc=query_desc,
        log_scale=False,
        show_indicators=False,
        full_nodes_for_percentiles=full_nodes_for_percentiles,
        metric='deps'
    )


def create_nodes_graph(nodes_dict, save_to_file=False, query_desc="/graph nodes", full_nodes_for_percentiles=None):
    """
    Create and display an individual node count graph using plotly.
    This is a convenience wrapper around create_downloads_graph() with metric='nodes'.

    Args:
        nodes_dict: Dictionary of nodes to display
        save_to_file: Whether to save the graph to a file
        query_desc: Query description for file naming and title
        full_nodes_for_percentiles: Full dataset for calculating percentiles (when using &top filter)

    Returns:
        True if successful, False otherwise
    """
    return create_downloads_graph(
        nodes_dict=nodes_dict,
        save_to_file=save_to_file,
        query_desc=query_desc,
        log_scale=False,
        show_indicators=False,
        full_nodes_for_percentiles=full_nodes_for_percentiles,
        metric='nodes'
    )