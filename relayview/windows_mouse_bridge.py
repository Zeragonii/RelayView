"""Scoped Windows mouse input for libVLC's out-of-process child HWNDs.

libVLC's native video windows may be owned by another process: Qt's event
filter cannot receive their mouse events. A low-level mouse hook runs on our
Qt UI thread and only acts inside a visible grid video rectangle.
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

from .logging_config import get_logger

log = get_logger('mouse')


def wheel_steps(delta: int) -> int:
    """Convert a Windows wheel delta to discrete 0.25x zoom steps."""
    if delta == 0:
        return 0
    return max(1, abs(delta) // 120) * (1 if delta > 0 else -1)


if sys.platform == 'win32':
    from PySide6.QtCore import QObject, QPoint
    from PySide6.QtWidgets import QApplication

    WH_MOUSE_LL = 14
    WM_MOUSEMOVE = 0x0200
    WM_MBUTTONDOWN = 0x0207
    WM_MBUTTONUP = 0x0208
    WM_MOUSEWHEEL = 0x020A
    GA_ROOT = 2

    class _POINT(ctypes.Structure):
        _fields_ = [('x', wintypes.LONG), ('y', wintypes.LONG)]

    class _MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [('pt', _POINT), ('mouseData', wintypes.DWORD),
                    ('flags', wintypes.DWORD), ('time', wintypes.DWORD),
                    ('dwExtraInfo', ctypes.c_size_t)]

    _HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

    class WindowsMouseBridge(QObject):
        def __init__(self, grid):
            super().__init__(grid)
            self.grid = grid
            self._hook = None
            self._pan_tile = None
            self._pan_last = None
            self._wheel_remainder = 0
            self._last_pan_dispatch = 0.0
            self._pan_pending = [0, 0]
            self._proc = _HOOKPROC(self._callback)  # Keep callback alive while hooked.
            user32 = ctypes.windll.user32
            self._user32 = user32
            user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
            user32.SetWindowsHookExW.restype = wintypes.HHOOK
            user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
            user32.CallNextHookEx.restype = ctypes.c_ssize_t
            user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
            user32.UnhookWindowsHookEx.restype = wintypes.BOOL
            user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            user32.GetAncestor.restype = wintypes.HWND
            user32.GetForegroundWindow.restype = wintypes.HWND
            self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, None, 0)
            if not self._hook:
                log.warning('Windows mouse hook could not be installed: error=%s', ctypes.get_last_error())
            else:
                log.info('Native VLC mouse wheel/pan bridge installed')
            app = QApplication.instance()
            if app:
                app.aboutToQuit.connect(self.close)

        def close(self):
            if self._hook:
                self._user32.UnhookWindowsHookEx(self._hook)
                self._hook = None
                self._proc = None
                log.debug('Native mouse bridge removed')

        def _active(self):
            if not self.grid.isVisible():
                return False
            foreground = self._user32.GetForegroundWindow()
            own_root = self._user32.GetAncestor(int(self.grid.window().winId()), GA_ROOT)
            return bool(foreground and own_root and foreground == own_root)

        def _tile_at(self, global_pos):
            for tile in self.grid.tiles:
                if tile.stream is None or not tile.isVisible() or not tile.video.isVisible():
                    continue
                local = tile.video.mapFromGlobal(global_pos)
                if tile.video.rect().contains(local):
                    return tile
            return None

        def _handle(self, message, pos, mouse_data):
            if not self._active():
                self._pan_tile = None
                self._pan_last = None
                self._wheel_remainder = 0
                return False
            if message == WM_MOUSEWHEEL:
                tile = self._tile_at(pos)
                if tile is None:
                    self._wheel_remainder = 0
                    return False
                signed_delta = ctypes.c_short((mouse_data >> 16) & 0xffff).value
                self._wheel_remainder += signed_delta
                steps = int(self._wheel_remainder / 120)
                self._wheel_remainder -= steps * 120
                if steps:
                    log.debug('Native wheel tile=%s steps=%s', tile.index, steps)
                    tile.zoom_by(steps)
                return True  # Do not let VLC interpret wheel as volume adjustment.
            if message == WM_MBUTTONDOWN:
                tile = self._tile_at(pos)
                if tile and tile.zoom.factor > 1:
                    self._pan_tile, self._pan_last = tile, pos
                    self._pan_pending = [0, 0]
                    self._last_pan_dispatch = 0.0
                    log.debug('Native pan start tile=%s', tile.index)
                    return True
            elif message == WM_MOUSEMOVE and self._pan_tile is not None:
                if self._pan_tile not in self.grid.tiles or not self._pan_tile.isVisible():
                    self._pan_tile, self._pan_last = None, None
                    return False
                dx = pos.x() - self._pan_last.x()
                dy = pos.y() - self._pan_last.y()
                self._pan_last = pos
                self._pan_pending[0] += dx
                self._pan_pending[1] += dy
                if time.monotonic() - self._last_pan_dispatch >= 1 / 30:
                    self._flush_pan()
                return True
            elif message == WM_MBUTTONUP and self._pan_tile is not None:
                self._flush_pan()
                self._pan_tile, self._pan_last = None, None
                log.debug('Native pan ended')
                return True
            return False

        def _flush_pan(self):
            if self._pan_tile is None:
                return
            dx, dy = self._pan_pending
            self._pan_pending = [0, 0]
            self._last_pan_dispatch = time.monotonic()
            if dx or dy:
                self._pan_tile.pan_by(-dx / max(1, self._pan_tile.video.width()),
                                      -dy / max(1, self._pan_tile.video.height()))

        def _callback(self, code, wparam, lparam):
            if code >= 0 and wparam in (WM_MOUSEWHEEL, WM_MBUTTONDOWN, WM_MOUSEMOVE, WM_MBUTTONUP):
                try:
                    info = ctypes.cast(lparam, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
                    if self._handle(int(wparam), QPoint(info.pt.x, info.pt.y), int(info.mouseData)):
                        return 1
                except Exception:
                    log.exception('Native mouse handling failed')
            return self._user32.CallNextHookEx(self._hook, code, wparam, lparam)
else:
    class WindowsMouseBridge:
        def __init__(self, grid):
            self.grid = grid

        def close(self):
            pass
