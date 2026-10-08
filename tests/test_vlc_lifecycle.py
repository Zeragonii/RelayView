import time
from relayview.vlc_backend import VLCPlayer


def await_reap(proc):
    deadline = time.monotonic() + 2
    while not proc.terminated and time.monotonic() < deadline:
        time.sleep(0.005)
    assert proc.terminated


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
    from collections import deque
    player._events = deque(maxlen=128)
    player._generation = 1
    player._last_event = time.monotonic()
    player._starting_at = time.monotonic()
    player._retry_at = 0.0
    player._failures = 0
    player._reported_state = "Playing"
    player._enabled = True
    return player


def test_stop_terminates_worker_instead_of_native_vlc_stop():
    wrapper = make_player()
    proc = wrapper._process
    wrapper.stop(detach=True)
    await_reap(proc)
    assert wrapper._process is None
    assert wrapper._attached_handle is None


def test_release_is_idempotent_after_worker_termination():
    wrapper = make_player()
    proc = wrapper._process
    wrapper.release()
    wrapper.release()
    await_reap(proc)
    assert wrapper._process is None


def test_unexpected_worker_exit_is_detected():
    messages = []
    wrapper = make_player()
    wrapper._status_callback = messages.append
    wrapper._process.returncode = 17
    assert wrapper.check_health() is False
    assert wrapper._process is None
    assert messages == ["Worker exited (17) — retry in 1s"]
    assert wrapper.check_health() is False


def test_termination_does_not_wait_for_slow_process():
    import threading

    class SlowProcess(FakeProcess):
        def __init__(self):
            super().__init__()
            self.gate = threading.Event()

        def wait(self, timeout=None):
            self.gate.wait(timeout=0.25)
            return self.returncode

    wrapper = make_player()
    proc = SlowProcess()
    wrapper._process = proc
    start = time.monotonic()
    wrapper.terminate()
    assert time.monotonic() - start < 0.15
    assert wrapper._process is None
    proc.gate.set()
    await_reap(proc)


def test_worker_playing_event_resets_failure_count():
    wrapper = make_player()
    wrapper._failures = 3
    received = []
    wrapper._status_callback = received.append
    wrapper._events.append((wrapper._generation, {"event": "state", "value": "Playing"}, time.monotonic()))
    assert wrapper.check_health()
    assert wrapper._failures == 0
    assert received == []  # already Playing


def test_stale_worker_event_is_discarded():
    wrapper = make_player()
    wrapper._events.append((wrapper._generation - 1, {"event": "state", "value": "Error"}, time.monotonic()))
    assert wrapper.check_health()
    assert wrapper._process is not None


def test_error_event_schedules_recovery():
    wrapper = make_player()
    previous = wrapper._process
    wrapper._events.append((wrapper._generation, {"event": "state", "value": "Error"}, time.monotonic()))
    assert not wrapper.check_health()
    assert wrapper._process is None
    assert wrapper._retry_at > time.monotonic()
    await_reap(previous)


def test_manual_stop_disables_reconnection():
    wrapper = make_player()
    wrapper.stop()
    assert wrapper._enabled is False
    assert wrapper.check_health() is True
