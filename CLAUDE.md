# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python-based dependency analysis tool for the ComfyUI ecosystem. Analyzes dependencies across ComfyUI node packages using data from the ComfyUI registry API. The tool provides interactive and command-line modes for searching, filtering, and visualizing dependency patterns.

**Note**: Almost everything in this tool is Claude Code generated (per the original author).

## Common Commands

### Running the Tool

```bash
# Interactive mode (default)
python analysis.py

# Execute a single command and exit
python analysis.py -e "numpy &top 100"
python analysis.py -e "//summary"

# Update nodes data from registry
python analysis.py -e "//update"

# Update requirements.txt from repositories
python analysis.py -e "/update-reqs &top 10"
```

### Testing

```bash
# Run test files (if needed)
python test_update_command.py
python test_concurrent_download.py
```

### Dependencies

```bash
# Install required packages
pip install requests plotly
```

The tool primarily uses Python standard library, with only two external dependencies: `requests` for API calls and `plotly` for graph visualization.

## Architecture

### Code Organization

The codebase follows a **functional programming** style with no classes. All code is organized into:

- **analysis.py** - Main monolithic file (~2500 lines) containing:
  - Registry API interaction functions
  - Dependency analysis logic
  - Interactive and execute mode implementations
  - Command parsing and dispatch
  - All command implementations (/summary, /list, /top, /nodes, /graph, etc.)

- **src/utils.py** - Shared utility functions:
  - `parse_dependency_string()` - Parses pip dependency specifications
  - `parse_requirements_txt()` - Parses requirements.txt content
  - `create_timestamped_filepath()` - Generates timestamped output files
  - `load_csv_data_to_nodes()` - Loads CSV data into node dictionaries
  - `load_extension_node_map()` - Maps node IDs to packages with fuzzy matching
  - `normalize_repository_url()` - Normalizes GitHub URLs for comparison

- **src/graph.py** - Visualization functions using plotly:
  - `create_cumulative_graph()` - Shows dependency accumulation by rank
  - `create_downloads_graph()` - Visualizes download statistics
  - `create_deps_graph()` - Shows dependency counts by node
  - `create_nodes_graph()` - Visualizes individual node counts

### Data Flow

1. **Data Loading** (`load_nodes_to_dict()`):
   - Loads `manager-files/nodes.json` (auto-fetches if missing)
   - Loads `manager-files/extension-node-map.json` for node ID mappings
   - Loads cached requirements.txt from `updated_reqs/` directory
   - Optionally loads CSV data (web directories, routes, pip usage)

2. **Dependency Compilation** (`compile_dependencies()`):
   - Parses all dependencies from all nodes
   - Groups by base package name (ignoring version specifiers)
   - Separates regular dependencies, git dependencies, pip commands, and comments
   - Creates indices for fast lookup

3. **Mode Selection**:
   - **Interactive mode**: Command loop accepting user queries
   - **Execute mode**: Single command execution via `-e` flag

4. **Command Processing**:
   - Commands start with `/` (e.g., `/summary`, `/list`, `/nodes`, `/update-reqs`)
   - Modifiers start with `&` (e.g., `&save`, `&top 100`, `&dupes`)
   - Direct searches match dependency names (e.g., `numpy`, `torch*`)

### Key Data Structures

**nodes_dict** - Main data structure mapping node IDs to node data:
```python
{
  "node-id": {
    "id": "node-id",
    "name": "Display Name",
    "repository": "https://github.com/user/repo",
    "downloads": 12345,
    "github_stars": 678,
    "latest_version": {
      "version": "1.2.3",
      "createdAt": "2024-01-01T00:00:00Z",
      "dependencies": ["numpy>=1.20", "torch"]
    },
    "_node_ids": ["NodeType1", "NodeType2"],  # Added by load_extension_node_map()
    "_has_node_pattern": True,  # If node count is dynamic
    "_web_directories": [...],   # Added by load_web_directory_data()
    "_routes": [...],            # Added by load_routes_data()
  }
}
```

**dep_analysis** - Result from `compile_dependencies()`:
```python
{
  "unique_base_dependencies": ["numpy", "torch", ...],
  "base_dep_to_nodes": {"numpy": ["node1", "node2", ...]},
  "git_dependencies": [...],
  "pip_commands": [...],
  "commented_dependencies": [...]
}
```

### Modifier System

Modifiers filter or modify command behavior. They are parsed using regex patterns:

- `&save` - Saves output to `results/YYYYMMDD_HHMMSS_query.txt`
- `&all` - Shows all results (removes default limit)
- `&top N` / `&top -N` - Filter to top/bottom N nodes by downloads
- `&dupes` - (For `/list`) Show only dependencies with version conflicts
- `&nodes file:path.txt` - Filter to specific node IDs from file or comma-separated list
- `&stat <name>` - Filter to nodes with specific stats (e.g., `&stat web-dirs`, `&stat routes`)

### Registry API Integration

The tool fetches data from `https://api.comfy.org`:

- **Concurrent fetching** (`get_registry_nodes_concurrent()`): Uses ThreadPoolExecutor to fetch multiple pages in parallel
- **Pagination**: API returns 30 nodes per page; tool determines total pages from first response
- **Retry logic**: 3 attempts per page with exponential backoff
- **Caching**: Data saved to `manager-files/nodes.json` to avoid repeated API calls

### Requirements.txt Updating

The `/update-reqs` command:
1. Constructs raw GitHub URL for requirements.txt
2. Fetches file content with retry logic
3. Parses requirements and updates node data in-memory
4. Backs up original dependencies for comparison
5. Caches fetched requirements to `updated_reqs/` for future sessions
6. Supports `&nodes`, `&top`, and `&stat` modifiers for filtering which nodes to update

## Important Patterns

### Dependency Parsing

The `parse_dependency_string()` function handles various formats:
- Regular pip specs: `numpy>=1.20`, `torch==2.0.0`
- Git dependencies: `git+https://...` or `package @ git+https://...`
- Commented lines: `# this is skipped`
- Pip commands: `--extra-index-url https://...`
- Inline comments: `numpy  # this comment is stripped`

Git dependencies are categorized by type and tracked separately from regular dependencies.

### Version Grouping

Dependencies like `numpy`, `numpy>=1.20`, `numpy==1.24.0` are all grouped under base name `"numpy"` for statistics, while preserving individual version specs for display.

### Fuzzy Repository Matching

When mapping node IDs or other data to nodes, repository URLs are normalized and matched:
1. Try exact URL match first
2. Fall back to matching by repository name only (handles forks)

Example: `https://github.com/user/repo` and `https://github.com/fork/repo` both match on `"repo"`.

### Node Ranking

Nodes are ranked by downloads (descending). The rank map is calculated once via `calculate_node_ranks()` and reused across all commands.

## File Structure Notes

- **manager-files/**: JSON data from ComfyUI registry
- **results/**: Timestamped output files when using `&save`
- **updated_reqs/**: Cached requirements.txt files organized by node ID
- **src/**: Utility and graphing modules
- **test_*.py**: Test scripts for specific functionality

## Development Notes

### Adding New Commands

Commands are implemented in the `interactive_mode()` function's main while loop. To add a new command:

1. Add elif branch matching command pattern (e.g., `elif query.lower().startswith('/mycommand')`)
2. Parse any modifiers using regex or string methods
3. Process nodes_dict and dep_analysis as needed
4. Format output
5. Handle `&save` modifier if applicable
6. Update help text in `print_help()` function

### Adding New Modifiers

Modifiers are parsed within each command handler. Common pattern:

```python
# Check for modifier
if '&mymodifier' in query.lower():
    # Parse any parameters
    # Modify behavior accordingly
```

For universal modifiers (work across commands), consider adding to a shared parsing function.

### Working with Graphs

All graph functions in `src/graph.py` follow this pattern:
1. Calculate data to visualize
2. Create plotly figure with go.Figure()
3. Configure layout, axes, hover text
4. Either display (`fig.show()`) or save to HTML

### Data Freshness

The `/update` command refreshes both `nodes.json` and `extension-node-map.json` from the registry. Always test with fresh data when analyzing current ecosystem state.
