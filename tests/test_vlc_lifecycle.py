import sys

from relayview.vlc_backend import VLCPlayer


class FakeNativePlayer:
    def __init__(self):
        self.calls = []

    def set_hwnd(self, value):
        self.calls.append(("detach", value))

    def set_nsobject(self, value):
        self.calls.append(("detach", value))

    def set_xwindow(self, value):
        self.calls.append(("detach", value))

    def stop(self):
        self.calls.append(("stop", None))

    def set_media(self, value):
        self.calls.append(("media", value))

    def release(self):
        self.calls.append(("release", None))


def make_player():
    wrapper = VLCPlayer.__new__(VLCPlayer)
    wrapper.player = FakeNativePlayer()
    wrapper._attached_handle = 12345
    return wrapper


def test_stop_detaches_before_native_stop():
    wrapper = make_player()
    wrapper.stop(detach=True)
    assert wrapper.player.calls[0] == ("detach", 0)
    assert wrapper.player.calls[1] == ("stop", None)
    assert wrapper._attached_handle is None


def test_release_orders_detach_stop_clear_release():
    wrapper = make_player()
    wrapper.release()
    assert wrapper.player.calls == [
        ("detach", 0),
        ("stop", None),
        ("media", None),
        ("release", None),
    ]
