"""Per-camera bounded zoom state, independent of decoding and Qt."""
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

