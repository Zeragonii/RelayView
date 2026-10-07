from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def configure_vlc_environment() -> None:
    """Prefer a VLC runtime bundled beside the executable when present."""
    root = _app_root()
    bundled = root / "vlc"
    if not bundled.exists():
        return

    os.environ["PATH"] = str(bundled) + os.pathsep + os.environ.get("PATH", "")
    plugins = bundled / "plugins"
    if plugins.exists():
        os.environ["VLC_PLUGIN_PATH"] = str(plugins)


class VLCBackend:
    def __init__(self, status_callback: Callable[[str], None] | None = None) -> None:
        configure_vlc_environment()
        try:
            import vlc  # Imported only after the bundled runtime path is configured.
        except Exception as exc:  # pragma: no cover - environment specific
            raise RuntimeError(
                "VLC could not be loaded. Install VLC 3.x, or use the packaged RelayView build."
            ) from exc

        self.vlc = vlc
        self._status_callback = status_callback or (lambda _status: None)
        self.instance = vlc.Instance(
            "--no-video-title-show",
            "--quiet",
            "--network-caching=250",
            "--clock-jitter=0",
        )
        self.player = self.instance.media_player_new()
        self._events = self.player.event_manager()
        self._events.event_attach(vlc.EventType.MediaPlayerOpening, self._event("Connecting…"))
        self._events.event_attach(vlc.EventType.MediaPlayerPlaying, self._event("Live"))
        self._events.event_attach(vlc.EventType.MediaPlayerPaused, self._event("Paused"))
        self._events.event_attach(vlc.EventType.MediaPlayerEncounteredError, self._event("Stream error"))
        self._events.event_attach(vlc.EventType.MediaPlayerEndReached, self._event("Stream ended"))

    def _event(self, text: str):
        def callback(_event) -> None:
            self._status_callback(text)
        return callback

    def attach_video(self, widget_id: int) -> None:
        if sys.platform.startswith("win"):
            self.player.set_hwnd(widget_id)
        elif sys.platform == "darwin":
            self.player.set_nsobject(widget_id)
        else:
            self.player.set_xwindow(widget_id)

    def play(self, url: str) -> None:
        media = self.instance.media_new(url)
        self.player.set_media(media)
        self.player.play()

    def toggle_pause(self) -> bool:
        if self.player.is_playing():
            self.player.pause()
            return True
        self.player.play()
        return False

    def stop(self) -> None:
        self.player.stop()

    def set_muted(self, muted: bool) -> None:
        self.player.audio_set_mute(muted)

    def is_muted(self) -> bool:
        return bool(self.player.audio_get_mute())
