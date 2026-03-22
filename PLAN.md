# Issue #1: Cleanup Plan

## Problem Statement

The codebase was written before using Amp and has poor architecture. Using the tool is painful — the interactive mode is a plain-text REPL with no navigation, long outputs scroll off-screen, and graphs open in a browser via plotly.

**Goal**: Clean up architecture, improve usage and visuals. Build a Textual TUI (like `pr_tracker_tui`).

### Decisions

- **Remove plotly** — the plotly graph code was messy. Drop it entirely; can revisit from scratch later once the core is solid.
- **TUI package structure** — use a package with separate screen files (like `pr_tracker_tui`), not a monolith.
- **Data caching** — cache `nodes.json` locally with timestamps in a `.cache/` directory so the app starts instantly, like `pr_tracker`'s pattern. Auto-prompt if cache is >7 days old.
- **Filter persistence** — filters persist across screen navigation in the TUI (matches how the tool is actually used).
- **Build incrementally** — start with the most-used screens (NodeList + DependencySearch), iterate from there.
- **Modifier syntax: Option C (Hybrid)** — TUI users get UI controls for filters (no modifier syntax to learn). CLI `-e` mode gets standard `--flag` style via argparse. The core filter pipeline accepts a structured dict either way.

---

## Phase 1: Refactor into Clean Library ✅ DONE

Split the 2727-line monolithic `analysis.py` into focused modules under `core/`:

| Module | Responsibility |
|---|---|
| `core/registry.py` | API fetching from `api.comfy.org`, saving `nodes.json` and `extension-node-map.json` |
| `core/data.py` | Data loading, rank calculation, missing-nodes mapping, cached requirements, session initialization |
| `core/dependencies.py` | Dependency compilation, specific/wildcard analysis |
| `core/requirements.py` | `requirements.txt` fetching, parsing, caching, concurrent updating |
| `core/modifiers.py` | Centralized modifier parsing + filter application helpers |
| `core/formatters.py` | All plain-text output formatting |

`analysis.py` is now a thin CLI entry point (~530 lines).

---

## Phase 1.5: Modifier System + Caching Cleanup

### 1.5a: Refactor modifier system

**Separate filters from display options** in the parsed result:

```python
{
    'filters': {
        'top': None,           # int, tuple, or None
        'nodes': None,         # list of node IDs or None
        'include_stats': [],   # stats nodes MUST have
        'exclude_stats': [],   # stats nodes must NOT have (&!stat)
    },
    'display': {
        'save': False,
        'all': False,
        'dupes': False,
        'sort': None,          # stat name to sort by
    },
    'clean_query': '...',      # query with all modifiers stripped
}
```

**Remove `&hide-markers`** — plotly-specific, no longer needed.

**Add `&!stat` negation** — filter to nodes WITHOUT a stat:
```
/nodes &!stat web-dirs              # nodes without web directories
/nodes &stat routes &!stat pip-calls # has routes but not pip calls
```

**Add unknown modifier validation** — after stripping all known modifiers, scan for leftover `&` tokens and warn.

**Make filters universal** — every command passes through `apply_all_filters()`. The current gaps:

| Filter | Currently missing from | After |
|---|---|---|
| `&nodes` | `/list`, `/top` | All commands |
| `&stat` / `&!stat` | `/list`, `/top`, dep search | All commands |

### 1.5b: Add data caching

- Add `.cache/` directory for `nodes.json` and `extension-node-map.json` with timestamp metadata
- On startup, load from cache instantly; show cache age in status output
- `/update` refreshes the cache and records new timestamp
- Auto-prompt or warn if cache is >7 days old

### 1.5c: Remove plotly

- Remove `src/graph.py`
- Remove plotly from `requirements.txt`
- Remove `/graph` command handler from `analysis.py`
- Keep the graph-related data calculations in `core/` (cumulative deps, etc.) — they'll be useful for `textual-plotext` later

### 1.5d: CLI `--flag` style for `-e` mode

Update `analysis.py` argparse to accept standard flags for execute mode:

```bash
python analysis.py -e "/nodes --top 20 --stat web-dirs"
python analysis.py -e "numpy --top 50 --save"
python analysis.py -e "/list --dupes --top 100"
python analysis.py -e "/nodes --no-stat pip-calls"
```

The interactive REPL keeps `&modifier` syntax for now (it will be replaced by the TUI in Phase 2).

---

## Phase 2: Build Textual TUI

### Dependencies
- `textual`
- `textual-plotext` (for in-terminal charts)

### Package Structure

```
dep_tui/
├── __init__.py
├── __main__.py          # python -m dep_tui
├── app.py               # DepAnalyzerApp(App)
├── state.py             # Shared filter state, loaded data, session
├── screens/
│   ├── __init__.py
│   ├── dashboard.py     # DashboardScreen (summary)
│   ├── node_list.py     # NodeListScreen (sortable table)
│   ├── node_detail.py   # NodeDetailScreen (single node)
│   ├── dep_search.py    # DependencySearchScreen (search + list + dupes)
│   └── graph.py         # GraphScreen (textual-plotext charts)
└── styles/
    └── app.tcss         # Textual CSS
```

### Screens (build order)

#### 1. NodeListScreen (most used)
- Sortable `DataTable`: rank, name, downloads, stars, deps, stat indicators
- Search bar for fuzzy-finding nodes
- Filter bar showing active filters (top-N, stats)
- Press Enter on a row → push `NodeDetailScreen`

#### 2. DependencySearchScreen
- Search input with live results
- Results `DataTable`: dependency name, node count, version specs
- Toggle dupes view
- Click a dependency → show full detail panel

#### 3. DashboardScreen
- Rich summary panels: total nodes, dep counts, top 10 deps
- Git deps, pip commands, commented deps stats
- Stat summaries (web-dirs, routes, etc.)

#### 4. NodeDetailScreen
- Full node info panel: metadata, all dependencies (active, git, pip, commented), stat files
- Pushed from NodeListScreen

#### 5. GraphScreen (last)
- `textual-plotext` bar charts for downloads, dep counts, stat counts
- Line chart for cumulative dependencies
- Sortable by different metrics

### Shared UI
- **Footer** — keybindings: `n` = nodes, `d` = deps, `s` = summary, `g` = graph, `q` = quit
- **Filter bar** — persistent across screens, shows active filters, editable via UI controls
- **Status bar** — node count, cache age, active filter summary

### Entry Points
- `python -m dep_tui` — launches the TUI
- `python analysis.py -e "..."` — CLI execute mode (unchanged, uses `core/formatters.py`)

---

## Phase 3: Polish & Parity ✅ DONE

- ✅ `/update` as TUI modal with progress bar (`u` key → `UpdateScreen`)
- ✅ `/update-reqs` as TUI modal using concurrent fetcher with progress callback
- ✅ Stat filter UI (`t` key on NodeListScreen — `+name`/`-name`/toggle)
- ✅ Auto-staleness check on startup (notification if cache >7 days)
- ✅ Updated `README.md`

---

## Phase 4: GraphScreen

Add in-terminal charts using `textual-plotext` (wrapper around the `plotext` library).

### Dependency

```
pip install textual-plotext
```

Add `textual-plotext` to `requirements.txt`.

### Screen: `dep_tui/screens/graph.py`

New mode-switchable screen (`g` key) with multiple chart views:

| Chart | Data Source | Description |
|---|---|---|
| **Downloads** | `node_data['downloads']` | Bar chart of downloads per node by rank. X=rank, Y=downloads |
| **Dep Count** | Per-node dep count | Bar chart of dependency count per node by rank |
| **Top Deps** | `dep_analysis['sorted_by_frequency']` | Horizontal bar chart of the N most common dependencies |
| **Cumulative** | Running unique dep accumulation | Line chart: X=node rank, Y=total unique deps seen so far |

### UI

- `PlotextPlot` widget fills the main area
- Navigation bar or keybindings to switch chart type: `1`=downloads, `2`=deps, `3`=top deps, `4`=cumulative
- Charts respect active filters (top-N, stats) via `state.filtered_nodes()`
- Status bar shows chart type + filter summary

### Implementation Notes

- Use `textual-plotext`'s `PlotextPlot` widget — access `plt` via `widget.plt`
- Call `plt.bar()`, `plt.scatter()`, `plt.plot()` etc. per chart type
- Clear with `plt.clear_figure()` before redrawing
- No `plt.show()` needed — the widget handles rendering
- Add `on_screen_resume()` to redraw when filters change
- Use `textual-design-dark` theme for consistent look

### Build Order

1. Scaffold the screen with PlotextPlot + chart type switching
2. Implement Downloads bar chart (most visual impact)
3. Add Top Deps horizontal bar chart
4. Add Dep Count bar chart
5. Add Cumulative line chart
