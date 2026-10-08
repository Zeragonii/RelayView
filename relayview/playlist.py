from __future__ import annotations

import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse

from .models import Stream
from .logging_config import get_logger

log = get_logger("playlist")

_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


def _fallback_name(url: str, index: int) -> str:
    parsed = urlparse(url)
    candidate = Path(parsed.path.rstrip("/")).name
    return candidate.replace("_", " ").replace("-", " ").strip().title() or f"Stream {index}"


def _parse_extinf(line: str) -> tuple[str, dict[str, str]]:
    body = line.split(":", 1)[1] if ":" in line else ""
    attrs = dict(_ATTR_RE.findall(body))
    # EXTINF names can themselves contain commas; only the first unquoted
    # comma separates attributes from the display name.
    quoted = False
    separator = None
    for index, character in enumerate(body):
        if character == '"':
            quoted = not quoted
        elif character == "," and not quoted:
            separator = index
            break
    display = body[separator + 1:].strip() if separator is not None else ""
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
    log.info("Loading playlist path=%s", path)
    try:
        streams = parse_m3u_text(path.read_text(encoding="utf-8-sig", errors="replace"))
        log.info("Playlist loaded path=%s streams=%s", path, len(streams))
        return streams
    except Exception:
        log.exception("Playlist load failed path=%s", path)
        raise


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
        display_name = str(stream.name).replace("\r", " ").replace("\n", " ")
        url = str(stream.url)
        if "\r" in url or "\n" in url:
            raise ValueError("Stream URL must not contain line breaks")
        lines.append(f"{prefix},{display_name}")
        lines.append(url.strip())
    return "\n".join(lines) + "\n"


def save_m3u(path: str | Path, streams: list[Stream]) -> None:
    path = Path(path)
    log.info("Saving playlist path=%s streams=%s", path, len(streams))
    path.parent.mkdir(parents=True, exist_ok=True)
    content = serialize_m3u(streams)

    # Atomic replacement avoids leaving a half-written playlist if saving fails.
    with NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False, dir=path.parent, suffix=".tmp") as temp:
        temp.write(content)
        temp_path = Path(temp.name)
    try:
        temp_path.replace(path)
    finally:
        # Do not leave credential-bearing temporary playlists on failed writes.
        temp_path.unlink(missing_ok=True)
    log.info("Playlist save complete path=%s", path)
