"""Shared application state — loaded data, filters, session info.

The AppState instance lives on the App and is accessible from all screens.
Filters persist across screen navigation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Filters:
    """Active filters that persist across screens."""

    top: int | tuple[int, int] | None = None
    include_stats: list[str] = field(default_factory=list)
    exclude_stats: list[str] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return bool(self.top or self.include_stats or self.exclude_stats)

    def clear(self) -> None:
        self.top = None
        self.include_stats.clear()
        self.exclude_stats.clear()

    def summary(self) -> str:
        """One-line summary of active filters for the status bar."""
        parts = []
        if self.top is not None:
            if isinstance(self.top, tuple):
                parts.append(f"rank {self.top[0]}-{self.top[1]}")
            elif self.top > 0:
                parts.append(f"top {self.top}")
            else:
                parts.append(f"bottom {abs(self.top)}")
        for s in self.include_stats:
            parts.append(f"+{s}")
        for s in self.exclude_stats:
            parts.append(f"-{s}")
        return " | ".join(parts) if parts else "no filters"


@dataclass
class UpdateState:
    """Tracks a background update operation."""

    running: bool = False
    kind: str = ""  # "registry" or "reqs"
    log_lines: list[str] = field(default_factory=list)
    progress: int = 0
    total: int = 100
    status: str = ""

    def reset(self, kind: str, total: int = 100) -> None:
        self.running = True
        self.kind = kind
        self.log_lines.clear()
        self.progress = 0
        self.total = total
        self.status = ""

    def log(self, msg: str) -> None:
        self.log_lines.append(msg)

    def finish(self, status: str) -> None:
        self.running = False
        self.status = status


@dataclass
class AppState:
    """Central state shared across all screens."""

    nodes_dict: dict = field(default_factory=dict)
    original_deps_backup: dict = field(default_factory=dict)
    filters: Filters = field(default_factory=Filters)
    cache_status: str = "loading..."
    update: UpdateState = field(default_factory=UpdateState)

    def filtered_nodes(self) -> dict:
        """Return nodes_dict with current filters applied."""
        from core.modifiers import apply_top_filter

        working = self.nodes_dict

        # Top filter
        if self.filters.top is not None:
            working, _ = apply_top_filter(working, self.filters.top)

        # Include stats
        for stat_name in self.filters.include_stats:
            working = {
                nid: nd for nid, nd in working.items()
                if nd.get('_stats', {}).get(stat_name)
            }

        # Exclude stats
        for stat_name in self.filters.exclude_stats:
            working = {
                nid: nd for nid, nd in working.items()
                if not nd.get('_stats', {}).get(stat_name)
            }

        return working
