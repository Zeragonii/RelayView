"""Geometry/regression checks for viewport-based zoom; requires no Qt runtime."""
from pathlib import Path
import pytest
from relayview.zoom import ZoomState, viewport_geometry


def test_unzoomed_video_exactly_fills_viewport():
    assert viewport_geometry(ZoomState(), 640, 360) == (0, 0, 640, 360)


def test_zoomed_center_expands_behind_clipped_viewport():
    assert viewport_geometry(ZoomState(2.0), 640, 360) == (-320, -180, 1280, 720)
    assert viewport_geometry(ZoomState(3.0), 400, 250) == (-400, -250, 1200, 750)


@pytest.mark.parametrize('cx,cy,expected', [
    (0.25, 0.25, (0, 0, 1280, 720)),
    (0.75, 0.75, (-640, -360, 1280, 720)),
    (0.25, 0.75, (0, -360, 1280, 720)),
])
def test_panning_moves_only_child_window(cx, cy, expected):
    assert viewport_geometry(ZoomState(2.0, cx, cy), 640, 360) == expected


def test_extreme_pan_cannot_expose_blank_edges():
    for factor in (1.0, 1.25, 2.0, 3.0, 5.0):
        for cx, cy in ((0, 0), (1, 1), (-999, 999), (.5, .5)):
            left, top, width, height = viewport_geometry(ZoomState(factor, cx, cy), 641, 361)
            assert left <= 0 and top <= 0
            assert left + width >= 641 and top + height >= 361


def test_pan_at_fixed_zoom_does_not_resize_child():
    a = viewport_geometry(ZoomState(4, 0.5, 0.5), 800, 600)
    b = viewport_geometry(ZoomState(4, 0.6, 0.4), 800, 600)
    assert a[:2] != b[:2]
    assert a[2:] == b[2:]


def test_vlc_workers_do_not_receive_interactive_crop_commands():
    ui = (Path(__file__).parents[1] / 'relayview' / 'grid_view.py').read_text()
    assert 'tile.player.set_zoom(' not in ui
    worker = (Path(__file__).parents[1] / 'relayview' / 'player_worker.py').read_text()
    assert 'video_set_crop_geometry' not in worker
    assert 'elif command == "zoom"' not in worker
    assert 'self.video = QFrame(self.video_viewport, objectName="gridVideo")' in ui
    assert 'self.video_viewport.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)' in ui
    assert 'self.video.move(left, top)' in ui
    assert 'self.video.resize(width, height)' in ui


def test_native_event_capture_remains_within_viewport():
    source = (Path(__file__).parents[1] / 'relayview' / 'windows_mouse_bridge.py').read_text()
    assert 'tile.video_viewport.mapFromGlobal(global_pos)' in source
    assert 'tile.video_viewport.rect().contains(local)' in source
