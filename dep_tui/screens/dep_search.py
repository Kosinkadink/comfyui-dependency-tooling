"""Dependency search screen — search, list, and dupes view."""

from __future__ import annotations

import fnmatch

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Input, Static

from core.dependencies import compile_dependencies


class DepSearchScreen(Screen):
    """Search and browse dependencies across all nodes."""

    BINDINGS = [
        Binding("slash", "search", "Search", show=True),
        Binding("escape", "cancel_search", "Cancel", show=False),
        Binding("v", "toggle_dupes", "Dupes", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._search_visible = False
        self._show_dupes = False
        self._search_text = ""
        self._sort_key = "count"
        self._sort_reverse = True

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search dependencies (use * for wildcard)...", id="dep-search", classes="search-input")
        yield DataTable(id="dep-table")
        yield Static("", id="filter-bar", classes="filter-bar")
        yield Static("", id="status-bar", classes="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        search_input = self.query_one("#dep-search", Input)
        search_input.display = False

        table = self.query_one("#dep-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True

        table.add_column("Dependency", key="name", width=35)
        table.add_column("Nodes", key="count", width=8)
        table.add_column("Versions", key="versions", width=10)
        table.add_column("Top Spec", key="top_spec", width=30)

        self._refresh_table()
        table.focus()

    def _refresh_table(self) -> None:
        table = self.query_one("#dep-table", DataTable)
        table.clear()

        state = self.app.state
        nodes = state.filtered_nodes()
        dep_analysis = compile_dependencies(nodes)

        rows = []
        for dep_name in dep_analysis['unique_base_dependencies']:
            count = dep_analysis['dependency_count'].get(dep_name, 0)
            versions = dep_analysis['dependency_versions'].get(dep_name, set())
            version_count = len(versions)

            # Most common spec
            top_spec = dep_name
            if versions:
                sorted_specs = sorted(versions)
                top_spec = sorted_specs[0] if sorted_specs else dep_name

            rows.append({
                'name': dep_name,
                'count': count,
                'version_count': version_count,
                'top_spec': top_spec,
                'has_dupes': version_count > 1,
            })

        # Search filter
        if self._search_text:
            pattern = self._search_text.lower()
            if '*' in pattern:
                rows = [r for r in rows if fnmatch.fnmatch(r['name'].lower(), pattern)]
            else:
                rows = [r for r in rows if pattern in r['name'].lower()]

        # Dupes filter
        if self._show_dupes:
            rows = [r for r in rows if r['has_dupes']]

        # Sort
        rows.sort(key=lambda r: r.get(self._sort_key, 0), reverse=self._sort_reverse)

        for r in rows:
            dupes_marker = "⚠" if r['has_dupes'] else ""
            table.add_row(
                r['name'],
                str(r['count']),
                f"{r['version_count']}{dupes_marker}",
                r['top_spec'],
                key=r['name'],
            )

        self._update_bars(len(rows), len(dep_analysis['unique_base_dependencies']))

    def _update_bars(self, shown: int, total: int) -> None:
        state = self.app.state
        mode = "dupes only" if self._show_dupes else "all"
        search_info = f' matching "{self._search_text}"' if self._search_text else ""

        status = self.query_one("#status-bar", Static)
        status.update(f" {shown}/{total} dependencies ({mode}){search_info} | cache: {state.cache_status}")

        bar = self.query_one("#filter-bar", Static)
        if state.filters.active:
            bar.update(f" Filters: {state.filters.summary()}")
        else:
            bar.update(" v=toggle dupes | /=search | click row for details")

    # -- Sorting --

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        key = str(event.column_key)
        if key == self._sort_key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_key = key
            self._sort_reverse = key == "count"  # default descending for count
        self._refresh_table()

    # -- Row selection --

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        dep_name = str(event.row_key.value)
        from .dep_detail import DepDetailScreen
        self.app.push_screen(DepDetailScreen(dep_name))

    # -- Search --

    def action_search(self) -> None:
        search_input = self.query_one("#dep-search", Input)
        search_input.display = True
        search_input.value = self._search_text
        search_input.focus()
        self._search_visible = True

    def action_cancel_search(self) -> None:
        if self._search_visible:
            search_input = self.query_one("#dep-search", Input)
            search_input.display = False
            self._search_visible = False
            self.query_one("#dep-table", DataTable).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "dep-search":
            self._search_text = event.value.strip()
            self._refresh_table()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._search_text = event.value.strip()
        event.input.display = False
        self._search_visible = False
        self._refresh_table()
        self.query_one("#dep-table", DataTable).focus()

    # -- Dupes toggle --

    def on_screen_resume(self) -> None:
        self._refresh_table()

    def action_toggle_dupes(self) -> None:
        self._show_dupes = not self._show_dupes
        self._refresh_table()
