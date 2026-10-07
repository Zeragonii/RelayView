from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable

from .logging_config import get_logger, redact_url

log = get_logger("vlc")


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def configure_vlc_environment() -> None:
    root = _app_root()
    bundled = root / "vlc"
    log.debug("Configuring VLC environment app_root=%s bundled_exists=%s", root, bundled.exists())
    if not bundled.exists():
        return
    os.environ["PATH"] = str(bundled) + os.pathsep + os.environ.get("PATH", "")
    plugins = bundled / "plugins"
    if plugins.exists():
        os.environ["VLC_PLUGIN_PATH"] = str(plugins)
        log.debug("VLC_PLUGIN_PATH=%s", plugins)


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
        log.debug("Created VLCPlayer id=%s native=%r", id(self), self.player)

    def _event(self, text: str):
        def callback(_event) -> None:
            log.debug("VLC event player=%s status=%s", id(self), text)
            self._status_callback(text)
        return callback

    def attach_video(self, widget_id: int) -> None:
        widget_id = int(widget_id)
        if self._attached_handle == widget_id:
            log.debug("Skipping duplicate video attach player=%s hwnd=%s", id(self), widget_id)
            return
        log.debug("Attaching video player=%s old_hwnd=%s new_hwnd=%s platform=%s", id(self), self._attached_handle, widget_id, sys.platform)
        if sys.platform.startswith("win"):
            self.player.set_hwnd(widget_id)
        elif sys.platform == "darwin":
            self.player.set_nsobject(widget_id)
        else:
            self.player.set_xwindow(widget_id)
        self._attached_handle = widget_id

    def play(self, url: str) -> None:
        log.info("Play player=%s url=%s", id(self), redact_url(url))
        media = self.instance.media_new(url)
        self.player.set_media(media)
        result = self.player.play()
        log.debug("player.play returned=%s player=%s", result, id(self))

    def toggle_pause(self) -> bool:
        playing = bool(self.player.is_playing())
        log.debug("Toggle pause player=%s is_playing=%s", id(self), playing)
        if playing:
            self.player.pause()
            return True
        self.player.play()
        return False

    def set_paused(self, paused: bool) -> None:
        log.debug("Set paused player=%s paused=%s", id(self), paused)
        self.player.set_pause(1 if paused else 0)

    def stop(self) -> None:
        log.debug("Stop player=%s", id(self))
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
    def __init__(self, status_callback: Callable[[str], None] | None = None) -> None:
        configure_vlc_environment()
        try:
            import vlc
        except Exception as exc:
            log.exception("VLC import failed")
            raise RuntimeError("VLC could not be loaded. Install VLC 3.x, or use the packaged RelayView build.") from exc
        self.vlc = vlc
        log.info("Creating shared libVLC instance")
        self.instance = vlc.Instance("--no-video-title-show", "--quiet", "--network-caching=250", "--clock-jitter=0")
        self.primary = VLCPlayer(self.instance, self.vlc, status_callback)
        self._extra_players: list[VLCPlayer] = []

    @property
    def player(self):
        return self.primary.player

    def create_player(self, status_callback: Callable[[str], None] | None = None) -> VLCPlayer:
        player = VLCPlayer(self.instance, self.vlc, status_callback)
        self._extra_players.append(player)
        log.debug("Registered extra player=%s count=%s", id(player), len(self._extra_players))
        return player

    def release_player(self, player: VLCPlayer) -> None:
        log.debug("Releasing extra player=%s attached_hwnd=%s", id(player), player._attached_handle)
        try:
            player.stop()
            player._attached_handle = None
            try: player.player.set_media(None)
            except Exception: log.exception("set_media(None) failed player=%s", id(player))
            try: player.player.release()
            except Exception: log.exception("native release failed player=%s", id(player))
        finally:
            if player in self._extra_players:
                self._extra_players.remove(player)
            log.debug("Extra player released=%s remaining=%s", id(player), len(self._extra_players))

    def attach_video(self, widget_id: int) -> None: self.primary.attach_video(widget_id)
    def play(self, url: str) -> None: self.primary.play(url)
    def toggle_pause(self) -> bool: return self.primary.toggle_pause()
    def stop_primary(self) -> None: self.primary.stop()
    def stop(self) -> None:
        log.info("Stopping VLC backend extra_players=%s", len(self._extra_players))
        self.primary.stop()
        for player in list(self._extra_players): player.stop()
    def set_muted(self, muted: bool) -> None:
        self.primary.set_muted(muted)
        for player in self._extra_players: player.set_muted(muted)
    def set_volume(self, volume: int) -> None:
        self.primary.set_volume(volume)
        for player in self._extra_players: player.set_volume(volume)
    def get_volume(self) -> int: return self.primary.get_volume()
    def is_muted(self) -> bool: return self.primary.is_muted()
