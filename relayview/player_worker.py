from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path


def _worker_log(message: str) -> None:
    """Best-effort per-process logging without sharing RotatingFileHandler state."""
    try:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "RelayView" / "logs"
        base.mkdir(parents=True, exist_ok=True)
        line = f"{datetime.now().isoformat(timespec='milliseconds')} | pid={os.getpid()} | {message}\n"
        with (base / "player-workers.log").open("a", encoding="utf-8") as handle:
            handle.write(line)
    except Exception:
        pass


def _configure_vlc() -> None:
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
    else:
        root = Path(__file__).resolve().parent.parent
    bundled = root / "vlc"
    if bundled.exists():
        os.environ["PATH"] = str(bundled) + os.pathsep + os.environ.get("PATH", "")
        plugins = bundled / "plugins"
        if plugins.exists():
            os.environ["VLC_PLUGIN_PATH"] = str(plugins)


def _emit(event: str, **fields) -> None:
    # stdout is exclusively for protocol messages; logs go to the worker logfile.
    try:
        sys.stdout.write(json.dumps({"event": event, **fields}, separators=(",", ":")) + "\n")
        sys.stdout.flush()
    except (BrokenPipeError, OSError):
        pass


def _report_player(player, stop_event: threading.Event, zoom_callback=None) -> None:
    """Report native VLC state from within the isolated worker process."""
    last_state = None
    last_frames = -1
    while not stop_event.wait(1.0):
        try:
            if zoom_callback is not None:
                zoom_callback()
            state = str(player.get_state()).split(".")[-1]
            _emit("heartbeat", state=state)
            # libVLC video decoder statistics are unavailable for some streams.
            # Never invent frame progress when the decoder does not expose it.
            if state == "Playing":
                try:
                    media = player.get_media()
                    stats_result = media.get_stats() if media else None
                    stats = stats_result[1] if isinstance(stats_result, tuple) and len(stats_result) == 2 and stats_result[0] else None
                    frames = getattr(stats, "displayed_pictures", None) if stats is not None else None
                    if frames is not None and int(frames) >= 0 and int(frames) != last_frames:
                        last_frames = int(frames)
                        _emit("progress", frames=last_frames)
                except (AttributeError, TypeError, ValueError):
                    pass
            if state != last_state:
                _emit("state", value=state)
                last_state = state
        except Exception as exc:
            _worker_log(f"state polling failed: {type(exc).__name__}")
            _emit("state", value="Error")
            return


def run_worker() -> int:
    _worker_log("worker starting")
    try:
        _configure_vlc()
        import vlc
        instance = vlc.Instance("--no-video-title-show", "--quiet", "--network-caching=250", "--clock-jitter=0")
        player = instance.media_player_new()
    except Exception as exc:
        _worker_log(f"initialisation failed: {exc!r}")
        _emit("fatal", message="VLC initialisation failed")
        return 2

    # Keep the requested crop across video output reinitialisation. Some streams
    # do not expose dimensions until the first decoded frame arrives.
    zoom_request = {"factor": 1.0, "cx": 0.5, "cy": 0.5}
    last_crop = object()
    last_zoom_note = object()
    zoom_lock = threading.RLock()

    def apply_zoom() -> None:
        nonlocal last_crop, last_zoom_note
        from .zoom import ZoomState
        with zoom_lock:
            try:
                factor = float(zoom_request["factor"])
                w, h = player.video_get_size(0)
                state = ZoomState(factor, float(zoom_request["cx"]), float(zoom_request["cy"]))
                crop = state.crop(w, h)
                if factor > 1.0 and crop is None:
                    if last_zoom_note != "dimensions-pending":
                        _emit("zoom_status", status="dimensions-pending", width=w, height=h, factor=factor)
                        last_zoom_note = "dimensions-pending"
                    return
                if crop != last_crop:
                    player.video_set_crop_geometry(crop)
                    last_crop = crop
                    last_zoom_note = crop
                    _emit("zoom_status", status="applied", crop=crop, width=w, height=h, factor=factor)
            except Exception as exc:
                note = ("error", type(exc).__name__)
                if last_zoom_note != note:
                    _worker_log(f"zoom failed: {exc!r}")
                    _emit("zoom_status", status="error", detail=type(exc).__name__)
                    last_zoom_note = note

    stop_event = threading.Event()
    threading.Thread(target=_report_player, args=(player, stop_event, apply_zoom), daemon=True, name="vlc-state").start()
    _emit("ready")

    # Intentionally never call player.stop()/release() on normal teardown. The
    # parent process terminates this worker to let Windows reclaim native libVLC
    # resources atomically, isolating known RTSP teardown crashes from the GUI.
    try:
        for raw in sys.stdin:
            try:
                msg = json.loads(raw)
                command = msg.get("command")
                if command == "attach":
                    hwnd = int(msg.get("hwnd", 0))
                    if sys.platform.startswith("win"):
                        player.set_hwnd(hwnd)
                    elif sys.platform == "darwin":
                        player.set_nsobject(hwnd)
                    else:
                        player.set_xwindow(hwnd)
                    _worker_log(f"attached hwnd={hwnd}")
                elif command == "play":
                    url = str(msg["url"])
                    media = instance.media_new(url)
                    last_crop = object()
                    player.set_media(media)
                    result = player.play()
                    _worker_log(f"play returned={result}")
                    if result == -1:
                        _emit("state", value="Error")
                elif command == "zoom":
                    from .zoom import ZoomState
                    state = ZoomState(float(msg.get("factor", 1.0)), float(msg.get("cx", 0.5)), float(msg.get("cy", 0.5)))
                    state.factor = max(1.0, min(5.0, state.factor))
                    state._clamp()
                    with zoom_lock:
                        next_request = dict(factor=state.factor, cx=state.cx, cy=state.cy)
                        if next_request != zoom_request:
                            zoom_request.update(next_request)
                        last_zoom_note = object()
                    apply_zoom()
                elif command == "volume":
                    player.audio_set_volume(max(0, min(100, int(msg.get("value", 100)))))
                elif command == "mute":
                    player.audio_set_mute(bool(msg.get("value", False)))
                elif command == "pause":
                    player.set_pause(1 if bool(msg.get("value", False)) else 0)
                elif command == "ping":
                    _emit("pong")
            except Exception as exc:
                _worker_log(f"command failed: {type(exc).__name__}")
                _emit("command_error", command=command)
    except Exception as exc:
        _worker_log(f"worker loop failed: {exc!r}")
        return 3

    stop_event.set()
    _worker_log("stdin closed; exiting without libVLC teardown")
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(run_worker())
