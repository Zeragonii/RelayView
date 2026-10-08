"""Regression guard for Qt footer input handling (works without PySide6 installed)."""
from pathlib import Path

def test_zoom_footer_accepts_mouse_input():
    source = (Path(__file__).parents[1] / "relayview" / "grid_view.py").read_text()
    assert "footer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)" in source
    assert "footer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)" not in source

def test_zoom_buttons_connect_to_zoom_by():
    source = (Path(__file__).parents[1] / "relayview" / "grid_view.py").read_text()
    assert "self.zoom_in_button.clicked.connect(lambda: self.zoom_by(1))" in source
    assert "self.zoom_out_button.clicked.connect(lambda: self.zoom_by(-1))" in source
    assert "tile.zoom_changed.connect(self._update_tile_zoom)" in source
