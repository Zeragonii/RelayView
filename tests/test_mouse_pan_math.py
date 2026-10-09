"""Pan dragging is independent of the mouse hook, window or playback engine."""
import pytest
from relayview.mouse_pan import anchored_pan_center
from relayview.mpv_native import view_properties


def test_horizontal_middle_drag_moves_image_without_recentering():
    center = (0.5, 0.5)
    assert anchored_pan_center((100, 100), (300, 100), center, 2, (800, 400)) == pytest.approx((.375, .5))
    assert anchored_pan_center((100, 100), (500, 100), center, 2, (800, 400)) == pytest.approx((.25, .5))
    assert anchored_pan_center((100, 100), (500, 100), center, 2, (800, 400)) == pytest.approx((.25, .5))


def test_vertical_drag_is_bounded_and_reverse_is_reversible():
    start = (.35, .65)
    assert anchored_pan_center((200, 200), (200, -150), start, 3, (800, 500))[1] == pytest.approx(5/6)
    assert anchored_pan_center((200, 200), (200, 200), start, 3, (800, 500)) == pytest.approx(start)
    assert anchored_pan_center((200, 200), (-9000, 9000), start, 3, (800, 500)) == pytest.approx((5/6, 1/6))


def test_middle_drag_changes_native_mpv_alignment():
    zoom = 3.0
    original = view_properties(zoom, .5, .5)
    cx, cy = anchored_pan_center((0, 0), (300, 60), (.5, .5), zoom, (800, 400))
    moved = view_properties(zoom, cx, cy)
    assert moved['video-align-x'] != original['video-align-x']
    assert moved['video-align-y'] != original['video-align-y']
    assert moved['video-zoom'] == original['video-zoom']


def test_unzoomed_pan_is_fixed_at_centre():
    assert anchored_pan_center((0, 0), (500, -500), (.5,.5), 1, (800, 600)) == (.5,.5)
