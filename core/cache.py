"""Data caching for instant startup.

Caches nodes.json and extension-node-map.json with timestamps so the app
starts instantly from disk. Warns when data is stale (>7 days old).
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
NODES_CACHE = CACHE_DIR / "nodes.json"
EXT_MAP_CACHE = CACHE_DIR / "extension-node-map.json"
META_FILE = CACHE_DIR / "meta.json"

STALE_DAYS = 7


def _ensure_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _load_meta():
    try:
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_meta(meta):
    _ensure_dir()
    META_FILE.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def cache_age_days():
    """Return cache age in days, or None if no cache exists."""
    meta = _load_meta()
    ts = meta.get("updated_at")
    if not ts:
        return None
    try:
        updated = datetime.fromisoformat(ts)
        now = datetime.now(timezone.utc)
        return (now - updated).days
    except (ValueError, TypeError):
        return None


def is_stale():
    """Return True if cache is older than STALE_DAYS or doesn't exist."""
    age = cache_age_days()
    return age is None or age >= STALE_DAYS


def cache_status_str():
    """Return a human-readable cache status string."""
    age = cache_age_days()
    if age is None:
        return "no cache"
    if age == 0:
        return "updated today"
    if age == 1:
        return "1 day old"
    if age >= STALE_DAYS:
        return f"{age} days old (stale — run /update)"
    return f"{age} days old"


def save_nodes_cache(registry_data):
    """
    Cache registry data (nodes.json) to .cache/ directory.

    Args:
        registry_data: dict with 'nodes' key

    Returns:
        True if successful
    """
    _ensure_dir()
    try:
        NODES_CACHE.write_text(
            json.dumps(registry_data, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        # Update timestamp
        meta = _load_meta()
        meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        meta["node_count"] = len(registry_data.get("nodes", []))
        _save_meta(meta)
        return True
    except OSError as e:
        print(f"Warning: Could not save nodes cache: {e}")
        return False


def load_nodes_cache():
    """
    Load cached nodes data.

    Returns:
        dict with 'nodes' key, or None if no cache
    """
    if not NODES_CACHE.exists():
        return None
    try:
        return json.loads(NODES_CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_ext_map_cache(ext_map_data):
    """Cache extension-node-map.json."""
    _ensure_dir()
    try:
        EXT_MAP_CACHE.write_text(
            json.dumps(ext_map_data, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return True
    except OSError as e:
        print(f"Warning: Could not save extension map cache: {e}")
        return False


def load_ext_map_cache():
    """Load cached extension-node-map.json."""
    if not EXT_MAP_CACHE.exists():
        return None
    try:
        return json.loads(EXT_MAP_CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def copy_to_cache(source_path, cache_file):
    """Copy a file into the cache directory."""
    _ensure_dir()
    try:
        shutil.copy2(source_path, cache_file)
        return True
    except OSError:
        return False
