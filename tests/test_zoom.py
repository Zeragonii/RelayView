from relayview.zoom import ZoomState


def test_zoom_bounds_and_reset():
    state = ZoomState()
    state.change(100)
    assert state.factor == 5
    state.change(-100)
    assert state.factor == 1
    assert state.crop(1920, 1080) is None


def test_crop_center():
    state = ZoomState(2)
    assert state.crop(1920, 1080) == "960x540+480+270"


def test_pan_clamped_to_video():
    state = ZoomState(2)
    state.move(100, 100)
    assert state.crop(1920, 1080) == "960x540+960+540"
    state.move(-100, -100)
    assert state.crop(1920, 1080) == "960x540+0+0"


def test_invalid_dimensions():
    assert ZoomState(2).crop(0, 1080) is None
