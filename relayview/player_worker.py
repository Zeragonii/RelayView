from __future__ import annotations

import json
import os
import sys
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


def run_worker() -> int:
    _worker_log("worker starting")
    try:
        _configure_vlc()
        import vlc
        instance = vlc.Instance("--no-video-title-show", "--quiet", "--network-caching=250", "--clock-jitter=0")
        player = instance.media_player_new()
    except Exception as exc:
        _worker_log(f"initialisation failed: {exc!r}")
        return 2

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
                elif command == "volume":
                    player.audio_set_volume(max(0, min(100, int(msg.get("value", 100)))))
                elif command == "mute":
                    player.audio_set_mute(bool(msg.get("value", False)))
                elif command == "pause":
                    player.set_pause(1 if bool(msg.get("value", False)) else 0)
                elif command == "ping":
                    pass
            except Exception as exc:
                _worker_log(f"command failed: {exc!r}")
    except Exception as exc:
        _worker_log(f"worker loop failed: {exc!r}")
        return 3

    _worker_log("stdin closed; exiting without libVLC teardown")
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(run_worker())
