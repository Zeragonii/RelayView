"""Native mpv zoom/alignment math and fixed window regression tests."""
import math
from pathlib import Path
import pytest
from relayview.mpv_native import view_properties


@pytest.mark.parametrize('factor,expected', [(1, 0), (1.25, math.log2(1.25)), (2, 1), (4, 2), (5, math.log2(5))])
def test_mpv_native_zoom(factor, expected):
    view = view_properties(factor, 0.5, 0.5)
    assert view['video-zoom'] == pytest.approx(expected)
    assert view['video-align-x'] == 0
    assert view['video-align-y'] == 0


def test_native_alignment_reaches_all_bounds():
    view = view_properties(2, .25, .75)
    assert view['video-align-x'] == pytest.approx(-1)
    assert view['video-align-y'] == pytest.approx(1)


def test_unzoomed_alignment_recenters():
    assert view_properties(1, .99, .01) == dict.fromkeys(('video-zoom','video-align-x','video-align-y'), 0.0)


def test_clamped_overshoot():
    assert view_properties(3, -50, 50)['video-align-x'] == -1
    assert view_properties(3, -50, 50)['video-align-y'] == 1


def test_uses_fixed_native_qt_window_not_viewport_geometry():
    root = Path(__file__).parents[1] / 'relayview'
    ui = (root / 'grid_view.py').read_text()
    worker = (root / 'player_worker.py').read_text()
    assert 'self.video = QFrame(objectName="gridVideo")' in ui
    assert 'video_viewport' not in ui
    assert 'self.video.resize(' not in ui
    assert 'self.video.move(' not in ui
    assert 'self.player.set_zoom(' in ui
    assert 'elif command == "zoom":' in worker
    assert 'video_set_crop_geometry' not in worker
    assert 'video-align-x' in (root / 'mpv_native.py').read_text()


def test_native_event_capture_uses_fixed_video():
    bridge = (Path(__file__).parents[1] / 'relayview' / 'windows_mouse_bridge.py').read_text()
    assert 'tile.video.mapFromGlobal(global_pos)' in bridge
    assert 'tile.video.rect().contains(local)' in bridge
