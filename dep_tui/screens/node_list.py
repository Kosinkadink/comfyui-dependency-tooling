"""Node list screen — sortable DataTable of all node packs."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Input, Static


COLUMNS = [
    ("Rank", "rank", 6),
    ("Name", "name", 40),
    ("Downloads", "downloads", 12),
    ("Stars", "stars", 8),
    ("Deps", "deps", 6),
    ("Version", "version", 12),
]


class NodeListScreen(Screen):
    """Sortable, searchable table of node packs."""

    BINDINGS = [
        Binding("slash", "search", "Search", show=True),
        Binding("escape", "cancel_search", "Cancel", show=False),
        Binding("f", "cycle_filter", "Top N", show=True),
        Binding("t", "toggle_stat", "Stats", show=True),
        Binding("c", "clear_filters", "Clear", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._search_visible = False
        self._search_text = ""
        self._sort_key = "rank"
        self._sort_reverse = False

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search nodes...", id="search-input", classes="search-input")
        yield Input(placeholder="Enter top N (e.g. 50, -10, 10:20) or empty to clear", id="top-n-input", classes="search-input")
        yield Input(placeholder="Stat filter (+name, -name, or name to toggle)", id="stat-input", classes="search-input")
        yield DataTable(id="node-table")
        yield Static("", id="filter-bar", classes="filter-bar")
        yield Static("", id="status-bar", classes="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        for inp_id in ["search-input", "top-n-input", "stat-input"]:
            self.query_one(f"#{inp_id}", Input).display = False

        table = self.query_one("#node-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True

        for label, key, width in COLUMNS:
            table.add_column(label, key=key, width=width)

        self._refresh_table()
        self._update_status()
        table.focus()

    def _refresh_table(self) -> None:
        """Rebuild the table rows from state."""
        table = self.query_one("#node-table", DataTable)
        table.clear()

        state = self.app.state
        nodes = state.filtered_nodes()

        # Build row data
        rows = []
        for node_id, nd in nodes.items():
            rank = nd.get('_rank', 0)
            name = nd.get('name', node_id)
            downloads = nd.get('downloads', 0)
            stars = nd.get('github_stars', 0)

            dep_count = 0
            lv = nd.get('latest_version', {})
            if lv and 'dependencies' in lv:
                deps = lv['dependencies']
                if deps and isinstance(deps, list):
                    dep_count = sum(
                        1 for d in deps
                        if not str(d).strip().startswith('#')
                        and not str(d).strip().startswith('--')
                    )

            version = lv.get('version', '') if lv else ''

            rows.append({
                'id': node_id,
                'rank': rank,
                'name': name,
                'downloads': downloads,
                'stars': stars,
                'deps': dep_count,
                'version': version,
            })

        # Apply search filter
        search = self._search_text.lower()
        if search:
            rows = [r for r in rows if search in r['name'].lower() or search in r['id'].lower()]

        # Sort — numeric columns default to descending, rank defaults to ascending
        reverse = self._sort_reverse
        if self._sort_key in ("downloads", "stars", "deps"):
            reverse = not self._sort_reverse
        rows.sort(key=lambda r: r.get(self._sort_key, 0), reverse=reverse)

        for r in rows:
            table.add_row(
                str(r['rank']),
                r['name'],
                f"{r['downloads']:,}",
                f"{r['stars']:,}",
                str(r['deps']),
                r['version'],
                key=r['id'],
            )

        self._update_filter_bar()

    def _update_status(self) -> None:
        state = self.app.state
        total = len(state.nodes_dict)
        shown = self.query_one("#node-table", DataTable).row_count
        status = self.query_one("#status-bar", Static)
        status.update(f" {shown}/{total} nodes | cache: {state.cache_status}")

    def _update_filter_bar(self) -> None:
        state = self.app.state
        bar = self.query_one("#filter-bar", Static)
        if state.filters.active:
            bar.update(f" Filters: {state.filters.summary()}")
        else:
            bar.update(" No active filters (f=set top-N, c=clear)")
        self._update_status()

    # -- Sorting --

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        key = str(event.column_key)
        if key == self._sort_key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_key = key
            self._sort_reverse = False
        self._refresh_table()

    # -- Row selection --

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        node_id = str(event.row_key.value)
        from .node_detail import NodeDetailScreen
        self.app.push_screen(NodeDetailScreen(node_id))

    # -- Search --

    def on_screen_resume(self) -> None:
        self._refresh_table()

    def action_search(self) -> None:
        search_input = self.query_one("#search-input", Input)
        search_input.display = True
        search_input.value = self._search_text
        search_input.focus()
        self._search_visible = True

    def action_cancel_search(self) -> None:
        for inp_id in ["search-input", "top-n-input", "stat-input"]:
            self.query_one(f"#{inp_id}", Input).display = False
        self._search_visible = False
        self.query_one("#node-table", DataTable).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            self._search_text = event.value.strip()
            self._refresh_table()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search-input":
            self._search_text = event.value.strip()
            event.input.display = False
            self._search_visible = False
            self._refresh_table()
            self.query_one("#node-table", DataTable).focus()
        elif event.input.id == "top-n-input":
            self._apply_top_n(event.value.strip())
            event.input.display = False
            self.query_one("#node-table", DataTable).focus()
        elif event.input.id == "stat-input":
            self._apply_stat_filter(event.value.strip())
            event.input.display = False
            self.query_one("#node-table", DataTable).focus()

    # -- Filters --

    def action_cycle_filter(self) -> None:
        """Show input to set top-N filter."""
        inp = self.query_one("#top-n-input", Input)
        if inp.display:
            inp.display = False
            self.query_one("#node-table", DataTable).focus()
        else:
            inp.display = True
            inp.value = ""
            inp.focus()

    def _apply_top_n(self, value: str) -> None:
        if not value:
            self.app.state.filters.top = None
        elif ':' in value:
            parts = value.split(':')
            try:
                self.app.state.filters.top = (int(parts[0]), int(parts[1]))
            except (ValueError, IndexError):
                return
        else:
            try:
                self.app.state.filters.top = int(value)
            except ValueError:
                return
        self._refresh_table()

    def action_toggle_stat(self) -> None:
        """Show input for stat filtering."""
        from core.utils import get_all_stat_names

        stats = get_all_stat_names(self.app.state.nodes_dict)
        if not stats:
            return

        inp = self.query_one("#stat-input", Input)
        if inp.display:
            inp.display = False
            self.query_one("#node-table", DataTable).focus()
        else:
            inp.placeholder = f"Stat filter (+include, -exclude, toggle): {', '.join(stats)}"
            inp.display = True
            inp.value = ""
            inp.focus()

    def _apply_stat_filter(self, value: str) -> None:
        if not value:
            return
        filters = self.app.state.filters
        if value.startswith('+'):
            stat = value[1:].strip()
            if stat and stat not in filters.include_stats:
                filters.include_stats.append(stat)
                if stat in filters.exclude_stats:
                    filters.exclude_stats.remove(stat)
        elif value.startswith('-'):
            stat = value[1:].strip()
            if stat and stat not in filters.exclude_stats:
                filters.exclude_stats.append(stat)
                if stat in filters.include_stats:
                    filters.include_stats.remove(stat)
        else:
            if value in filters.include_stats:
                filters.include_stats.remove(value)
            elif value in filters.exclude_stats:
                filters.exclude_stats.remove(value)
            else:
                filters.include_stats.append(value)
        self._refresh_table()

    def action_clear_filters(self) -> None:
        self.app.state.filters.clear()
        self._refresh_table()


