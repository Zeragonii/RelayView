"""Pure per-tile digital zoom geometry; no native video dependencies."""
from __future__ import annotations
from dataclasses import dataclass

MIN_ZOOM = 1.0
MAX_ZOOM = 5.0
STEP = 0.25


@dataclass
class ZoomState:
    factor: float = 1.0
    cx: float = 0.5
    cy: float = 0.5

    def change(self, steps: int) -> None:
        self.factor = round(max(MIN_ZOOM, min(MAX_ZOOM, self.factor + steps * STEP)), 2)
        self._clamp()

    def move(self, dx: float, dy: float) -> None:
        self.cx += dx / self.factor
        self.cy += dy / self.factor
        self._clamp()

    def reset(self) -> None:
        self.factor, self.cx, self.cy = 1.0, 0.5, 0.5

    def _clamp(self) -> None:
        margin = 0.5 / self.factor
        self.cx = max(margin, min(1 - margin, self.cx))
        self.cy = max(margin, min(1 - margin, self.cy))

    def crop(self, width: int, height: int) -> str | None:
        if self.factor <= 1.0 or width <= 0 or height <= 0:
            return None
        self._clamp()
        w = max(1, min(width, round(width / self.factor)))
        h = max(1, min(height, round(height / self.factor)))
        x = max(0, min(width - w, round(self.cx * width - w / 2)))
        y = max(0, min(height - h, round(self.cy * height - h / 2)))
        # VLC 3.x crop geometry treats WxH as bottom-right coordinates for
        # offset crops, so encode (right,bottom,left,top), not (width,height,left,top).
        return f"{x + w}x{y + h}+{x}+{y}"


def viewport_geometry(state: ZoomState, width: int, height: int) -> tuple[int, int, int, int]:
    """Child video window rectangle, relative to a clipping viewport.

    The video decoder always renders into the whole child HWND. Instead of
    asking libVLC to crop/recentre every frame, the GUI scales that native HWND
    and translates it behind a fixed-size native parent window. Its parent
    clips the oversize portions at the viewport border.

    The normalized (cx, cy) denotes the source point at the viewport centre.
    It uses the same bounds as ZoomState._clamp(), so no black edges appear.
    """
    if width <= 0 or height <= 0:
        return (0, 0, max(1, width), max(1, height))
    state._clamp()
    scaled_width = max(1, round(width * state.factor))
    scaled_height = max(1, round(height * state.factor))
    left = round(width / 2 - state.cx * scaled_width)
    top = round(height / 2 - state.cy * scaled_height)
    # Round-off must not expose the background at extreme pan positions.
    left = max(width - scaled_width, min(0, left))
    top = max(height - scaled_height, min(0, top))
    return (left, top, scaled_width, scaled_height)
