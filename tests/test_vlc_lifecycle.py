from relayview.vlc_backend import VLCPlayer


class FakeProcess:
    def __init__(self):
        self.pid = 1234
        self.returncode = None
        self.terminated = False
        self.killed = False
        self.stdin = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def make_player():
    player = VLCPlayer.__new__(VLCPlayer)
    player._process = FakeProcess()
    player._attached_handle = 12345
    player._current_url = "rtsp://example"
    player._volume = 100
    player._muted = False
    player._paused = False
    player._lock = __import__('threading').Lock()
    player._status_callback = lambda _: None
    return player


def test_stop_terminates_worker_instead_of_native_vlc_stop():
    wrapper = make_player()
    proc = wrapper._process
    wrapper.stop(detach=True)
    assert proc.terminated is True
    assert wrapper._process is None
    assert wrapper._attached_handle is None


def test_release_is_idempotent_after_worker_termination():
    wrapper = make_player()
    proc = wrapper._process
    wrapper.release()
    wrapper.release()
    assert proc.terminated is True
    assert wrapper._process is None
