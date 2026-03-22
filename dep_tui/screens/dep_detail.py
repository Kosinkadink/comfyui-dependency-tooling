"""Dependency detail screen — shows which nodes use a specific dependency."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static

from core.dependencies import analyze_specific_dependency


class DepDetailScreen(Screen):
    """Detail view for a specific dependency — which nodes use it and versions."""

    BINDINGS = [
        Binding("escape", "pop_screen", "Back", show=True),
    ]

    def __init__(self, dep_name: str) -> None:
        super().__init__()
        self.dep_name = dep_name

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="dep-detail-scroll")
        yield Footer()

    def on_mount(self) -> None:
        state = self.app.state
        nodes = state.filtered_nodes()
        result = analyze_specific_dependency(nodes, self.dep_name)

        container = self.query_one("#dep-detail-scroll", VerticalScroll)

        # Header
        header_lines = [
            f"[bold]Dependency: {result['dependency_name']}[/bold]",
            f"Nodes using: {result['total_nodes']}",
        ]
        if result['commented_count'] > 0:
            header_lines.append(f"Commented-out in: {result['commented_count']} nodes")

        container.mount(Static("\n".join(header_lines), classes="detail-section"))

        # Version specs
        if result['sorted_versions']:
            version_lines = ["[bold]Version Specifications[/bold]"]
            for version, count in result['sorted_versions']:
                version_lines.append(f"  {version:30} — {count} nodes")
            container.mount(Static("\n".join(version_lines), classes="detail-section"))

        # Nodes using this dependency
        if result['nodes_using']:
            sorted_nodes = sorted(result['nodes_using'],
                                key=lambda x: x.get('downloads', 0), reverse=True)

            node_lines = [f"[bold]Nodes ({len(sorted_nodes)})[/bold]"]
            for i, node in enumerate(sorted_nodes, 1):
                node_lines.append(
                    f"  {i:3}. {node['node_name']}"
                    f"  (#{node.get('rank', '?')}  {node.get('downloads', 0):,} dl)"
                    f"  — {node['dependency_spec']}"
                )
            container.mount(Static("\n".join(node_lines), classes="detail-section"))

    def action_pop_screen(self) -> None:
        self.app.pop_screen()
