from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from .models import Stream

_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


def _fallback_name(url: str, index: int) -> str:
    parsed = urlparse(url)
    candidate = Path(parsed.path.rstrip("/")).name
    return candidate.replace("_", " ").replace("-", " ").strip().title() or f"Stream {index}"


def _parse_extinf(line: str) -> tuple[str, str]:
    body = line.split(":", 1)[1] if ":" in line else ""
    attrs = dict(_ATTR_RE.findall(body))
    display = body.rsplit(",", 1)[1].strip() if "," in body else ""
    name = display or attrs.get("tvg-name", "")
    return name, attrs.get("group-title", "")


def parse_m3u_text(text: str) -> list[Stream]:
    streams: list[Stream] = []
    pending_name = ""
    pending_group = ""

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            pending_name, pending_group = _parse_extinf(line)
            continue
        if line.startswith("#"):
            continue

        name = pending_name or _fallback_name(line, len(streams) + 1)
        streams.append(Stream(name=name, url=line, group=pending_group))
        pending_name = ""
        pending_group = ""

    return streams


def load_m3u(path: str | Path) -> list[Stream]:
    path = Path(path)
    # utf-8-sig tolerates BOMs produced by some playlist generators.
    return parse_m3u_text(path.read_text(encoding="utf-8-sig", errors="replace"))
