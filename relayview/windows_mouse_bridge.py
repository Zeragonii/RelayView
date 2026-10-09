"""Windows input bridge: wheel hook + *polled* middle-button dragging.

Low-level WH_MOUSE_LL wheel capture is needed because mpv renders into a
native HWND owned by a playback worker. Middle-drag uses GetAsyncKeyState
from the Qt event loop, rather than relying on native middle-button messages
from the foreign child window. No worker calls execute in the mouse hook.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from .logging_config import get_logger
from .mouse_pan import anchored_pan_center

log = get_logger('mouse')


def wheel_steps(delta: int) -> int:
    """Convert a Windows wheel delta into discrete 0.25x zoom steps."""
    if delta == 0:
        return 0
    return max(1, abs(delta) // 120) * (1 if delta > 0 else -1)


if sys.platform == 'win32':
    from PySide6.QtCore import QObject, QTimer
    from PySide6.QtGui import QCursor
    from PySide6.QtWidgets import QApplication

    WH_MOUSE_LL = 14
    WM_MOUSEWHEEL = 0x020A
    GA_ROOT = 2
    VK_MBUTTON = 0x04

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
            self._pan_origin = None
            self._pan_center = None
            self._wheel_remainder = 0

            self._user32 = ctypes.windll.user32
            user32 = self._user32
            user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
            user32.SetWindowsHookExW.restype = wintypes.HHOOK
            user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
            user32.CallNextHookEx.restype = ctypes.c_ssize_t
            user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
            user32.UnhookWindowsHookEx.restype = wintypes.BOOL
            user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            user32.GetAncestor.restype = wintypes.HWND
            user32.GetForegroundWindow.restype = wintypes.HWND
            user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
            user32.GetAsyncKeyState.restype = wintypes.SHORT

            # Polling is deliberately separate from WH_MOUSE_LL. In particular,
            # do not swallow middle button messages or move/resize video HWNDs.
            self._pan_timer = QTimer(self)
            self._pan_timer.setInterval(25)  # 40 Hz, enough for a responsive pan
            self._pan_timer.timeout.connect(self._poll_pan)
            self._pan_timer.start()

            self._proc = _HOOKPROC(self._callback)
            self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, None, 0)
            if not self._hook:
                log.warning('Wheel hook unavailable error=%s (middle pan polling remains active)', ctypes.get_last_error())
            else:
                log.info('Wheel hook installed; middle pan polled via GetAsyncKeyState')
            app = QApplication.instance()
            if app:
                app.aboutToQuit.connect(self.close)

        def close(self):
            self._pan_timer.stop()
            self._clear_pan()
            if self._hook:
                self._user32.UnhookWindowsHookEx(self._hook)
                self._hook = None
                self._proc = None
                log.debug('Native wheel hook removed')

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

        def _clear_pan(self):
            self._pan_tile = None
            self._pan_origin = None
            self._pan_center = None

        def _poll_pan(self):
            try:
                # GetAsyncKeyState uses the *physical* middle-button state and
                # continues working even if mpv/Qt consume mouse messages.
                pressed = bool(self._user32.GetAsyncKeyState(VK_MBUTTON) & 0x8000)
                if not self._active():
                    if self._pan_tile is not None:
                        log.info('Pan cancelled: viewer lost foreground')
                    self._clear_pan()
                    return

                pos = QCursor.pos()  # Qt coordinates match QWidget.mapFromGlobal.
                if not pressed:
                    if self._pan_tile is not None:
                        self._apply_pan(self._pan_tile, pos)
                        tile = self._pan_tile
                        log.info('Middle pan end tile=%s center=(%.3f, %.3f)', tile.index, tile.zoom.cx, tile.zoom.cy)
                        self._clear_pan()
                    return

                if self._pan_tile is None:
                    tile = self._tile_at(pos)
                    if tile is None or tile.zoom.factor <= 1:
                        return
                    self._pan_tile = tile
                    self._pan_origin = pos
                    self._pan_center = (tile.zoom.cx, tile.zoom.cy)
                    log.info('Middle pan start tile=%s zoom=%.2f center=%s', tile.index, tile.zoom.factor, self._pan_center)
                    return

                self._apply_pan(self._pan_tile, pos)
            except Exception:
                log.exception('Middle pan polling failed')
                self._clear_pan()

        def _apply_pan(self, tile, global_pos):
            if (tile not in self.grid.tiles or not tile.isVisible()
                    or not tile.stream or tile.zoom.factor <= 1):
                self._clear_pan()
                return
            cx, cy = anchored_pan_center(
                (self._pan_origin.x(), self._pan_origin.y()),
                (global_pos.x(), global_pos.y()),
                self._pan_center, tile.zoom.factor,
                (tile.video.width(), tile.video.height()),
            )
            if abs(tile.zoom.cx - cx) < 0.0003 and abs(tile.zoom.cy - cy) < 0.0003:
                return
            tile.zoom.cx, tile.zoom.cy = cx, cy
            tile._update_zoom()
            log.debug('Middle pan update tile=%s center=(%.4f, %.4f)', tile.index, cx, cy)

        def _callback(self, code, wparam, lparam):
            if code >= 0 and wparam == WM_MOUSEWHEEL:
                try:
                    info = ctypes.cast(lparam, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
                    if self._active():
                        from PySide6.QtCore import QPoint
                        tile = self._tile_at(QPoint(info.pt.x, info.pt.y))
                        if tile is not None:
                            signed_delta = ctypes.c_short((int(info.mouseData) >> 16) & 0xffff).value
                            self._wheel_remainder += signed_delta
                            steps = int(self._wheel_remainder / 120)
                            self._wheel_remainder -= steps * 120
                            if steps:
                                log.debug('Native wheel tile=%s steps=%s', tile.index, steps)
                                tile.zoom_by(steps)
                            return 1
                    else:
                        self._wheel_remainder = 0
                except Exception:
                    log.exception('Native wheel input failed')
            return self._user32.CallNextHookEx(self._hook, code, wparam, lparam)
else:
    class WindowsMouseBridge:
        def __init__(self, grid):
            self.grid = grid

        def close(self):
            pass
