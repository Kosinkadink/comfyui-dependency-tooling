"""
Graph visualization functionality for ComfyUI dependency analysis.
"""

import re
from datetime import datetime
from pathlib import Path
from .utils import parse_dependency_string, create_timestamped_filepath

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


def create_cumulative_graph(nodes_dict, save_to_file=False, query_desc="/graph"):
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


def create_downloads_graph(nodes_dict, save_to_file=False, query_desc="/graph downloads", log_scale=False, show_indicators=False, full_nodes_for_percentiles=None):
    """
    Create and display a total downloads graph using plotly.

    Args:
        nodes_dict: Dictionary of nodes to display
        save_to_file: Whether to save the graph to a file
        query_desc: Query description for file naming and title
        log_scale: Whether to use logarithmic scale for y-axis
        show_indicators: Whether to show percentage milestone indicators
        full_nodes_for_percentiles: Full dataset for calculating percentiles (when using &top filter)

    Returns:
        True if successful, False otherwise
    """
    if not PLOTLY_AVAILABLE:
        print("Error: plotly is not installed. Install it with: pip install plotly")
        return False

    try:
        print("Creating downloads graph...")

        # Sort nodes by downloads (rank)
        sorted_nodes = sorted(nodes_dict.items(), key=lambda x: x[1].get('downloads', 0), reverse=True)

        # Separate lists for nodes with and without web directories
        web_dir_ranks = []
        web_dir_downloads = []
        web_dir_names = []
        web_dir_ids = []
        web_dir_dep_counts = []
        web_dir_route_counts = []
        web_dir_pip_nonos_counts = []

        no_web_dir_ranks = []
        no_web_dir_downloads = []
        no_web_dir_names = []
        no_web_dir_ids = []
        no_web_dir_dep_counts = []
        no_web_dir_route_counts = []
        no_web_dir_pip_nonos_counts = []

        # Track nodes with routes for visual indicator
        routes_ranks = []
        routes_downloads = []
        routes_names = []
        routes_ids = []
        routes_counts = []
        routes_dep_counts = []
        routes_web_dir_status = []

        # Track nodes with pip-nonos for visual indicator
        pip_nonos_ranks = []
        pip_nonos_downloads = []
        pip_nonos_names = []
        pip_nonos_ids = []
        pip_nonos_counts = []
        pip_nonos_dep_counts = []
        pip_nonos_web_dir_status = []

        cumulative_downloads = []

        total_downloads = sum(node[1].get('downloads', 0) for node in sorted_nodes)
        running_total = 0

        for i, (node_id, node_data) in enumerate(sorted_nodes, 1):
            download_count = node_data.get('downloads', 0)
            running_total += download_count
            cumulative_downloads.append(running_total)

            # Count dependencies (excluding comments and pip commands)
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

            # Check if node has web directory, routes, and pip-nonos
            has_web_dir = bool(node_data.get('_web_directories'))
            has_routes = bool(node_data.get('_routes'))
            route_count = len(node_data.get('_routes', []))
            has_pip_nonos = bool(node_data.get('_pip_nonos'))
            pip_nonos_count = len(node_data.get('_pip_nonos', []))

            # Track routes separately for visual indicator
            if has_routes:
                routes_ranks.append(i)
                routes_downloads.append(download_count)
                routes_names.append(node_data.get('name', node_id))
                routes_ids.append(node_id)
                routes_counts.append(route_count)
                routes_dep_counts.append(dep_count)
                routes_web_dir_status.append('Yes' if has_web_dir else 'No')

            # Track pip-nonos separately for visual indicator
            if has_pip_nonos:
                pip_nonos_ranks.append(i)
                pip_nonos_downloads.append(download_count)
                pip_nonos_names.append(node_data.get('name', node_id))
                pip_nonos_ids.append(node_id)
                pip_nonos_counts.append(pip_nonos_count)
                pip_nonos_dep_counts.append(dep_count)
                pip_nonos_web_dir_status.append('Yes' if has_web_dir else 'No')

            # Append to appropriate lists
            if has_web_dir:
                web_dir_ranks.append(i)
                web_dir_downloads.append(download_count)
                web_dir_names.append(node_data.get('name', node_id))
                web_dir_ids.append(node_id)
                web_dir_dep_counts.append(dep_count)
                web_dir_route_counts.append(route_count)
                web_dir_pip_nonos_counts.append(pip_nonos_count)
            else:
                no_web_dir_ranks.append(i)
                no_web_dir_downloads.append(download_count)
                no_web_dir_names.append(node_data.get('name', node_id))
                no_web_dir_ids.append(node_id)
                no_web_dir_dep_counts.append(dep_count)
                no_web_dir_route_counts.append(route_count)
                no_web_dir_pip_nonos_counts.append(pip_nonos_count)

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

        # Add trace for nodes without web directories (blue)
        if no_web_dir_ranks:
            fig.add_trace(go.Bar(
                x=no_web_dir_ranks,
                y=no_web_dir_downloads,
                name='No Web Directory',
                marker=dict(
                    color='#3498db',  # Blue
                    line=dict(width=0.5, color='#2c3e50')
                ),
                text=no_web_dir_names,
                textposition='auto',
                customdata=list(zip(no_web_dir_ids, no_web_dir_dep_counts, no_web_dir_route_counts, no_web_dir_pip_nonos_counts)),
                hovertemplate='<b>Rank #%{x}</b><br>' +
                             'Downloads: %{y:,.0f}<br>' +
                             'Name: %{text}<br>' +
                             'ID: %{customdata[0]}<br>' +
                             'Dependencies: %{customdata[1]}<br>' +
                             'Routes: %{customdata[2]}<br>' +
                             'Pip Calls: %{customdata[3]}<br>' +
                             'Web Directory: No<br>' +
                             '<extra></extra>'
            ))

        # Add trace for nodes with web directories (green)
        if web_dir_ranks:
            fig.add_trace(go.Bar(
                x=web_dir_ranks,
                y=web_dir_downloads,
                name='Has Web Directory',
                marker=dict(
                    color='#2ecc71',  # Green
                    line=dict(width=0.5, color='#27ae60')
                ),
                text=web_dir_names,
                textposition='auto',
                customdata=list(zip(web_dir_ids, web_dir_dep_counts, web_dir_route_counts, web_dir_pip_nonos_counts)),
                hovertemplate='<b>Rank #%{x}</b><br>' +
                             'Downloads: %{y:,.0f}<br>' +
                             'Name: %{text}<br>' +
                             'ID: %{customdata[0]}<br>' +
                             'Dependencies: %{customdata[1]}<br>' +
                             'Routes: %{customdata[2]}<br>' +
                             'Pip Calls: %{customdata[3]}<br>' +
                             'Web Directory: Yes<br>' +
                             '<extra></extra>'
            ))

        # Add visual indicator for nodes with routes (star markers on top of bars)
        if routes_ranks:
            fig.add_trace(go.Scatter(
                x=routes_ranks,
                y=routes_downloads,
                mode='markers',
                name='Has Routes',
                marker=dict(
                    symbol='star',
                    size=8,
                    color='#e74c3c',  # Red
                    line=dict(width=1, color='#c0392b')
                ),
                customdata=list(zip(routes_ids, routes_dep_counts, routes_counts, routes_web_dir_status)),
                hovertemplate='<b>Rank #%{x}</b><br>' +
                             'Downloads: %{y:,.0f}<br>' +
                             'Name: %{text}<br>' +
                             'ID: %{customdata[0]}<br>' +
                             'Dependencies: %{customdata[1]}<br>' +
                             'Routes: %{customdata[2]}<br>' +
                             'Web Directory: %{customdata[3]}<br>' +
                             '<extra></extra>',
                text=routes_names
            ))

        # Add visual indicator for nodes with pip-nonos (diamond markers on top of bars)
        if pip_nonos_ranks:
            fig.add_trace(go.Scatter(
                x=pip_nonos_ranks,
                y=pip_nonos_downloads,
                mode='markers',
                name='Has Pip Calls',
                marker=dict(
                    symbol='diamond',
                    size=8,
                    color='#f39c12',  # Orange
                    line=dict(width=1, color='#d68910')
                ),
                customdata=list(zip(pip_nonos_ids, pip_nonos_dep_counts, pip_nonos_counts, pip_nonos_web_dir_status)),
                hovertemplate='<b>Rank #%{x}</b><br>' +
                             'Downloads: %{y:,.0f}<br>' +
                             'Name: %{text}<br>' +
                             'ID: %{customdata[0]}<br>' +
                             'Dependencies: %{customdata[1]}<br>' +
                             'Pip Calls: %{customdata[2]}<br>' +
                             'Web Directory: %{customdata[3]}<br>' +
                             '<extra></extra>',
                text=pip_nonos_names
            ))

        # Build title based on query
        title = build_graph_title('Total Downloads by Node Rank', query_desc)

        # Update layout
        layout_params = {
            'title': title,
            'xaxis_title': 'Node Rank (sorted by popularity)',
            'yaxis_title': 'Total Downloads' + (' (log scale)' if log_scale else ''),
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

        if log_scale:
            layout_params['yaxis_type'] = 'log'

        fig.update_layout(**layout_params)

        # Add percentage milestone annotations if requested
        if show_indicators:
            # Create a mapping of rank to downloads for milestone lookup
            rank_to_downloads = {}
            for rank, download in zip(web_dir_ranks, web_dir_downloads):
                rank_to_downloads[rank] = download
            for rank, download in zip(no_web_dir_ranks, no_web_dir_downloads):
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
        web_dir_count = len(web_dir_ranks)
        no_web_dir_count = len(no_web_dir_ranks)
        routes_count = len(routes_ranks)
        pip_nonos_count = len(pip_nonos_ranks)

        print(f"\nStatistics:")
        print(f"  Total nodes: {total_nodes:,}")
        print(f"  Nodes with web directories: {web_dir_count:,} ({web_dir_count * 100 // total_nodes if total_nodes > 0 else 0}%)")
        print(f"  Nodes without web directories: {no_web_dir_count:,} ({no_web_dir_count * 100 // total_nodes if total_nodes > 0 else 0}%)")
        print(f"  Nodes with routes: {routes_count:,} ({routes_count * 100 // total_nodes if total_nodes > 0 else 0}%)")
        print(f"  Nodes with pip calls: {pip_nonos_count:,} ({pip_nonos_count * 100 // total_nodes if total_nodes > 0 else 0}%)")
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