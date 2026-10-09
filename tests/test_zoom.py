from relayview.zoom import ZoomState


def test_zoom_bounds_and_reset():
    state = ZoomState()
    state.change(100)
    assert state.factor == 5
    state.change(-100)
    assert state.factor == 1
    state.reset()
    assert (state.factor, state.cx, state.cy) == (1, .5, .5)


def test_pan_bounds():
    state = ZoomState(2)
    state.move(100, 100)
    assert (state.cx, state.cy) == (.75, .75)
    state.move(-100, -100)
    assert (state.cx, state.cy) == (.25, .25)


def test_pan_clamps_after_zoom_change():
    state = ZoomState(5, .1, .9)
    state.change(-12)  # 5x -> 2x
    assert (state.cx, state.cy) == (.25, .75)
