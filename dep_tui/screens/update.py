"""Update screen — passive view of background update progress."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Static, ProgressBar


class UpdateScreen(ModalScreen):
    """Modal view for monitoring a background update operation."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close", show=True, priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield Static("[bold]Updating...[/bold]", id="update-title")
        yield ProgressBar(id="update-progress", total=100, show_eta=False)
        yield VerticalScroll(id="update-log")
        yield Static("", id="update-status", classes="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Replay current update state so reopening shows full history."""
        us = self.app.state.update
        bar = self.query_one("#update-progress", ProgressBar)
        bar.update(total=us.total, progress=us.progress)

        container = self.query_one("#update-log", VerticalScroll)
        for line in us.log_lines:
            container.mount(Static(line))
        container.scroll_end(animate=False)

        if us.status:
            self.query_one("#update-status", Static).update(f" {us.status}")

        kind = us.kind or "registry"
        label = "Updating Requirements..." if kind == "reqs" else "Updating Registry..."
        if not us.running:
            label = "Update Complete" if us.status and "failed" not in us.status.lower() else "Update Finished"
        self.query_one("#update-title", Static).update(f"[bold]{label}[/bold]")

    # -- Called by App to push live updates --

    def append_log(self, msg: str) -> None:
        try:
            container = self.query_one("#update-log", VerticalScroll)
            container.mount(Static(msg))
            container.scroll_end(animate=False)
        except Exception:
            pass

    def set_progress(self, value: int, total: int) -> None:
        try:
            bar = self.query_one("#update-progress", ProgressBar)
            bar.update(total=total, progress=value)
        except Exception:
            pass

    def set_status(self, msg: str) -> None:
        try:
            self.query_one("#update-status", Static).update(f" {msg}")
        except Exception:
            pass

    def action_dismiss_modal(self) -> None:
        self.app.pop_screen()
