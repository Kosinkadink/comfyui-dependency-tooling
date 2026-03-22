"""Main Textual App for Dependency Analyzer TUI."""

from __future__ import annotations

from textual import work
from textual.app import App
from textual.binding import Binding

from .state import AppState
from .screens.node_list import NodeListScreen
from .screens.dep_search import DepSearchScreen
from .screens.dashboard import DashboardScreen
from .screens.graph import GraphScreen


class DepAnalyzerApp(App):
    """ComfyUI Dependency Analyzer — interactive terminal UI."""

    TITLE = "ComfyUI Dep Analyzer"
    CSS_PATH = "styles/app.tcss"

    BINDINGS = [
        Binding("n", "switch_nodes", "Nodes", show=True),
        Binding("d", "switch_deps", "Deps", show=True),
        Binding("s", "switch_summary", "Summary", show=True),
        Binding("g", "switch_graph", "Graph", show=True),
        Binding("u", "update", "Update", show=True),
        Binding("r", "update_reqs", "Update Reqs", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    MODES = {
        "nodes": NodeListScreen,
        "deps": DepSearchScreen,
        "summary": DashboardScreen,
        "graph": GraphScreen,
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.state = AppState()

    def on_mount(self) -> None:
        """Show UI immediately, load data in background."""
        self.switch_mode("nodes")
        self._load_data_async()

    @work(thread=True)
    def _load_data_async(self) -> None:
        """Load data in background thread so the UI renders immediately."""
        from core.data import load_nodes_to_dict, store_node_ranks, initialize_session
        from core.cache import cache_status_str, is_stale

        def set_loading_status(msg: str) -> None:
            self.state.cache_status = msg
            self.app.call_from_thread(self._refresh_current_screen)

        set_loading_status("loading nodes...")
        nodes_dict = load_nodes_to_dict()

        if not nodes_dict:
            self.app.call_from_thread(self._set_state_no_data)
            return

        set_loading_status("ranking nodes...")
        store_node_ranks(nodes_dict)

        set_loading_status("loading requirements & stats...")
        session = initialize_session(nodes_dict)

        status = cache_status_str()
        stale = is_stale()

        def apply():
            self.state.nodes_dict = nodes_dict
            self.state.original_deps_backup = session['original_deps_backup']
            self.state.cache_status = status
            self._refresh_current_screen()
            if stale:
                self.notify("Data is stale — press [bold]u[/bold] to update", severity="warning", timeout=5)

        self.app.call_from_thread(apply)

    def _set_state_no_data(self) -> None:
        self.state.cache_status = "no data — press u to update"
        self._refresh_current_screen()

    def _load_data(self) -> None:
        """Load nodes from cache and initialize session (synchronous)."""
        from core.data import load_nodes_to_dict, store_node_ranks, initialize_session
        from core.cache import cache_status_str

        self.state.nodes_dict = load_nodes_to_dict()

        if not self.state.nodes_dict:
            self.state.cache_status = "no data — press u to update"
            return

        store_node_ranks(self.state.nodes_dict)
        session = initialize_session(self.state.nodes_dict)
        self.state.original_deps_backup = session['original_deps_backup']
        self.state.cache_status = cache_status_str()

    def _refresh_current_screen(self) -> None:
        """Tell the current screen to refresh its data."""
        screen = self.screen
        for method in ('_refresh_table', '_refresh_content', '_update_status'):
            if hasattr(screen, method):
                getattr(screen, method)()

    # -- Update notification to visible UpdateScreen --

    def _get_update_screen(self):
        """Return the UpdateScreen if it's currently visible on the stack."""
        from .screens.update import UpdateScreen
        for screen in self.screen_stack:
            if isinstance(screen, UpdateScreen):
                return screen
        return None

    def _update_log(self, msg: str) -> None:
        """Log to UpdateState and notify visible UpdateScreen."""
        self.state.update.log(msg)
        us = self._get_update_screen()
        if us and us.is_current:
            us.append_log(msg)

    def _update_progress(self, progress: int, total: int | None = None) -> None:
        """Update progress in state and notify visible UpdateScreen."""
        self.state.update.progress = progress
        if total is not None:
            self.state.update.total = total
        us = self._get_update_screen()
        if us and us.is_current:
            us.set_progress(progress, self.state.update.total)

    def _update_status(self, msg: str) -> None:
        """Update status in state and notify visible UpdateScreen."""
        self.state.update.status = msg
        us = self._get_update_screen()
        if us and us.is_current:
            us.set_status(msg)

    # -- Update workers (owned by App, run in background) --

    @work(thread=True)
    def _run_registry_update(self) -> None:
        """Fetch fresh node data from registry."""
        from core.registry import get_registry_nodes, save_nodes_json, fetch_and_save_extension_node_map

        def log(msg: str) -> None:
            self.app.call_from_thread(self._update_log, msg)

        def on_page_progress(completed: int, total: int) -> None:
            pct = completed * 80 // total if total else 80
            self.app.call_from_thread(self._update_progress, pct, 100)
            self.app.call_from_thread(self._update_status, f"Fetching pages: {completed}/{total}")

        log("Fetching nodes from registry...")
        try:
            registry_data = get_registry_nodes(
                print_time=False,
                log_callback=log,
                progress_callback=on_page_progress,
            )
            node_count = len(registry_data.get('nodes', []))
            log(f"Fetched {node_count} nodes")

            log("Saving to cache...")
            save_nodes_json(registry_data, log_callback=log)

            self.app.call_from_thread(self._update_progress, 90)
            log("Fetching extension-node-map.json...")
            fetch_and_save_extension_node_map(log_callback=log)

            log("Done! Reloading data...")

            # Reload data on this worker thread (heavy I/O), then apply on main thread
            from core.data import load_nodes_to_dict, store_node_ranks, initialize_session
            from core.cache import cache_status_str

            nodes_dict = load_nodes_to_dict()
            if nodes_dict:
                store_node_ranks(nodes_dict)
                session = initialize_session(nodes_dict)
                cache_status = cache_status_str()

                def finish():
                    self.state.nodes_dict = nodes_dict
                    self.state.original_deps_backup = session['original_deps_backup']
                    self.state.cache_status = cache_status
                    self._refresh_current_screen()
                    self._update_progress(100)
                    status = f"Update complete — {node_count} nodes"
                    self.state.update.finish(status)
                    self._update_status(status)

                self.app.call_from_thread(finish)
            else:
                def finish_no_data():
                    self._update_progress(100)
                    status = f"Update complete — {node_count} nodes (reload failed)"
                    self.state.update.finish(status)
                    self._update_status(status)

                self.app.call_from_thread(finish_no_data)
        except Exception as e:
            log(f"Error: {e}")

            def fail():
                status = f"Update failed: {e}"
                self.state.update.finish(status)
                self._update_status(status)

            self.app.call_from_thread(fail)

    @work(thread=True)
    def _run_reqs_update(self) -> None:
        """Fetch requirements.txt for nodes using the concurrent updater."""
        from core.modifiers import apply_top_filter
        from core.requirements import update_node_requirements

        state = self.state
        nodes = state.filtered_nodes()
        node_ids = list(nodes.keys())
        total = len(node_ids)

        self.app.call_from_thread(self._update_log, f"Updating requirements for {total} nodes...")
        self.app.call_from_thread(self._update_progress, 0, total)

        def on_progress(completed, total, node_id, ok):
            status_char = "✓" if ok else "✗"
            self.app.call_from_thread(self._update_log, f"  {status_char} {node_id}")
            self.app.call_from_thread(self._update_progress, completed)
            self.app.call_from_thread(self._update_status, f"[{completed}/{total} nodes] {node_id}")

        stats = update_node_requirements(
            nodes_dict=state.nodes_dict,
            node_ids=node_ids,
            original_deps_backup=state.original_deps_backup,
            progress_callback=on_progress,
        )

        def finish():
            msg = f"Done! {total} nodes checked — {stats['success']} succeeded, {stats['failed']} failed, {stats['unsupported']} unsupported"
            status = f"Requirements update: {total} nodes — {stats['success']} ok, {stats['failed']} failed, {stats['unsupported']} unsupported"
            self._update_log(msg)
            self.state.update.finish(status)
            self._update_status(status)
            try:
                self._refresh_current_screen()
            except Exception:
                pass

        self.app.call_from_thread(finish)

    # -- Actions --

    def action_switch_nodes(self) -> None:
        if self.current_mode != "nodes":
            self.switch_mode("nodes")

    def action_switch_deps(self) -> None:
        if self.current_mode != "deps":
            self.switch_mode("deps")

    def action_switch_summary(self) -> None:
        if self.current_mode != "summary":
            self.switch_mode("summary")

    def action_switch_graph(self) -> None:
        if self.current_mode != "graph":
            self.switch_mode("graph")

    def action_update(self) -> None:
        from .screens.update import UpdateScreen
        if self.state.update.running:
            # Already running — just show the screen if not visible
            if not self._get_update_screen():
                self.push_screen(UpdateScreen())
            return
        self.state.update.reset("registry")
        self.push_screen(UpdateScreen())
        self._run_registry_update()

    def action_update_reqs(self) -> None:
        from .screens.update import UpdateScreen
        if self.state.update.running:
            if not self._get_update_screen():
                self.push_screen(UpdateScreen())
            return
        self.state.update.reset("reqs")
        self.push_screen(UpdateScreen())
        self._run_reqs_update()
