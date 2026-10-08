from __future__ import annotations

import faulthandler
import os
import platform
import sys
from datetime import datetime
from pathlib import Path

from .logging_config import current_log_path, get_log_level, log_dir

_CRASH_FILE = None


def enable_crash_logging() -> Path | None:
    """Enable Python/faulthandler logging for native faults where supported."""
    global _CRASH_FILE
    try:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = log_dir() / f"crash-{stamp}.log"
        _CRASH_FILE = open(path, "a", encoding="utf-8", buffering=1)
        _CRASH_FILE.write(f"RelayView process start pid={os.getpid()} python={sys.version}\n")
        faulthandler.enable(_CRASH_FILE, all_threads=True)
        return path
    except Exception:
        return None


def diagnostic_summary(*, version: str, playlist_name: str, view_mode: str, grid_rows: int, grid_columns: int, active_grid_feeds: int, player_details: list[dict] | None = None) -> str:
    return "\n".join([
        f"RelayView version: {version}",
        f"Log level: {get_log_level()}",
        f"Log file: {current_log_path()}",
        f"Python: {platform.python_version()}",
        f"Platform: {platform.platform()}",
        f"Process architecture: {platform.machine()}",
        f"View mode: {view_mode}",
        f"Grid: {grid_rows}x{grid_columns} ({active_grid_feeds} assigned)",
        f"Playlist: {playlist_name or '<none>'}",
    ] + [
        f"Player {index}: " + ", ".join(f"{key}={value}" for key, value in item.items())
        for index, item in enumerate(player_details or [], start=1)
    ])
