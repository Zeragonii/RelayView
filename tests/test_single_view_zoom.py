"""Single-camera wheel/pan zoom adapter contract independent of Qt and Windows."""
from types import SimpleNamespace

from relayview.single_view_zoom import SingleViewZoom


def test_single_view_zoom_updates_primary_player_and_clamps():
    updates = []
    video = SimpleNamespace(isVisible=lambda: True)
    active = [True]
    stream = [object()]
    player = SimpleNamespace(set_zoom=lambda *args: updates.append(args))
    controller = SingleViewZoom(video, player, lambda: stream[0], lambda: active[0])
    assert controller.isVisible()
    controller.zoom_by(1)
    assert updates[-1] == (1.25, 0.5, 0.5)
    controller.zoom_by(100)
    assert updates[-1] == (5.0, 0.5, 0.5)
    controller.zoom_by(-100)
    assert updates[-1] == (1.0, 0.5, 0.5)
    controller.zoom_by(-1)
    assert updates[-1] == (1.0, 0.5, 0.5)
    assert len(updates) == 3


def test_single_view_only_zooms_while_selected_camera_active():
    updates = []
    active = [False]
    stream = [object()]
    video = SimpleNamespace(isVisible=lambda: True)
    player = SimpleNamespace(set_zoom=lambda *args: updates.append(args))
    controller = SingleViewZoom(video, player, lambda: stream[0], lambda: active[0])
    controller.zoom_by(1)
    assert not updates
    assert not controller.isVisible()
    active[0] = True
    stream[0] = None
    controller.zoom_by(1)
    assert not updates
    stream[0] = object()
    controller.zoom_by(1)
    assert updates[-1] == (1.25, 0.5, 0.5)
    controller.reset_zoom()
    assert updates[-1] == (1.0, 0.5, 0.5)


def test_reset_restores_pan_and_zoom_for_new_camera():
    values = []
    controller = SingleViewZoom(SimpleNamespace(isVisible=lambda: True),
                                SimpleNamespace(set_zoom=lambda *args: values.append(args)),
                                lambda: object(), lambda: True)
    controller.zoom_by(4)
    controller.zoom.cx, controller.zoom.cy = .65, .4
    controller._update_zoom()
    assert values[-1] == (2.0, .65, .4)
    controller.reset_zoom()
    assert values[-1] == (1.0, .5, .5)
