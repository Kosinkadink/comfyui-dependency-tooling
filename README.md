# ComfyUI Dependency Analysis Tool

Analyze dependencies across the ComfyUI node ecosystem — find common packages, version conflicts, and usage patterns across thousands of custom node packs.

NOTE: Since it is a bit of busy work, almost everything related to this tool is AI generated; this sentence is one of the only things I (Kosinkadink) wrote here (hi!).

## Quick Start

```bash
pip install -r requirements.txt

# Interactive TUI (primary interface)
python -m dep_tui

# CLI one-shot mode (scripting)
python analysis.py -e "/summary"
```

## TUI Usage

Launch with `python -m dep_tui`. Navigate between screens with global keybindings:

| Key | Screen | Description |
|-----|--------|-------------|
| `n` | Node List | Sortable table of all node packs |
| `d` | Dependencies | Searchable dependency list |
| `s` | Summary | Dashboard with ecosystem stats and top deps |
| `g` | Graph | Interactive charts with cursor navigation |
| `u` | Update | Fetch fresh data from the registry |
| `r` | Update Reqs | Fetch requirements.txt from GitHub |
| `q` | Quit | Exit the TUI |

### Node List (`n`)

Sortable, searchable table of node packs ranked by downloads.

- `/` — Search by name
- `f` — Set top-N filter (enter a number like `50`, `-10`, or `10:20`)
- `t` — Toggle stat filter (`+web-dirs` to include, `-pip-calls` to exclude)
- `c` — Clear all filters
- `Enter` — Open node detail view

### Dependencies (`d`)

Browse and search all dependencies in the ecosystem.

- `/` — Search by dependency name
- `v` — Toggle showing only duplicated (version-conflict) deps
- `Enter` — Open dependency detail view

### Summary (`s`)

Dashboard showing total node count, dependency statistics, and top dependencies at a glance.

### Graph (`g`)

Interactive in-terminal charts powered by plotext.

- `1`–`4` — Switch chart type: Downloads, Dep Count, Top Deps, Cumulative
- `j` / `k` — Move cursor left/right through data points
- `+` / `-` — Adjust number of items displayed
- `l` — Toggle log scale
- `Enter` — Open detail view for the highlighted item
- Click — Highlight a bar; double-click to open detail view
- Mouse hover — Shows item info in the top bar

## CLI Usage

Run a single command and exit with `-e`:

```bash
python analysis.py -e "/command"
```

> **Git Bash note:** Use `//command` (double slash) to prevent path interpretation.

### Commands

| Command | Description |
|---------|-------------|
| `/summary` | Ecosystem overview — node counts, top deps, warnings |
| `/list` | All unique dependencies (alphabetical, with usage counts) |
| `/top` | Top 20 most common dependencies |
| `/nodes` | Node list sorted by downloads; add a name to view details |
| `/update` | Fetch latest data from the ComfyUI registry |
| `/update-reqs` | Fetch actual deps from GitHub requirements.txt files |

### Filter Modifiers

| Modifier | Effect |
|----------|--------|
| `&top N` | Limit to top N nodes by downloads (negative = bottom N) |
| `&nodes id1,id2` | Filter to specific node IDs (or `&nodes file:list.txt`) |
| `&stat name` | Filter to nodes with a given stat (stackable) |
| `&!stat name` | Exclude nodes with a given stat |

### Display Modifiers

| Modifier | Effect |
|----------|--------|
| `&save` | Save results to `results/` with timestamp |
| `&all` | Show all results (no truncation) |
| `&dupes` | Show only deps with version conflicts (`/list` only) |
| `&sort` | Change sort order |

### Examples

```bash
# Summary of the whole ecosystem
python analysis.py -e "/summary"

# Dependencies with version conflicts in top 100 nodes
python analysis.py -e "//list &dupes &top 100"

# Search for torch-related packages
python analysis.py -e "torch* &all &save"

# View a specific node's dependencies
python analysis.py -e "//nodes comfyui-kjnodes"

# Update deps from requirements.txt for top 20 nodes
python analysis.py -e "//update-reqs &top 20"

# Filter nodes by stat
python analysis.py -e "//nodes &stat web-dirs &top 50"
```

## Architecture

```
core/               Core library modules
  registry.py         Registry API client
  data.py             Node data loading and session init
  dependencies.py     Dependency compilation and analysis
  requirements.py     requirements.txt fetching/parsing
  modifiers.py        Query modifier parsing and filtering
  cache.py            Disk cache management
  formatters.py       CLI output formatting
  utils.py            Shared utilities
dep_tui/            Textual TUI application
  app.py              Main App class and keybindings
  state.py            Shared application state
  screens/            Screen implementations (node list, dep search, dashboard, detail views)
analysis.py         CLI entry point
```

## Data & Caching

Node data is cached in `.cache/` after the first fetch from the ComfyUI registry. On subsequent runs the cached data is loaded instantly.

- Use `/update` (CLI) or `u` (TUI) to refresh from the registry
- Cache staleness is shown in the TUI status bar
- Requirements.txt updates (via `/update-reqs`) are session-scoped

## Requirements

- Python 3.10+
- `requests` — registry API access
- `textual` — TUI framework (for `python -m dep_tui`)
- `textual-plotext` — Terminal plotting for the Graph screen
