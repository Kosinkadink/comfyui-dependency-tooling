"""Node detail screen — full info for a single node pack."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static

from core.utils import parse_dependency_string


class NodeDetailScreen(Screen):
    """Detailed view of a single node pack."""

    BINDINGS = [
        Binding("escape", "pop_screen", "Back", show=True),
    ]

    def __init__(self, node_id: str) -> None:
        super().__init__()
        self.node_id = node_id

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="detail-scroll")
        yield Footer()

    def on_mount(self) -> None:
        state = self.app.state
        nd = state.nodes_dict.get(self.node_id, {})
        container = self.query_one("#detail-scroll", VerticalScroll)

        if not nd:
            container.mount(Static(f"Node '{self.node_id}' not found."))
            return

        # Header
        name = nd.get('name', self.node_id)
        rank = nd.get('_rank', 'N/A')
        downloads = nd.get('downloads', 0)
        stars = nd.get('github_stars', 0)
        repo = nd.get('repository', 'N/A')
        description = nd.get('description', 'N/A')

        header_lines = [
            f"[bold]{name}[/bold]",
            f"ID: {self.node_id}",
            f"Rank: #{rank}  |  Downloads: {downloads:,}  |  Stars: {stars:,}",
            f"Repository: {repo}",
            f"Description: {description}",
        ]

        # Node IDs info
        node_ids = nd.get('_node_ids', [])
        has_pattern = nd.get('_has_node_pattern', False)
        if node_ids or has_pattern:
            count = len(node_ids) if node_ids else 0
            suffix = '*' if has_pattern else ''
            header_lines.append(f"Individual Nodes: {count}{suffix}")

        # Version info
        lv = nd.get('latest_version', {})
        if lv:
            version = lv.get('version', 'N/A')
            date = 'N/A'
            if 'createdAt' in lv:
                date = lv['createdAt'][:10] if lv['createdAt'] else 'N/A'
            header_lines.append(f"Latest: {version}  |  Released: {date}")

        container.mount(Static("\n".join(header_lines), classes="detail-section"))

        # Dependencies
        updated_from_reqs = lv.get('_updated_from_requirements', False) if lv else False
        original_backup = state.original_deps_backup.get(self.node_id, {})
        original_deps = original_backup.get('dependencies', []) if original_backup else []

        if lv and 'dependencies' in lv and lv['dependencies']:
            active, git, pip_cmds, commented = [], [], [], []
            for dep in lv['dependencies']:
                parsed = parse_dependency_string(dep)
                if parsed['is_comment']:
                    commented.append(parsed['original_str'])
                elif parsed['is_pip_command']:
                    pip_cmds.append(parsed['cleaned_str'])
                elif parsed['skip']:
                    continue
                elif parsed['is_git_dep']:
                    git.append(parsed['cleaned_str'])
                else:
                    active.append(parsed['cleaned_str'])

            sections = []

            # Show source indicator
            if updated_from_reqs:
                source_label = "[italic]Source: requirements.txt[/italic]"
                if original_deps:
                    def _norm(s):
                        return str(s).strip().replace(' ', '')
                    orig_set = set(_norm(d) for d in original_deps if not str(d).strip().startswith('#'))
                    curr_set = set(_norm(d) for d in lv['dependencies'])
                    if orig_set != curr_set:
                        added = curr_set - orig_set
                        removed = orig_set - curr_set
                        diff_parts = []
                        if added:
                            diff_parts.append(f"+{len(added)} added")
                        if removed:
                            diff_parts.append(f"-{len(removed)} removed")
                        source_label += f"  [bold yellow]⚠ Differs from registry ({', '.join(diff_parts)})[/bold yellow]"
                    else:
                        source_label += "  [green]✓ Matches registry[/green]"
                else:
                    source_label += "  [dim](no registry deps to compare)[/dim]"
                sections.append(source_label)

            if active:
                items = "\n".join(f"  {i}. {d}" for i, d in enumerate(active, 1))
                sections.append(f"[bold]Active Dependencies ({len(active)})[/bold]\n{items}")
            if git:
                items = "\n".join(f"  {i}. {d}" for i, d in enumerate(git, 1))
                sections.append(f"[bold]Git Dependencies ({len(git)})[/bold]\n{items}")
            if pip_cmds:
                items = "\n".join(f"  {i}. {d}" for i, d in enumerate(pip_cmds, 1))
                sections.append(f"[bold]Pip Flags ({len(pip_cmds)})[/bold]\n{items}")
            if commented:
                items = "\n".join(f"  {i}. {d}" for i, d in enumerate(commented, 1))
                sections.append(f"[bold]Commented ({len(commented)})[/bold]\n{items}")

            # Show original registry deps if they differ
            if updated_from_reqs and original_deps:
                orig_set = set(_norm(d) for d in original_deps if not str(d).strip().startswith('#'))
                curr_set = set(_norm(d) for d in lv['dependencies'])
                if orig_set != curr_set:
                    orig_items = "\n".join(f"  {i}. {d}" for i, d in enumerate(sorted(original_deps), 1))
                    sections.append(f"[bold dim]Original Registry Dependencies ({len(original_deps)})[/bold dim]\n[dim]{orig_items}[/dim]")

            if sections:
                container.mount(Static("\n\n".join(sections), classes="detail-section"))
            else:
                container.mount(Static("No dependencies listed.", classes="detail-section"))
        else:
            container.mount(Static("No dependencies listed.", classes="detail-section"))

        # Stats
        node_stats = nd.get('_stats', {})
        if node_stats:
            stat_lines = []
            for stat_name in sorted(node_stats.keys()):
                files = node_stats[stat_name]
                if files:
                    display = stat_name.replace('-', ' ').replace('_', ' ').title()
                    stat_lines.append(f"[bold]{display} ({len(files)})[/bold]")
                    for fp in files[:20]:
                        stat_lines.append(f"  - {fp}")
                    if len(files) > 20:
                        stat_lines.append(f"  ... and {len(files) - 20} more")

            if stat_lines:
                container.mount(Static("\n".join(stat_lines), classes="detail-section"))

    def action_pop_screen(self) -> None:
        self.app.pop_screen()
