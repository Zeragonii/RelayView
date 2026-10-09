"""Isolated libmpv decoder and video renderer, controlled by newline JSON IPC."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from .mpv_native import (MPV_EVENT_END_FILE,
                         MPV_EVENT_FILE_LOADED, MPV_EVENT_NONE, MpvClient,
                         MpvError, view_properties)


def _worker_log(message: str) -> None:
    try:
        directory = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "RelayView" / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "player-workers.log").open("a", encoding="utf-8") as file:
            file.write(f"{datetime.now().isoformat(timespec='milliseconds')} | pid={os.getpid()} | {message}\n")
    except Exception:
        pass


def _emit(event: str, **fields) -> None:
    try:
        sys.stdout.write(json.dumps({"event": event, **fields}, separators=(",", ":")) + "\n")
        sys.stdout.flush()
    except (BrokenPipeError, OSError):
        pass


def _report_player(client: MpvClient, stop: threading.Event, loaded: threading.Event, started: threading.Event) -> None:
    previous_state = None
    previous_pts: float | None = None
    frame_count = 0
    while not stop.wait(1.0):
        try:
            if not client.initialized:
                _emit("heartbeat", state="Opening")
                continue
            # Drain native player events. An RTSP stream ending unexpectedly should
            # recover just like an unhandled process exit.
            for _ in range(128):
                event_id, reason = client.event()
                if event_id == MPV_EVENT_NONE:
                    break
                if event_id == MPV_EVENT_FILE_LOADED:
                    loaded.set()
                elif event_id == MPV_EVENT_END_FILE and started.is_set():
                    _worker_log(f"stream ended reason={reason}")
                    _emit("state", value="Error")
                    return
            idle = client.read("idle-active") == "yes"
            paused = client.read("pause") == "yes"
            buffering = client.read("paused-for-cache") == "yes"
            state = "Opening" if idle and not loaded.is_set() else ("Error" if idle else ("Paused" if paused else ("Buffering" if buffering else "Playing")))
            _emit("heartbeat", state=state)
            if state != previous_state:
                _emit("state", value=state)
                previous_state = state
            if state == "Playing":
                # video-pts is a video-specific clock; time-pos alone may move
                # even when a displayed frame is frozen. Don't fabricate progress.
                pts = client.read("video-pts")
                try:
                    parsed = float(pts) if pts is not None else None
                except (ValueError, TypeError):
                    parsed = None
                # Video PTS can reset on RTSP reconnect or clock discontinuity;
                # any genuine change counts as progress, not only increases.
                if parsed is not None and (previous_pts is None or abs(parsed - previous_pts) > 0.00001):
                    frame_count += 1
                    _emit("progress", frames=frame_count)
                    previous_pts = parsed
        except Exception as exc:
            _worker_log(f"polling failed: {type(exc).__name__}: {exc}")
            _emit("state", value="Error")
            return


def run_worker() -> int:
    _worker_log("libmpv worker starting")
    try:
        client = MpvClient()
    except Exception as exc:
        _worker_log(f"mpv load failed: {type(exc).__name__}: {exc}")
        _emit("fatal", message="libmpv runtime unavailable")
        return 2

    stop = threading.Event()
    loaded = threading.Event()
    started = threading.Event()
    hwnd = None
    desired_volume = 100
    desired_muted = False
    desired_paused = False
    desired_view = (1.0, 0.5, 0.5)
    _emit("ready")
    reporter = threading.Thread(target=_report_player, args=(client, stop, loaded, started),
                                daemon=True, name="mpv-monitor")
    reporter.start()

    try:
        for raw in sys.stdin:
            command = None
            try:
                msg = json.loads(raw)
                command = msg.get("command")
                if command == "attach":
                    new_hwnd = int(msg.get("hwnd", 0))
                    if client.initialized and new_hwnd != hwnd and new_hwnd > 0:
                        raise MpvError("video target changed after mpv initialization; start a new worker")
                    hwnd = new_hwnd or None
                elif command == "play":
                    if not client.initialized:
                        client.initialize(hwnd)
                    loaded.clear()
                    client.property("volume", desired_volume)
                    client.property("mute", desired_muted)
                    client.property("pause", desired_paused)
                    for key, value in view_properties(*desired_view).items():
                        client.property(key, value)
                    url = str(msg["url"])
                    started.set()
                    client.command("loadfile", url, "replace")
                    # URLs may contain passwords: never log the raw arguments.
                    _worker_log("mpv loadfile accepted")
                elif command == "zoom":
                    desired_view = (float(msg.get("factor", 1)), float(msg.get("cx", 0.5)), float(msg.get("cy", 0.5)))
                    if client.initialized:
                        for key, value in view_properties(*desired_view).items():
                            client.property(key, value)
                    _emit("view", factor=desired_view[0], cx=desired_view[1], cy=desired_view[2])
                elif command == "volume":
                    desired_volume = max(0, min(100, int(msg.get("value", 100))))
                    if client.initialized:
                        client.property("volume", desired_volume)
                elif command == "mute":
                    desired_muted = bool(msg.get("value", False))
                    if client.initialized:
                        client.property("mute", desired_muted)
                elif command == "pause":
                    desired_paused = bool(msg.get("value", False))
                    if client.initialized:
                        client.property("pause", desired_paused)
                elif command == "ping":
                    _emit("pong")
            except (ValueError, TypeError, MpvError, KeyError) as exc:
                _worker_log(f"command {command} failed: {type(exc).__name__}: {exc}")
                _emit("command_error", command=command)
                if command == "play":
                    _emit("state", value="Error")
    except Exception as exc:
        _worker_log(f"IPC failed: {type(exc).__name__}: {exc}")
        return 3
    finally:
        stop.set()
        # Process termination isolates third-party native shutdown paths.
        # Worker handles are reclaimed by the OS after exit.
        _worker_log("worker stdin closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_worker())
