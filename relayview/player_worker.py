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


def _report_player(player, stop_event: threading.Event) -> None:
    """Report native VLC state from within the isolated worker process."""
    last_state = None
    while not stop_event.wait(1.0):
        try:
            state = str(player.get_state()).split(".")[-1]
            _emit("heartbeat", state=state)
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

    stop_event = threading.Event()
    threading.Thread(target=_report_player, args=(player, stop_event), daemon=True, name="vlc-state").start()
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
                    player.set_media(media)
                    result = player.play()
                    _worker_log(f"play returned={result}")
                    if result == -1:
                        _emit("state", value="Error")
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
