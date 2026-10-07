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


class VLCPlayer:
    def __init__(self, instance, vlc_module, status_callback: Callable[[str], None] | None = None) -> None:
        self.instance = instance
        self.vlc = vlc_module
        self._status_callback = status_callback or (lambda _status: None)
        self.player = self.instance.media_player_new()
        self._events = self.player.event_manager()
        self._attached_handle: int | None = None
        self._events.event_attach(self.vlc.EventType.MediaPlayerOpening, self._event("Connecting…"))
        self._events.event_attach(self.vlc.EventType.MediaPlayerPlaying, self._event("Live"))
        self._events.event_attach(self.vlc.EventType.MediaPlayerPaused, self._event("Paused"))
        self._events.event_attach(self.vlc.EventType.MediaPlayerEncounteredError, self._event("Stream error"))
        self._events.event_attach(self.vlc.EventType.MediaPlayerEndReached, self._event("Stream ended"))

    def _event(self, text: str):
        def callback(_event) -> None:
            self._status_callback(text)
        return callback

    def attach_video(self, widget_id: int) -> None:
        widget_id = int(widget_id)
        if self._attached_handle == widget_id:
            return
        # libVLC expects the target native window to remain valid for the life
        # of playback. Do not repeatedly rebind a player to the same HWND.
        if sys.platform.startswith("win"):
            self.player.set_hwnd(widget_id)
        elif sys.platform == "darwin":
            self.player.set_nsobject(widget_id)
        else:
            self.player.set_xwindow(widget_id)
        self._attached_handle = widget_id

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

    def set_paused(self, paused: bool) -> None:
        if paused:
            self.player.set_pause(1)
        else:
            self.player.set_pause(0)

    def stop(self) -> None:
        self.player.stop()

    def set_muted(self, muted: bool) -> None:
        self.player.audio_set_mute(muted)

    def set_volume(self, volume: int) -> None:
        self.player.audio_set_volume(max(0, min(100, int(volume))))

    def get_volume(self) -> int:
        return int(self.player.audio_get_volume())

    def is_muted(self) -> bool:
        return bool(self.player.audio_get_mute())


class VLCBackend:
    """Own one shared libVLC instance and as many players as RelayView needs."""

    def __init__(self, status_callback: Callable[[str], None] | None = None) -> None:
        configure_vlc_environment()
        try:
            import vlc  # Imported only after the bundled runtime path is configured.
        except Exception as exc:  # pragma: no cover - environment specific
            raise RuntimeError(
                "VLC could not be loaded. Install VLC 3.x, or use the packaged RelayView build."
            ) from exc

        self.vlc = vlc
        self.instance = vlc.Instance(
            "--no-video-title-show",
            "--quiet",
            "--network-caching=250",
            "--clock-jitter=0",
        )
        self.primary = VLCPlayer(self.instance, self.vlc, status_callback)
        self._extra_players: list[VLCPlayer] = []

    @property
    def player(self):
        """Compatibility escape hatch for existing code/tests."""
        return self.primary.player

    def create_player(self, status_callback: Callable[[str], None] | None = None) -> VLCPlayer:
        player = VLCPlayer(self.instance, self.vlc, status_callback)
        self._extra_players.append(player)
        return player

    def release_player(self, player: VLCPlayer) -> None:
        try:
            player.stop()
            # Explicitly release the native media-player object before its Qt HWND
            # is destroyed. Relying on Python GC here can leave libVLC rendering
            # into a stale window during grid reconfiguration.
            player._attached_handle = None
            try:
                player.player.set_media(None)
            except Exception:
                pass
            try:
                player.player.release()
            except Exception:
                pass
        finally:
            if player in self._extra_players:
                self._extra_players.remove(player)

    def attach_video(self, widget_id: int) -> None:
        self.primary.attach_video(widget_id)

    def play(self, url: str) -> None:
        self.primary.play(url)

    def toggle_pause(self) -> bool:
        return self.primary.toggle_pause()

    def stop_primary(self) -> None:
        self.primary.stop()

    def stop(self) -> None:
        self.primary.stop()
        for player in list(self._extra_players):
            player.stop()

    def set_muted(self, muted: bool) -> None:
        self.primary.set_muted(muted)
        for player in self._extra_players:
            player.set_muted(muted)

    def set_volume(self, volume: int) -> None:
        self.primary.set_volume(volume)
        for player in self._extra_players:
            player.set_volume(volume)

    def get_volume(self) -> int:
        return self.primary.get_volume()

    def is_muted(self) -> bool:
        return self.primary.is_muted()
