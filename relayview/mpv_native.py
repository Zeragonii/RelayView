"""Minimal libmpv C API binding, intentionally loaded *only* in player workers.

Uses stdlib ctypes to avoid importing a second, Qt-owning Python UI wrapper.
The C API is stable; no installed mpv.exe or system PATH dependency is needed.
"""
from __future__ import annotations

import ctypes
import math
import os
import sys
from pathlib import Path

MPV_EVENT_NONE = 0
MPV_EVENT_SHUTDOWN = 1
MPV_EVENT_END_FILE = 7
MPV_EVENT_FILE_LOADED = 8


class MpvError(RuntimeError):
    pass


class _Event(ctypes.Structure):
    _fields_ = [
        ("event_id", ctypes.c_int),
        ("error", ctypes.c_int),
        ("reply_userdata", ctypes.c_uint64),
        ("data", ctypes.c_void_p),
    ]


class _EndFile(ctypes.Structure):
    _fields_ = [
        ("reason", ctypes.c_int),
        ("error", ctypes.c_int),
        ("playlist_entry_id", ctypes.c_int64),
        ("playlist_insert_id", ctypes.c_int64),
        ("playlist_insert_num_entries", ctypes.c_int),
    ]


def runtime_directory() -> Path:
    root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    return root / "mpv"


def _library_file() -> Path:
    directory = runtime_directory()
    if sys.platform == "win32":
        for filename in ("libmpv-2.dll", "mpv-2.dll"):
            candidate = directory / filename
            if candidate.is_file():
                return candidate
        raise MpvError(f"Missing libmpv-2.dll in {directory}")
    if sys.platform == "darwin":
        return directory / "libmpv.dylib" if (directory / "libmpv.dylib").exists() else Path("libmpv.dylib")
    return directory / "libmpv.so" if (directory / "libmpv.so").exists() else Path("libmpv.so.2")


class MpvClient:
    """Own one libmpv handle. Never share this object between processes."""

    def __init__(self, *, dll=None):
        self._dll_dir = None
        if dll is None:
            lib_path = _library_file()
            if sys.platform == "win32":
                # Bundled native dependencies are found beside libmpv, not on PATH.
                self._dll_dir = os.add_dll_directory(str(lib_path.parent))
                dll = ctypes.CDLL(str(lib_path))
            else:
                dll = ctypes.CDLL(str(lib_path))
        self._dll = dll
        self._bind()
        self.handle = self._dll.mpv_create()
        if not self.handle:
            raise MpvError("mpv_create returned NULL")
        self.initialized = False

    def _bind(self):
        specs = {
            "mpv_create": (ctypes.c_void_p, []),
            "mpv_set_option_string": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]),
            "mpv_initialize": (ctypes.c_int, [ctypes.c_void_p]),
            "mpv_command": (ctypes.c_int, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p)]),
            "mpv_set_property_string": (ctypes.c_int, [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]),
            "mpv_get_property_string": (ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_char_p]),
            "mpv_free": (None, [ctypes.c_void_p]),
            "mpv_wait_event": (ctypes.POINTER(_Event), [ctypes.c_void_p, ctypes.c_double]),
        }
        for name, (result, args) in specs.items():
            function = getattr(self._dll, name)
            function.argtypes = args
            function.restype = result

    @staticmethod
    def _check(code: int, context: str) -> None:
        if code < 0:
            raise MpvError(f"{context} failed (libmpv error {code})")

    def option(self, name: str, value: str) -> None:
        self._check(self._dll.mpv_set_option_string(self.handle, name.encode(), str(value).encode()), f"option {name}")

    def initialize(self, hwnd: int | None, *, headless: bool = False) -> None:
        if self.initialized:
            return
        if headless:
            self.option("vo", "null")
        elif not hwnd or hwnd < 0:
            raise MpvError("A valid video window HWND is required before playing")
        else:
            self.option("wid", str(int(hwnd)))
            self.option("vo", "gpu")
        for key, value in (
            ("config", "no"), ("input-default-bindings", "no"),
            ("input-vo-keyboard", "no"), ("osc", "no"),
            ("osd-level", "0"), ("keepaspect", "yes"),
            ("hwdec", "auto-safe"), ("rtsp-transport", "tcp"),
            ("demuxer-readahead-secs", "0.5"),
        ):
            self.option(key, value)
        self._check(self._dll.mpv_initialize(self.handle), "mpv_initialize")
        self.initialized = True

    def property(self, name: str, value: str | int | float | bool) -> None:
        if isinstance(value, bool):
            value = "yes" if value else "no"
        self._check(self._dll.mpv_set_property_string(self.handle, name.encode(), str(value).encode()), f"property {name}")

    def read(self, name: str) -> str | None:
        address = self._dll.mpv_get_property_string(self.handle, name.encode())
        if not address:
            return None
        try:
            return ctypes.string_at(address).decode("utf-8", errors="replace")
        finally:
            self._dll.mpv_free(address)

    def command(self, *arguments: str) -> None:
        items = (ctypes.c_char_p * (len(arguments) + 1))(*(a.encode("utf-8") for a in arguments), None)
        self._check(self._dll.mpv_command(self.handle, items), "mpv_command")

    def event(self) -> tuple[int, int | None]:
        pointer = self._dll.mpv_wait_event(self.handle, 0.0)
        if not pointer:
            return MPV_EVENT_NONE, None
        evt = pointer.contents
        reason = None
        if evt.event_id == MPV_EVENT_END_FILE and evt.data:
            reason = ctypes.cast(evt.data, ctypes.POINTER(_EndFile)).contents.reason
        return evt.event_id, reason


def view_properties(factor: float, cx: float, cy: float) -> dict[str, float]:
    """Map bounded tile zoom state to mpv native transform properties.

    video-align controls the *visible* rectangle and cannot pan outside the
    image. Unlike video-pan, coordinates remain valid at extreme zoom levels.
    """
    zoom = max(1.0, min(5.0, float(factor)))
    span = 1.0 - (1.0 / zoom)
    if span <= 0:
        return {"video-zoom": 0.0, "video-align-x": 0.0, "video-align-y": 0.0}
    def alignment(center):
        lo = 0.5 / zoom
        center = max(lo, min(1 - lo, float(center)))
        return max(-1.0, min(1.0, 2 * (center - 0.5) / span))
    return {"video-zoom": math.log2(zoom), "video-align-x": alignment(cx), "video-align-y": alignment(cy)}
