"""Wheel and middle-button bridge migration guards."""
from pathlib import Path
from relayview.windows_mouse_bridge import wheel_steps


def test_wheel_delta_sign_and_precision():
    assert wheel_steps(120) == 1
    assert wheel_steps(-120) == -1
    assert wheel_steps(240) == 2
    assert wheel_steps(0) == 0


def test_middle_button_polls_physical_state_not_low_level_mouse_events():
    root = Path(__file__).parents[1] / 'relayview'
    source = (root / 'grid_view.py').read_text()
    mouse = (root / 'windows_mouse_bridge.py').read_text()
    assert 'self._native_mouse = WindowsMouseBridge(self)' in source
    assert 'GetAsyncKeyState(VK_MBUTTON)' in mouse
    assert 'self._pan_timer.timeout.connect(self._poll_pan)' in mouse
    assert 'self._pan_timer.setInterval(25)' in mouse
    assert 'tile.video.rect().contains(local)' in mouse
    assert 'WM_MBUTTONDOWN' not in mouse
    assert 'wparam == WM_MOUSEWHEEL' in mouse
    assert 'app.aboutToQuit.connect(self.close)' in mouse


def test_middle_drag_defers_mpv_commands_to_normal_qt_event_loop():
    source = (Path(__file__).parents[1] / 'relayview' / 'windows_mouse_bridge.py').read_text()
    assert 'self._apply_pan(self._pan_tile, pos)' in source
    assert 'tile._update_zoom()' in source
    assert 'Middle pan update' in source


def test_qt_middle_drag_is_disabled_on_windows_to_avoid_competing_pan():
    grid = (Path(__file__).parents[1] / 'relayview' / 'grid_view.py').read_text()
    assert 'if (event.buttons() & Qt.MouseButton.MiddleButton) and not sys.platform.startswith("win"):' in grid
