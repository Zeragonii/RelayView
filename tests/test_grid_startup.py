"""Prevent launch regressions caused by early Qt native QWidget events.

Qt-based smoke tests run on the Windows packaging job, after dependencies are
installed. A standalone event-filter test also runs in Linux/pytest-only CI.
"""
import ast
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GRID_SOURCE = ROOT / "relayview" / "grid_view.py"


def _filter_method_without_qt():
    """Load the *real* GridTile.eventFilter method under a minimal Qt mock."""
    tree = ast.parse(GRID_SOURCE.read_text(encoding="utf-8"))
    grid_tile = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "GridTile")
    method = next(node for node in grid_tile.body if isinstance(node, ast.FunctionDef) and node.name == "eventFilter")
    # The original source has a `QFrame` base; reuse it with a tiny Python stub.
    bare_class = ast.ClassDef(name="GridTile", bases=[ast.Name(id="QFrame", ctx=ast.Load())],
                              keywords=[], body=[method], decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[bare_class], type_ignores=[]))

    class QFrame:
        def eventFilter(self, obj, event):
            return False

    class _EventTypes:
        Resize = 1
        Wheel = 2

    class QEvent:
        Type = _EventTypes

    scope = {"QFrame": QFrame, "QEvent": QEvent, "sys": sys}
    exec(compile(module, str(GRID_SOURCE), "exec"), scope)
    return scope["GridTile"]


def test_event_filter_is_safe_before_video_widget_exists():
    """Reproduces the exact traceback: resize runs before `self.video` exists."""
    GridTile = _filter_method_without_qt()
    tile = GridTile()
    viewport = object()
    tile.zoom_by = lambda *args: pytest.fail("zoom called without video")

    class Event:
        def __init__(self, kind):
            self.kind = kind
        def type(self):
            return self.kind

    assert tile.eventFilter(viewport, Event(1)) is False
    assert tile.eventFilter(viewport, Event(2)) is False


def test_event_filter_is_installed_after_video_widget_creation():
    """Avoid future regressions from prematurely installing the native filter."""
    source = GRID_SOURCE.read_text(encoding="utf-8")
    assert source.index('self.video = QFrame(objectName="gridVideo")') < source.index('self.video.installEventFilter(self)')


def test_grid_constructs_and_resizes_in_real_qt():
    """Actually construct four GridTiles and process Qt resize events."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtWidgets", reason="PySide6 unavailable in lightweight test environment")
    from PySide6.QtWidgets import QApplication
    from relayview.grid_view import GridView

    app = QApplication.instance() or QApplication([])
    widget = GridView(None)
    try:
        assert len(widget.tiles) == 4
        widget.resize(800, 500)
        widget.show()
        app.processEvents()
        for tile in widget.tiles:
            assert tile.video is not None
            assert tile.video.parentWidget() is tile
            assert tile.video.width() > 0 and tile.video.height() > 0
        widget.configure(2, 1, [])
        app.processEvents()
        assert len(widget.tiles) == 2
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()
