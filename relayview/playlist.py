from __future__ import annotations

import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse

from .models import Stream

_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


def _fallback_name(url: str, index: int) -> str:
    parsed = urlparse(url)
    candidate = Path(parsed.path.rstrip("/")).name
    return candidate.replace("_", " ").replace("-", " ").strip().title() or f"Stream {index}"


def _parse_extinf(line: str) -> tuple[str, dict[str, str]]:
    body = line.split(":", 1)[1] if ":" in line else ""
    attrs = dict(_ATTR_RE.findall(body))
    display = body.rsplit(",", 1)[1].strip() if "," in body else ""
    name = display or attrs.get("tvg-name", "")
    return name, attrs


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on", "favorite", "favourite"}


def parse_m3u_text(text: str) -> list[Stream]:
    streams: list[Stream] = []
    pending_name = ""
    pending_attrs: dict[str, str] = {}

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            pending_name, pending_attrs = _parse_extinf(line)
            continue
        if line.startswith("#"):
            continue

        attrs = dict(pending_attrs)
        name = pending_name or _fallback_name(line, len(streams) + 1)
        group = attrs.get("group-title", "")
        favorite = _truthy(attrs.get("relayview-favorite", ""))
        notes = attrs.get("relayview-notes", "")
        streams.append(
            Stream(
                name=name,
                url=line,
                group=group,
                favorite=favorite,
                notes=notes,
                attrs=attrs,
            )
        )
        pending_name = ""
        pending_attrs = {}

    return streams


def load_m3u(path: str | Path) -> list[Stream]:
    path = Path(path)
    # utf-8-sig tolerates BOMs produced by some playlist generators.
    return parse_m3u_text(path.read_text(encoding="utf-8-sig", errors="replace"))


def _escape_attr(value: str) -> str:
    # M3U EXTINF attributes have no universal escaping standard. Replacing quotes
    # keeps generated files valid for VLC and most IPTV-style parsers.
    return value.replace('"', "'").replace("\r", " ").replace("\n", " ")


def serialize_m3u(streams: list[Stream]) -> str:
    lines = ["#EXTM3U"]
    for stream in streams:
        attrs = dict(stream.attrs)
        if stream.group:
            attrs["group-title"] = stream.group
        else:
            attrs.pop("group-title", None)

        # Keep tvg-name aligned when the source playlist already used it.
        if "tvg-name" in attrs:
            attrs["tvg-name"] = stream.name

        if stream.favorite:
            attrs["relayview-favorite"] = "1"
        else:
            attrs.pop("relayview-favorite", None)

        if stream.notes:
            attrs["relayview-notes"] = stream.notes
        else:
            attrs.pop("relayview-notes", None)

        attr_text = " ".join(f'{key}="{_escape_attr(value)}"' for key, value in attrs.items())
        prefix = f"#EXTINF:-1 {attr_text}" if attr_text else "#EXTINF:-1"
        lines.append(f"{prefix},{stream.name}")
        lines.append(stream.url)
    return "\n".join(lines) + "\n"


def save_m3u(path: str | Path, streams: list[Stream]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = serialize_m3u(streams)

    # Atomic replacement avoids leaving a half-written playlist if saving fails.
    with NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False, dir=path.parent, suffix=".tmp") as temp:
        temp.write(content)
        temp_path = Path(temp.name)
    temp_path.replace(path)
