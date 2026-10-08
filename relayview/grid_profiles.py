"""Validation and resolution of saved camera layouts (independent of Qt)."""
from __future__ import annotations

MAX_TILES = 64


def validate_profile(profile: object) -> tuple[int, int, list[str]]:
    if not isinstance(profile, dict):
        raise ValueError("Layout is not an object")
    try:
        rows, columns = int(profile["rows"]), int(profile["columns"])
        urls = profile["urls"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Missing or invalid layout fields") from exc
    if not (1 <= rows <= 32 and 1 <= columns <= 32 and rows * columns <= MAX_TILES):
        raise ValueError("Grid dimensions outside supported range")
    if not isinstance(urls, list) or len(urls) > rows * columns or any(not isinstance(u, str) for u in urls):
        raise ValueError("Invalid camera URLs")
    return rows, columns, urls


def resolve_assignments(urls: list[str], rows: int, columns: int, streams: list) -> list:
    by_url = {stream.url: stream for stream in streams}
    result = [by_url.get(url) if url else None for url in urls]
    return result + [None] * (rows * columns - len(result))
