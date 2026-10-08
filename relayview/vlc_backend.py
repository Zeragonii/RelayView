from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from collections import deque
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


def _worker_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--player-worker"]
    return [sys.executable, "-m", "relayview.player_worker"]


class VLCPlayer:
    """Proxy for a libVLC player hosted in an isolated child process.

    The GUI process never loads libVLC. Destroying/switching a stream terminates the
    worker process instead of calling libvlc_media_player_stop(), which is known to
    be unstable with some RTSP streams on VLC 3.x.
    """

    def __init__(self, status_callback: Callable[[str], None] | None = None) -> None:
        self._status_callback = status_callback or (lambda _status: None)
        self._attached_handle: int | None = None
        self._process: subprocess.Popen[str] | None = None
        self._volume = 100
        self._muted = False
        self._paused = False
        self._current_url: str | None = None
        self._lock = threading.Lock()
        self._events = deque(maxlen=128)
        self._generation = 0
        self._last_event = 0.0
        self._starting_at = 0.0
        self._retry_at = 0.0
        self._failures = 0
        self._reported_state = "Idle"
        self._enabled = False
        log.debug("Created isolated VLCPlayer proxy id=%s", id(self))

    @property
    def player(self):
        # Compatibility only; callers should not touch a native player anymore.
        return None

    def _spawn(self) -> None:
        if self._process and self._process.poll() is None:
            return
        cmd = _worker_command()
        creationflags = 0
        if sys.platform.startswith("win"):
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        log.debug("Spawning playback worker proxy=%s command=%r", id(self), cmd)
        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            creationflags=creationflags,
        )
        self._generation += 1
        generation = self._generation
        self._starting_at = time.monotonic()
        self._last_event = self._starting_at
        self._reported_state = "Connecting"
        threading.Thread(target=self._read_events, args=(self._process, generation),
                         name=f"VLC-events-{self._process.pid}", daemon=True).start()
        log.info("Playback worker started proxy=%s pid=%s", id(self), self._process.pid)

    def _read_events(self, proc: subprocess.Popen[str], generation: int) -> None:
        """Only the UI watchdog consumes events; never invoke Qt callbacks here."""
        try:
            if proc.stdout:
                for raw in proc.stdout:
                    try:
                        event = json.loads(raw)
                        if isinstance(event, dict):
                            with self._lock:
                                self._events.append((generation, event, time.monotonic()))
                    except (ValueError, TypeError):
                        log.warning("Invalid playback worker protocol event pid=%s", proc.pid)
        except (OSError, ValueError):
            pass
        finally:
            if proc.stdout:
                proc.stdout.close()

    def _announce(self, state: str) -> None:
        if self._reported_state != state:
            self._reported_state = state
            self._status_callback(state)

    def _schedule_retry(self, reason: str) -> None:
        self._failures += 1
        delay = min(30.0, 2.0 ** min(self._failures - 1, 5))
        self._retry_at = time.monotonic() + delay
        log.warning("Worker recovery scheduled reason=%s retry_in=%.1fs", reason, delay)
        self._announce(f"{reason} — retry in {delay:g}s")
        self.terminate()

    def _send(self, command: str, **payload) -> bool:
        with self._lock:
            proc = self._process
            if proc is None:
                log.warning("Cannot send %s: no playback worker", command)
                return False
            if not proc or not proc.stdin or proc.poll() is not None:
                log.error("Playback worker unavailable proxy=%s command=%s", id(self), command)
                return False
            message = {"command": command, **payload}
            try:
                proc.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
                proc.stdin.flush()
                log.debug("Worker command sent proxy=%s pid=%s command=%s", id(self), proc.pid, command)
                return True
            except (BrokenPipeError, OSError):
                log.exception("Worker command failed proxy=%s pid=%s command=%s", id(self), proc.pid, command)
                return False

    def attach_video(self, widget_id: int) -> None:
        widget_id = int(widget_id)
        self._attached_handle = widget_id
        log.debug("Proxy video target set player=%s hwnd=%s", id(self), widget_id)
        if self._process and self._process.poll() is None:
            self._send("attach", hwnd=widget_id)

    def play(self, url: str) -> None:
        # Always create a fresh worker for a new stream. This deliberately avoids
        # libVLC's native stop/teardown path when switching RTSP media.
        if self._process and self._process.poll() is None:
            log.debug("Replacing playback worker before new stream proxy=%s", id(self))
            self.terminate()
        self._enabled = True
        self._failures = 0
        self._retry_at = 0.0
        self._current_url = url
        self._paused = False
        self._spawn()
        if self._attached_handle is not None:
            self._send("attach", hwnd=self._attached_handle)
        self._send("volume", value=self._volume)
        self._send("mute", value=self._muted)
        log.info("Play isolated player=%s url=%s", id(self), redact_url(url))
        self._send("play", url=url)
        self._announce("Connecting…")

    def toggle_pause(self) -> bool:
        self._paused = not self._paused
        self._send("pause", value=self._paused)
        return self._paused

    def set_paused(self, paused: bool) -> None:
        self._paused = bool(paused)
        self._send("pause", value=self._paused)

    def detach_video(self) -> None:
        log.debug("Proxy detach player=%s hwnd=%s", id(self), self._attached_handle)
        self._attached_handle = None
        if self._process and self._process.poll() is None:
            self._send("attach", hwnd=0)

    @staticmethod
    def _reap_worker(proc: subprocess.Popen[str]) -> None:
        """Reap a detached worker off the GUI thread, with bounded escalation."""
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    log.warning("Worker pid=%s did not exit; killing", proc.pid)
                    proc.kill()
                    proc.wait(timeout=1.0)
            else:
                proc.wait(timeout=0)
            log.debug("Playback worker reaped pid=%s rc=%s", proc.pid, proc.returncode)
        except Exception:
            log.exception("Playback worker cleanup failed pid=%s", proc.pid)
        finally:
            try:
                if proc.stdin:
                    proc.stdin.close()
            except (OSError, ValueError):
                pass

    def check_health(self) -> bool:
        """Run from Qt's watchdog only; delivers events and supervises retries."""
        now = time.monotonic()
        with self._lock:
            pending = list(self._events)
            self._events.clear()
        for generation, event, timestamp in pending:
            if generation != self._generation or not self._enabled:
                continue
            self._last_event = max(self._last_event, timestamp)
            kind = event.get("event")
            if kind == "state":
                state = str(event.get("value", "Unknown"))
                if state in ("Playing", "Paused", "Buffering", "Opening"):
                    self._announce(state)
                    if state == "Playing":
                        self._failures = 0
                elif state == "Error":
                    self._schedule_retry("Playback error")
                    break
            elif kind == "fatal":
                self._schedule_retry("VLC unavailable")
                break
            elif kind == "command_error":
                log.warning("Worker rejected command=%s", event.get("command"))

        proc = self._process
        if proc is not None:
            code = proc.poll()
            if code is not None:
                log.error("Worker exited unexpectedly pid=%s exit=%s", proc.pid, code)
                self._schedule_retry(f"Worker exited ({code})") if self._enabled else self.terminate()
                return False
            if self._enabled and now - self._last_event > 10.0:
                self._schedule_retry("Worker unresponsive")
                return False
            return True
        if self._enabled and self._current_url and now >= self._retry_at:
            try:
                self._spawn()
                if self._attached_handle is not None:
                    self._send("attach", hwnd=self._attached_handle)
                self._send("volume", value=self._volume)
                self._send("mute", value=self._muted)
                self._send("play", url=self._current_url)
                if self._paused:
                    self._send("pause", value=True)
                self._announce("Reconnecting…")
            except OSError:
                log.exception("Unable to launch playback worker")
                self._schedule_retry("Worker launch failed")
        return self._process is not None or not self._enabled

    @staticmethod
    def _reap_worker_async(proc: subprocess.Popen[str]) -> None:
        threading.Thread(target=VLCPlayer._reap_worker, args=(proc,),
                         name=f"VLC-reaper-{proc.pid}", daemon=True).start()

    def terminate(self) -> None:
        """Detach the child immediately and do OS process teardown in the background.

        Never call libVLC stop()/release() in this process.
        """
        with self._lock:
            proc = self._process
            self._process = None
            self._generation += 1
        if proc is None:
            return
        log.info("Scheduling playback worker termination proxy=%s pid=%s", id(self), proc.pid)
        self._reap_worker_async(proc)

    def stop(self, *, detach: bool = True) -> None:
        self._enabled = False
        self._retry_at = 0.0
        # Compatibility alias. Crucially, this does NOT invoke libVLC stop().
        if detach:
            self._attached_handle = None
        log.debug("Stop proxy=%s implemented as worker termination", id(self))
        self.terminate()

    def release(self) -> None:
        self._enabled = False
        self._retry_at = 0.0
        log.debug("Release proxy=%s implemented as worker termination", id(self))
        self.terminate()

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        if self._process and self._process.poll() is None:
            self._send("mute", value=self._muted)

    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, int(volume)))
        if self._process and self._process.poll() is None:
            self._send("volume", value=self._volume)

    def get_volume(self) -> int:
        return self._volume

    def is_muted(self) -> bool:
        return self._muted


class VLCBackend:
    def __init__(self, status_callback: Callable[[str], None] | None = None) -> None:
        # Validate that the VLC runtime exists for packaged builds, but deliberately
        # do not import/load libVLC in the GUI process.
        configure_vlc_environment()
        bundled = _app_root() / "vlc"
        if getattr(sys, "frozen", False) and not bundled.exists():
            raise RuntimeError("The bundled VLC runtime is missing from this RelayView installation.")
        log.info("Creating isolated playback backend (libVLC remains outside GUI process)")
        self.primary = VLCPlayer(status_callback)
        self._extra_players: list[VLCPlayer] = []
        self._shutdown = False

    @property
    def player(self):
        return None

    def create_player(self, status_callback: Callable[[str], None] | None = None) -> VLCPlayer:
        player = VLCPlayer(status_callback)
        self._extra_players.append(player)
        log.debug("Registered isolated extra player=%s count=%s", id(player), len(self._extra_players))
        return player

    def release_player(self, player: VLCPlayer) -> None:
        log.debug("Releasing isolated extra player=%s", id(player))
        player.release()
        if player in self._extra_players:
            self._extra_players.remove(player)

    def attach_video(self, widget_id: int) -> None:
        self.primary.attach_video(widget_id)

    def play(self, url: str) -> None:
        self.primary.play(url)

    def toggle_pause(self) -> bool:
        return self.primary.toggle_pause()

    def quiesce_primary(self) -> None:
        log.info("Quiesce primary via process termination player=%s", id(self.primary))
        self.primary.stop(detach=True)
        log.info("Quiesce primary complete")

    def stop_primary(self) -> None:
        self.quiesce_primary()

    def stop(self) -> None:
        log.info("Stopping isolated backend workers extra_players=%s", len(self._extra_players))
        self.primary.stop(detach=True)
        for player in list(self._extra_players):
            player.stop(detach=True)
        log.info("Isolated backend workers stopped")

    def shutdown(self) -> None:
        if self._shutdown:
            log.debug("Playback backend shutdown skipped already_shutdown=True")
            return
        self._shutdown = True
        log.warning("Playback backend shutdown begin extra_players=%s", len(self._extra_players))
        for player in list(self._extra_players):
            self.release_player(player)
        self.primary.release()
        log.warning("Playback backend shutdown complete")

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
