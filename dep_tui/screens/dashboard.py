"""Dashboard / summary screen — overview stats for the ecosystem."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static

from core.dependencies import compile_dependencies
from core.utils import get_all_stat_names


class DashboardScreen(Screen):
    """Overview summary of the ComfyUI dependency ecosystem."""

    BINDINGS = []

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="dashboard-scroll")
        yield Static("", id="status-bar", classes="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_content()

    def on_screen_resume(self) -> None:
        self._refresh_content()

    def _refresh_content(self) -> None:
        state = self.app.state
        nodes = state.filtered_nodes()
        dep_analysis = compile_dependencies(nodes)

        container = self.query_one("#dashboard-scroll", VerticalScroll)
        container.remove_children()

        # Overview panel
        total = len(nodes)
        with_deps = dep_analysis['nodes_with_deps_count']
        without_deps = dep_analysis['nodes_without_deps_count']
        pct = (with_deps * 100 // total) if total else 0

        overview = [
            "[bold]Ecosystem Overview[/bold]",
            f"  Total nodes:              {total:,}",
            f"  With dependencies:        {with_deps:,} ({pct}%)",
            f"  Without dependencies:     {without_deps:,}",
            f"  Total dep references:     {dep_analysis['total_dependencies']:,}",
            f"  Unique packages:          {dep_analysis['unique_count']:,}",
            f"  Unique raw specs:         {dep_analysis['unique_raw_count']:,}",
        ]

        if dep_analysis['nodes_with_commented_count'] > 0:
            overview.append(f"  With commented deps:      {dep_analysis['nodes_with_commented_count']:,}")
        if dep_analysis['nodes_with_pip_commands_count'] > 0:
            overview.append(f"  With pip flags:           {dep_analysis['nodes_with_pip_commands_count']:,}")
        if dep_analysis['nodes_with_git_deps_count'] > 0:
            overview.append(f"  With git dependencies:    {dep_analysis['nodes_with_git_deps_count']:,}")

        container.mount(Static("\n".join(overview), classes="stat-panel"))

        # Top 15 dependencies
        top_deps = dep_analysis['sorted_by_frequency'][:15]
        if top_deps:
            dep_lines = ["[bold]Top 15 Dependencies[/bold]"]
            for dep, count in top_deps:
                bar_len = int(count / top_deps[0][1] * 30) if top_deps[0][1] else 0
                bar = "█" * bar_len
                dep_lines.append(f"  {dep:30} {count:4}  {bar}")
            container.mount(Static("\n".join(dep_lines), classes="stat-panel"))

        # Git dependencies breakdown
        if dep_analysis['nodes_with_git_deps_count'] > 0:
            git_lines = ["[bold]Git Dependencies[/bold]"]
            git_lines.append(f"  Total unique: {len(dep_analysis['unique_git_dependencies'])}")
            if dep_analysis['sorted_git_dependency_types']:
                for dep_type, count in dep_analysis['sorted_git_dependency_types']:
                    git_lines.append(f"  {dep_type}: {count}")
            container.mount(Static("\n".join(git_lines), classes="stat-panel"))

        # Pip commands
        if dep_analysis['nodes_with_pip_commands_count'] > 0:
            pip_lines = ["[bold]Pip Command Flags[/bold]"]
            for cmd, count in dep_analysis['sorted_pip_commands'][:5]:
                pip_lines.append(f"  {cmd}: {count} nodes")
            container.mount(Static("\n".join(pip_lines), classes="stat-panel"))

        # Stats from node-stats/
        all_stats = get_all_stat_names(nodes)
        for stat_name in all_stats:
            count = sum(
                1 for nd in nodes.values()
                if nd.get('_stats', {}).get(stat_name)
            )
            if count > 0:
                display = stat_name.replace('-', ' ').replace('_', ' ').title()
                pct = count * 100 // total if total else 0
                container.mount(
                    Static(f"[bold]{display}[/bold]: {count:,} nodes ({pct}%)", classes="stat-panel")
                )

        # Status bar
        status = self.query_one("#status-bar", Static)
        filter_info = f" | filters: {state.filters.summary()}" if state.filters.active else ""
        status.update(f" {total:,} nodes analyzed | cache: {state.cache_status}{filter_info}")

