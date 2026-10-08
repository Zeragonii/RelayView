from pathlib import Path
from relayview.windows_mouse_bridge import wheel_steps


def test_wheel_delta_sign_and_precision():
    assert wheel_steps(120) == 1
    assert wheel_steps(-120) == -1
    assert wheel_steps(240) == 2
    assert wheel_steps(0) == 0


def test_bridge_connected_to_grid_and_scoped_to_video():
    root = Path(__file__).parents[1] / 'relayview'
    source = (root / 'grid_view.py').read_text()
    mouse = (root / 'windows_mouse_bridge.py').read_text()
    assert 'self._native_mouse = WindowsMouseBridge(self)' in source
    assert 'tile.video.rect().contains(local)' in mouse
    assert 'WM_MOUSEWHEEL' in mouse and 'WM_MBUTTONDOWN' in mouse
    assert 'app.aboutToQuit.connect(self.close)' in mouse
