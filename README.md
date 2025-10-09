# ComfyUI Dependency Analysis Tool

A Python tool for analyzing dependencies across ComfyUI node packages. This tool helps identify common dependencies, version conflicts, and provides detailed insights into the ComfyUI ecosystem's dependency landscape.

NOTE: Since it is a bit of busy work, almost everything related to this tool is Claude Code generated; this sentence is one of the only things I (Kosinkadink) wrote here (hi!).

## Table of Contents
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage Modes](#usage-modes)
- [Commands](#commands)
- [Search Modifiers](#search-modifiers)
- [Examples](#examples)
- [Output Files](#output-files)

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/comfyui-dependency-tooling.git
cd comfyui-dependency-tooling

# No additional dependencies required - uses Python standard library
python analysis.py
```

## Quick Start

```bash
# Launch interactive mode (default)
python analysis.py

# Execute a single command
python analysis.py -e "numpy"

# Search with modifiers
python analysis.py -e "torch* &top 100"
```

## Usage Modes

### Interactive Mode (Default)
When you run `analysis.py` without arguments, it launches an interactive session where you can explore dependencies, search for packages, and analyze nodes.

```bash
python analysis.py
```

### Execute Mode
Run a single command and exit. Useful for scripting or quick queries.

```bash
python analysis.py --execute "command"
# or
python analysis.py -e "command"
```

**Note for Git Bash users:** When using commands that start with `/`, use double slashes (e.g., `//top` instead of `/top`) to prevent path interpretation.

## Commands

### `/summary`
Display a comprehensive analysis summary including:
- Total nodes analyzed
- Nodes with/without dependencies
- Most common dependencies
- Example nodes with their dependencies
- Warnings about commented dependencies
- Information about pip commands

```bash
> /summary
```

### `/list`
Show all unique dependency names in the dataset.
- Dependencies are grouped by base package name (versions consolidated)
- Shows count of nodes using each dependency
- Displays in alphabetical order

```bash
> /list
> /list &dupes       # Show dependencies with version conflicts
> /list &top 50      # Show dependencies in top 50 nodes
> /list &top -10     # Show dependencies in bottom 10 nodes
```

### `/top`
Display the 20 most common dependencies across all nodes.

```bash
> /top
> /top &top 100      # Show most common deps in top 100 nodes
```

### `/nodes`
Show detailed information about nodes, sorted by downloads.
- Displays rank, downloads, stars, and dependency count
- Shows latest version and release date
- Includes repository URL and description

```bash
> /nodes              # Show top 20 nodes
> /nodes &all         # Show all nodes
> /nodes &top 50      # Show top 50 nodes
> /nodes &top -5      # Show bottom 5 nodes
```

### `/update`
Fetch the latest nodes data from the ComfyUI registry and update the local `nodes.json` file.
- Automatically runs if `nodes.json` is not found
- Shows fetch time and total nodes saved
- Refreshes the in-memory data for immediate analysis

```bash
> /update             # Fetch latest data from registry
```

### `/help`
Display help information about available commands and modifiers.

```bash
> /help
```

### `/quit`
Exit interactive mode. Alternatives: `/exit`, `/q`

```bash
> /quit
```

## Search Modifiers

Modifiers can be combined with commands and searches to customize output.

### `&save`
Save the results to a timestamped file in the `results/` directory.

```bash
> numpy &save
> /list &dupes &save
```

### `&all`
Show all results without limiting output (default shows first 10-20 items).

```bash
> scipy &all
> /nodes &all
```

### `&top N`
Filter results to only include the top N nodes by downloads.
- Use positive numbers for most downloaded: `&top 100`
- Use negative numbers for least downloaded: `&top -10`

```bash
> numpy &top 50       # Search numpy in top 50 nodes
> /list &top -20      # List dependencies in bottom 20 nodes
```

### `&dupes` (for /list only)
Show dependencies with multiple version specifications, helping identify version conflicts.

```bash
> /list &dupes
> /list &dupes &top 100
```

### `&nodes`
Filter results to only include specific nodes by their IDs.

**Comma-separated list:**
```bash
> numpy &nodes comfyui-kjnodes,rgthree-comfy
> /top &nodes node1,node2,node3
```

**From a file:**
```bash
> numpy &nodes file:nodelist.txt
> /list &nodes file:path/to/nodes.txt &dupes
```

The file should contain one node ID per line.

## Dependency Searches

Search for specific dependencies by typing their name directly.

### Simple Search
```bash
> numpy               # Find all nodes using numpy
> opencv-python       # Find all nodes using opencv-python
```

### Wildcard Search
Use `*` for pattern matching:
```bash
> torch*             # Find torch, torchvision, torchaudio, etc.
> *video*            # Find all dependencies where video appears in the name
> transformers*      # Find transformers and related packages
```

### Search Output Includes:
- **Rank**: Global rank among all registry nodes
- **Downloads**: Total download count
- **Stars**: GitHub stars
- **Latest**: Date of most recent version
- **Spec**: Exact dependency specification used
- **Repository**: GitHub repository URL

## Examples

### Find all packages using numpy in top 100 most popular nodes
```bash
python analysis.py -e "numpy &top 100"
```

### Search for all torch-related packages and save results
```bash
python analysis.py -e "torch* &save"
```

### Show dependencies with version conflicts in top 50 nodes
```bash
python analysis.py -e "//list &dupes &top 50"
```

### Get summary of the entire dataset
```bash
python analysis.py -e "//summary"
```

### Analyze dependencies for specific nodes from a file
```bash
python analysis.py -e "//list &nodes file:my_nodes.txt &dupes"
```

### Interactive session workflow
```bash
$ python analysis.py
> /summary           # Get overview
> /top               # See most common dependencies
> numpy              # Analyze numpy usage
> torch* &all        # See all torch-related packages
> /list &dupes       # Check for version conflicts
> /nodes &top 10     # See top 10 nodes by downloads
> numpy &nodes comfyui-kjnodes,rgthree-comfy  # Check numpy in specific nodes
> /quit              # Exit
```

## Output Files

When using the `&save` modifier, results are saved to the `results/` directory with timestamps:

```
results/
├── 20241007_220049_numpy.txt
├── 20241007_220806_scipy_all.txt
├── 20241007_221630_scipy_top_100_all.txt
├── 20241007_223354_list_dupes_dupes_top_50.txt
└── 20241007_222019_nodes_top_10.txt
```

File naming format: `YYYYMMDD_HHMMSS_queryname.txt`

## Data Source

The tool analyzes data from `manager-files/nodes.json`, which contains information about ComfyUI node packages including:
- Package metadata (name, description, repository)
- Download and star counts
- Dependency specifications
- Version information

The data is automatically fetched from the ComfyUI registry if `nodes.json` is not present. You can update it anytime using the `/update` command to get the latest node information.

## Special Dependency Handling

### Commented Dependencies
Dependencies starting with `#` are treated as commented (inactive) and tracked separately. Inline comments (text after `#`) are also stripped from dependency lines.

### Pip Commands
Lines starting with `--` are pip installation flags (e.g., `--extra-index-url`) and are tracked separately.

### Git-based Dependencies
Dependencies installed directly from git repositories are tracked separately:
- **git+ prefix**: Dependencies starting with `git+` (e.g., `git+https://github.com/user/repo.git`)
- **@ git+ style**: Dependencies with `@ git+` format (e.g., `package @ git+https://github.com/user/repo.git`)

These are displayed separately in the summary with breakdown by type.

### Version Grouping
Different versions of the same package (e.g., `numpy`, `numpy>=1.20`, `numpy==1.24.0`) are grouped together for accurate statistics while preserving version information.

## Tips

1. **Combine modifiers** for powerful queries:
   ```bash
   > numpy &top 100 &all &save
   ```

2. **Use wildcards** to discover related packages:
   ```bash
   > *audio*
   > transformers*
   ```

3. **Check for version conflicts** regularly:
   ```bash
   > /list &dupes
   ```

4. **Filter by popularity** to focus on widely-used nodes:
   ```bash
   > scipy &top 50
   ```

5. **Save important searches** for later reference:
   ```bash
   > torch &all &save
   ```

6. **Analyze specific node sets** to focus on particular packages:
   ```bash
   > /list &nodes file:production_nodes.txt &dupes
   > numpy &nodes comfyui-kjnodes,comfyui-easy-use
   ```
