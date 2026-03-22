"""Graph screen — in-terminal charts via textual-plotext."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.events import MouseMove
from textual.screen import Screen
from textual.widgets import Footer, Static
from textual_plotext import PlotextPlot

from core.dependencies import compile_dependencies
from core.utils import parse_dependency_string


# Default display counts per chart type
DEFAULTS = {
    "downloads": 100,
    "deps": 100,
    "top_deps": 30,
    "cumulative": 0,  # 0 = show all
}

STEPS = [10, 20, 30, 50, 100, 200, 500, 0]  # 0 = all

# Approximate plotext margins (characters)
MARGIN_LEFT = 12
MARGIN_RIGHT = 2
MARGIN_TOP = 2
MARGIN_BOTTOM = 3

HIGHLIGHT_COLOR = "red+"


class GraphScreen(Screen):
    """In-terminal charts for dependency analysis."""

    BINDINGS = [
        Binding("1", "chart_downloads", "Downloads", show=True),
        Binding("2", "chart_deps", "Dep Count", show=True),
        Binding("3", "chart_top_deps", "Top Deps", show=True),
        Binding("4", "chart_cumulative", "Cumulative", show=True),
        Binding("plus,equal", "increase", "+N", show=True),
        Binding("minus,underscore", "decrease", "-N", show=True),
        Binding("l", "toggle_log", "Log Scale", show=True),
        Binding("j", "cursor_left", "← j", show=True),
        Binding("k", "cursor_right", "→ k", show=True),
        Binding("enter", "open_detail", "Detail", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._chart_type = "downloads"
        self._display_n: dict[str, int] = dict(DEFAULTS)
        self._log_scale = False
        # Data for hover/cursor inspection
        self._chart_data: list[dict] = []
        self._cursor_idx: int = -1
        self._status_base: str = ""
        # Cached draw state for highlight redraws
        self._draw_x: list = []
        self._draw_y: list = []
        self._draw_use_names: bool = False
        self._draw_bar_width: float | None = None
        self._draw_orientation: str = "vertical"

    def compose(self) -> ComposeResult:
        yield Static(" Loading...", id="graph-info")
        yield PlotextPlot(id="graph-plot")
        yield Footer()

    def on_mount(self) -> None:
        self._draw()

    def on_screen_resume(self) -> None:
        self._draw()

    def _refresh_content(self) -> None:
        self._draw()

    def _current_n(self) -> int:
        return self._display_n.get(self._chart_type, 0)

    def _draw(self) -> None:
        state = self.app.state
        nodes = state.filtered_nodes()

        if not nodes:
            self._update_status("No data — press u to update")
            return

        n = self._current_n()
        chart_title = ""
        self._chart_data = []
        self._cursor_idx = -1
        self._draw_x = []
        self._draw_y = []
        self._draw_use_names = False
        self._draw_bar_width = None
        self._draw_orientation = "vertical"

        if self._chart_type == "downloads":
            chart_title = self._prepare_downloads(nodes, n)
        elif self._chart_type == "deps":
            chart_title = self._prepare_deps(nodes, n)
        elif self._chart_type == "top_deps":
            chart_title = self._prepare_top_deps(nodes, n)
        elif self._chart_type == "cumulative":
            chart_title = self._prepare_cumulative(nodes, n)

        self._render_chart(chart_title)

        n_label = "all" if n == 0 else f"top {n}"
        log_label = " [log]" if self._log_scale else ""
        filter_info = f" | filters: {state.filters.summary()}" if state.filters.active else ""
        self._status_base = f"{chart_title} — {n_label} of {len(nodes):,} nodes{log_label}{filter_info}"
        self._update_status(f"{self._status_base} | +/- adjust, l=log, j/k cursor")

    def _render_chart(self, title: str | None = None) -> None:
        """Render the chart with optional cursor highlight."""
        plot = self.query_one("#graph-plot", PlotextPlot)
        plt = plot.plt
        plt.clear_figure()
        plt.theme("dark")

        if self._chart_type == "cumulative":
            plt.plot(self._draw_x, self._draw_y)
            if 0 <= self._cursor_idx < len(self._draw_x):
                plt.scatter(
                    [self._draw_x[self._cursor_idx]],
                    [self._draw_y[self._cursor_idx]],
                    color=HIGHLIGHT_COLOR,
                    marker="hd",
                )
        elif self._draw_x and self._draw_y:
            orient = self._draw_orientation
            width = self._draw_bar_width
            count = len(self._draw_x)

            # Use numeric positions so split bar calls align correctly
            if self._draw_use_names:
                positions = list(range(1, count + 1))
                labels = self._draw_x
            else:
                positions = self._draw_x
                labels = None

            if 0 <= self._cursor_idx < count:
                hi = self._cursor_idx
                norm_pos = [p for i, p in enumerate(positions) if i != hi]
                norm_val = [v for i, v in enumerate(self._draw_y) if i != hi]
                kw = {"orientation": orient} if orient != "vertical" else {}
                if width is not None:
                    kw["width"] = width
                if norm_pos:
                    plt.bar(norm_pos, norm_val, reset_ticks=False, **kw)
                plt.bar([positions[hi]], [self._draw_y[hi]], color=HIGHLIGHT_COLOR, reset_ticks=False, **kw)
            else:
                kw = {"orientation": orient} if orient != "vertical" else {}
                if width is not None:
                    kw["width"] = width
                plt.bar(positions, self._draw_y, reset_ticks=False, **kw)

            if labels:
                if orient == "horizontal":
                    plt.yticks(positions, labels)
                else:
                    plt.xticks(positions, labels)

        if title:
            plt.title(title)
        if self._chart_type == "top_deps":
            plt.xlabel("Nodes")
        elif self._chart_type == "cumulative":
            plt.xlabel("Rank")
            plt.ylabel("Unique Deps")
        else:
            plt.xlabel("Rank" if not self._draw_use_names else "Node")
            plt.ylabel("Downloads" if self._chart_type == "downloads" else "Dependencies")

        if self._log_scale and self._chart_type != "cumulative":
            plt.yscale("log")

        plot.refresh()

    def _prepare_downloads(self, nodes: dict, n: int) -> str:
        sorted_nodes = sorted(nodes.values(), key=lambda nd: nd.get('_rank', 0))
        if n > 0:
            sorted_nodes = sorted_nodes[:n]

        self._chart_data = [
            {"name": nd.get('name', '?'), "rank": nd.get('_rank', 0),
             "downloads": nd.get('downloads', 0), "id": nd.get('id', nd.get('name', '?'))}
            for nd in sorted_nodes
        ]

        if len(sorted_nodes) <= 50:
            self._draw_x = [nd.get('name', '') for nd in sorted_nodes]
            self._draw_use_names = True
        else:
            self._draw_x = [nd.get('_rank', 0) for nd in sorted_nodes]
            self._draw_bar_width = 1
        self._draw_y = [nd.get('downloads', 0) for nd in sorted_nodes]

        return "Downloads by Rank"

    def _prepare_deps(self, nodes: dict, n: int) -> str:
        sorted_nodes = sorted(nodes.values(), key=lambda nd: nd.get('_rank', 0))
        if n > 0:
            sorted_nodes = sorted_nodes[:n]

        dep_counts = []
        for nd in sorted_nodes:
            lv = nd.get('latest_version', {})
            deps = lv.get('dependencies', []) if lv else []
            count = 0
            if deps and isinstance(deps, list):
                count = sum(
                    1 for d in deps
                    if not str(d).strip().startswith('#')
                    and not str(d).strip().startswith('--')
                )
            dep_counts.append(count)

        self._chart_data = [
            {"name": nd.get('name', '?'), "rank": nd.get('_rank', 0),
             "deps": dc, "id": nd.get('id', nd.get('name', '?'))}
            for nd, dc in zip(sorted_nodes, dep_counts)
        ]

        if len(sorted_nodes) <= 50:
            self._draw_x = [nd.get('name', '') for nd in sorted_nodes]
            self._draw_use_names = True
        else:
            self._draw_x = [nd.get('_rank', 0) for nd in sorted_nodes]
            self._draw_bar_width = 1
        self._draw_y = dep_counts

        return "Dep Count by Rank"

    def _prepare_top_deps(self, nodes: dict, n: int) -> str:
        dep_analysis = compile_dependencies(nodes)
        show_n = n if n > 0 else 30
        top = dep_analysis['sorted_by_frequency'][:show_n]

        if not top:
            return "Top Dependencies"

        self._chart_data = [
            {"name": name, "count": count}
            for name, count in top
        ]

        # Reverse so highest is at top in horizontal bar
        self._draw_x = [name for name, _ in reversed(top)]
        self._draw_y = [count for _, count in reversed(top)]
        self._draw_use_names = True
        self._draw_orientation = "horizontal"

        return f"Top {len(top)} Dependencies"

    def _prepare_cumulative(self, nodes: dict, n: int) -> str:
        sorted_nodes = sorted(nodes.values(), key=lambda nd: nd.get('_rank', 0))
        if n > 0:
            sorted_nodes = sorted_nodes[:n]

        seen = set()
        ranks = []
        cumulative = []

        for nd in sorted_nodes:
            rank = nd.get('_rank', 0)
            lv = nd.get('latest_version', {})
            deps = lv.get('dependencies', []) if lv else []
            if deps and isinstance(deps, list):
                for d in deps:
                    d_str = str(d).strip()
                    if not d_str.startswith('#') and not d_str.startswith('--'):
                        parsed = parse_dependency_string(d_str)
                        if not parsed['skip'] and not parsed['is_pip_command']:
                            seen.add(parsed['base_name'])
            ranks.append(rank)
            cumulative.append(len(seen))

        self._chart_data = [
            {"name": nd.get('name', '?'), "rank": nd.get('_rank', 0),
             "cumulative": c, "id": nd.get('id', nd.get('name', '?'))}
            for nd, c in zip(sorted_nodes, cumulative)
        ]

        self._draw_x = ranks
        self._draw_y = cumulative

        return "Cumulative Deps"

    # -- Info display for hovered/cursored item --

    def _show_item_info(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._chart_data):
            self._update_status(f"{self._status_base} | +/- adjust, l=log, j/k cursor")
            return

        item = self._chart_data[idx]

        if self._chart_type == "downloads":
            info = f"#{item['rank']} {item['name']} — {item['downloads']:,} downloads"
        elif self._chart_type == "deps":
            info = f"#{item['rank']} {item['name']} — {item['deps']} deps"
        elif self._chart_type == "top_deps":
            info = f"{item['name']} — used by {item['count']} nodes"
        elif self._chart_type == "cumulative":
            info = f"#{item['rank']} {item['name']} — {item['cumulative']} unique deps so far"
        else:
            info = str(item)

        self._update_status(f" [{idx + 1}/{len(self._chart_data)}] {info}")

    # -- Mouse hover --

    def on_mouse_move(self, event: MouseMove) -> None:
        if not self._chart_data:
            return

        try:
            plot = self.query_one("#graph-plot", PlotextPlot)
        except Exception:
            return

        # Check if mouse is over the plot widget
        region = plot.region
        if not region.contains(event.screen_x, event.screen_y):
            return

        # Map mouse position to data index
        if self._chart_type == "top_deps":
            # Horizontal bar — map Y position to bar index (reversed order)
            plot_top = region.y + MARGIN_TOP
            plot_bottom = region.y + region.height - MARGIN_BOTTOM
            plot_height = plot_bottom - plot_top
            if plot_height <= 0:
                return
            rel_y = event.screen_y - plot_top
            # Bars are reversed in display (highest at top)
            idx = int(rel_y / plot_height * len(self._chart_data))
        else:
            # Vertical charts — map X position to data index
            plot_left = region.x + MARGIN_LEFT
            plot_right = region.x + region.width - MARGIN_RIGHT
            plot_width = plot_right - plot_left
            if plot_width <= 0:
                return
            rel_x = event.screen_x - plot_left
            idx = int(rel_x / plot_width * len(self._chart_data))

        idx = max(0, min(idx, len(self._chart_data) - 1))
        if idx != self._cursor_idx:
            self._cursor_idx = idx
            self._show_item_info(idx)

    # -- Mouse click --

    def on_click(self, event) -> None:
        if not self._chart_data:
            return
        try:
            plot = self.query_one("#graph-plot", PlotextPlot)
        except Exception:
            return
        region = plot.region
        if not region.contains(event.screen_x, event.screen_y):
            return

        if self._chart_type == "top_deps":
            plot_top = region.y + MARGIN_TOP
            plot_bottom = region.y + region.height - MARGIN_BOTTOM
            plot_height = plot_bottom - plot_top
            if plot_height <= 0:
                return
            rel_y = event.screen_y - plot_top
            idx = int(rel_y / plot_height * len(self._chart_data))
        else:
            plot_left = region.x + MARGIN_LEFT
            plot_right = region.x + region.width - MARGIN_RIGHT
            plot_width = plot_right - plot_left
            if plot_width <= 0:
                return
            rel_x = event.screen_x - plot_left
            idx = int(rel_x / plot_width * len(self._chart_data))

        idx = max(0, min(idx, len(self._chart_data) - 1))
        self._cursor_idx = idx
        self._render_chart()
        self._show_item_info(idx)

        if getattr(event, 'chain', 1) >= 2:
            self._open_detail_for(idx)

    # -- Open detail --

    def action_open_detail(self) -> None:
        if not self._chart_data or self._cursor_idx < 0:
            return
        self._open_detail_for(self._cursor_idx)

    def _open_detail_for(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._chart_data):
            return
        item = self._chart_data[idx]
        if self._chart_type == "top_deps":
            from .dep_detail import DepDetailScreen
            self.app.push_screen(DepDetailScreen(item["name"]))
        else:
            from .node_detail import NodeDetailScreen
            self.app.push_screen(NodeDetailScreen(item["id"]))

    # -- Keyboard cursor --

    def action_cursor_left(self) -> None:
        if not self._chart_data:
            return
        if self._cursor_idx <= 0:
            self._cursor_idx = 0
        else:
            self._cursor_idx -= 1
        self._render_chart()
        self._show_item_info(self._cursor_idx)

    def action_cursor_right(self) -> None:
        if not self._chart_data:
            return
        if self._cursor_idx < 0:
            self._cursor_idx = 0
        elif self._cursor_idx < len(self._chart_data) - 1:
            self._cursor_idx += 1
        self._render_chart()
        self._show_item_info(self._cursor_idx)

    def _update_status(self, msg: str | None = None) -> None:
        if msg is None:
            msg = self._status_base or "Graph"
        self.query_one("#graph-info", Static).update(f" {msg}")

    # -- Chart type switching --

    def action_chart_downloads(self) -> None:
        self._chart_type = "downloads"
        self._draw()

    def action_chart_deps(self) -> None:
        self._chart_type = "deps"
        self._draw()

    def action_chart_top_deps(self) -> None:
        self._chart_type = "top_deps"
        self._draw()

    def action_chart_cumulative(self) -> None:
        self._chart_type = "cumulative"
        self._draw()

    # -- Display controls --

    def action_increase(self) -> None:
        current = self._current_n()
        for step in STEPS:
            if step > current or step == 0:
                self._display_n[self._chart_type] = step
                break
        self._draw()

    def action_decrease(self) -> None:
        current = self._current_n()
        for step in reversed(STEPS):
            if current == 0:
                if step > 0:
                    self._display_n[self._chart_type] = step
                    break
            elif step < current and step > 0:
                self._display_n[self._chart_type] = step
                break
        self._draw()

    def action_toggle_log(self) -> None:
        self._log_scale = not self._log_scale
        self._draw()
