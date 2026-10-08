from __future__ import annotations

import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

_LOGGER_NAME = "relayview"
_current_log: Path | None = None
_configured = False

LEVELS = {
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


def log_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        path = base / "RelayView" / "logs"
    else:
        path = Path.home() / ".local" / "state" / "RelayView" / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup_logging(level: str = "ERROR") -> Path:
    global _configured, _current_log
    root = logging.getLogger(_LOGGER_NAME)
    root.propagate = False
    numeric = LEVELS.get(str(level).upper(), logging.ERROR)
    root.setLevel(numeric)

    if not _configured:
        _current_log = log_dir() / "relayview.log"
        handler = RotatingFileHandler(
            _current_log,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s.%(msecs)03d | %(levelname)-7s | %(name)s | %(threadName)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        root.addHandler(handler)
        _configured = True
    for handler in root.handlers:
        handler.setLevel(numeric)
    root.info("Logging initialised at %s", logging.getLevelName(numeric))
    return _current_log


def set_log_level(level: str) -> str:
    name = str(level).upper()
    if name not in LEVELS:
        name = "ERROR"
    setup_logging(name)
    logging.getLogger(_LOGGER_NAME).setLevel(LEVELS[name])
    for handler in logging.getLogger(_LOGGER_NAME).handlers:
        handler.setLevel(LEVELS[name])
    logging.getLogger(f"{_LOGGER_NAME}.logging").warning("Log level changed to %s", name)
    return name


def get_log_level() -> str:
    level = logging.getLogger(_LOGGER_NAME).level
    for name, numeric in LEVELS.items():
        if numeric == level:
            return name
    return logging.getLevelName(level)


def current_log_path() -> Path:
    return _current_log or setup_logging("ERROR")


def get_logger(component: str) -> logging.Logger:
    return logging.getLogger(f"{_LOGGER_NAME}.{component}")


def redact_url(value: str) -> str:
    """Conservatively remove potentially secret parts of a media URL for logging.

    Retain host and port, but never log URL paths, fragments or query values:
    vendor-specific stream paths and query keys frequently contain credentials.
    """
    try:
        parts = urlsplit(value)
        if not parts.scheme or not parts.hostname:
            return "<redacted-url>"
        host = parts.hostname
        if ":" in host:
            host = f"[{host}]"
        if parts.port:
            host += f":{parts.port}"
        query = urlencode([(key, "<redacted>") for key, _ in parse_qsl(parts.query, keep_blank_values=True)])
        return urlunsplit((parts.scheme, host, "/<redacted>" if parts.path else "", query, ""))
    except Exception:
        return "<redacted-url>"


def install_exception_hook() -> None:
    previous = sys.excepthook

    def hook(exc_type, exc_value, exc_tb):
        get_logger("crash").critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
        previous(exc_type, exc_value, exc_tb)

    sys.excepthook = hook
