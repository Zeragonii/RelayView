from __future__ import annotations

import faulthandler
import os
import sys
from datetime import datetime
from pathlib import Path

_CRASH_FILE = None


def log_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        path = base / "RelayView" / "logs"
    else:
        path = Path.home() / ".local" / "state" / "RelayView" / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


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
