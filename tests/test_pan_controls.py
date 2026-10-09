"""Manual fallback is wired into the *real* Qt tile and native property path."""
from pathlib import Path


def test_manual_pan_ui_dispatch_and_visibility():
    s = (Path(__file__).parents[1] / 'relayview' / 'grid_view.py').read_text()
    assert 'self.pan_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)' in s
    assert 'self.pan_button.setVisible(self.zoom.factor > 1)' in s
    assert 'pan_menu.addAction("Pan left", lambda: self.pan_by(-0.2, 0))' in s
    assert 'pan_menu.addAction("Pan right", lambda: self.pan_by(0.2, 0))' in s
    assert 'self.player.set_zoom(' in s


def test_real_qt_tile_manual_pan_dispatch():
    import os
    import pytest
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    pytest.importorskip('PySide6.QtWidgets')
    from PySide6.QtWidgets import QApplication
    from relayview.grid_view import GridTile
    from relayview.models import Stream

    app = QApplication.instance() or QApplication([])
    tile = GridTile(0)
    try:
        tile.set_stream_label(Stream('Test camera', 'rtsp://127.0.0.1/test'))
        observed = []
        tile.player = type('FakePlayer', (), {
            'set_zoom': lambda self, factor, cx, cy: observed.append((factor, cx, cy))
        })()
        tile.zoom_by(8)  # 3x
        assert tile.pan_button.isVisible() is False  # Parent intentionally hidden
        tile.pan_by(0.2, 0)
        assert observed[-1][0] == 3
        assert observed[-1][1] > 0.5
        tile.reset_pan()
        assert observed[-1][1:] == (0.5, 0.5)
    finally:
        tile.close()
        tile.deleteLater()
        app.processEvents()
