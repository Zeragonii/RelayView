"""Zoom adapter for the primary (single-camera) mpv player.

Matches the narrow interface used by WindowsMouseBridge for grid tiles,
without introducing a second Windows mouse hook or manipulating the HWND.
"""
from __future__ import annotations

from typing import Callable

from .logging_config import get_logger
from .zoom import ZoomState

log = get_logger("single_zoom")


class SingleViewZoom:
    """Treat single-camera playback as another zoomable native video surface."""

    index = -1  # Distinct from numbered grid tiles in wheel/pan diagnostics.

    def __init__(self, video, player, stream_getter: Callable, active_getter: Callable[[], bool]):
        self.video = video
        self.player = player
        self._stream_getter = stream_getter
        self._active_getter = active_getter
        self.zoom = ZoomState()

    @property
    def stream(self):
        return self._stream_getter() if self._active_getter() else None

    def isVisible(self) -> bool:  # noqa: N802 - match QWidget's existing API
        return bool(self._active_getter() and self.video.isVisible())

    def _update_zoom(self) -> None:
        if self.player is not None:
            self.player.set_zoom(self.zoom.factor, self.zoom.cx, self.zoom.cy)

    def zoom_by(self, steps: int) -> None:
        if self.stream is None:
            return
        previous = self.zoom.factor
        self.zoom.change(steps)
        if self.zoom.factor != previous:
            log.info("Single camera zoom old=%.2f new=%.2f", previous, self.zoom.factor)
            self._update_zoom()

    def reset_zoom(self) -> None:
        self.zoom.reset()
        self._update_zoom()
