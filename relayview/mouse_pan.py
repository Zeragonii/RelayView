"""Pure mouse drag geometry, independent of native video/input backends."""
from __future__ import annotations


def anchored_pan_center(origin: tuple[float, float], current: tuple[float, float],
                        center: tuple[float, float], zoom: float,
                        viewport: tuple[float, float]) -> tuple[float, float]:
    """Pan the image by dragging a camera view, constrained to image bounds.

    All positions are in the same (Qt logical) coordinate system. The result
    is an *absolute* normalized image centre computed from the drag origin.
    """
    factor = max(1.0, float(zoom))
    margin = 0.5 / factor
    width = max(1.0, float(viewport[0]))
    height = max(1.0, float(viewport[1]))
    dx = float(current[0]) - float(origin[0])
    dy = float(current[1]) - float(origin[1])
    cx = float(center[0]) - dx / (width * factor)
    cy = float(center[1]) - dy / (height * factor)
    return (max(margin, min(1.0 - margin, cx)),
            max(margin, min(1.0 - margin, cy)))
