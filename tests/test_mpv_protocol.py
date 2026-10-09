"""Actual worker command handler with an injected native-client double."""
from __future__ import annotations

import io
import json
import sys

import relayview.player_worker as worker


class FakeNative:
    def __init__(self):
        self.initialized = False
        self.calls = []

    def initialize(self, hwnd):
        self.calls.append(('initialize', hwnd))
        self.initialized = True

    def property(self, key, value):
        self.calls.append(('property', key, value))

    def command(self, *args):
        self.calls.append(('command', args[0], '<redacted>'))


def test_worker_applies_view_and_volume_to_native_player(monkeypatch):
    fake = FakeNative()
    monkeypatch.setattr(worker, 'MpvClient', lambda: fake)
    monkeypatch.setattr(worker, '_worker_log', lambda _: None)
    commands = [
        {'command': 'attach', 'hwnd': 12345},
        {'command': 'zoom', 'factor': 3, 'cx': .35, 'cy': .65},
        {'command': 'volume', 'value': 37},
        {'command': 'mute', 'value': True},
        {'command': 'play', 'url': 'rtsp://user:secret@localhost/cam'},
        {'command': 'pause', 'value': True},
    ]
    monkeypatch.setattr(sys, 'stdin', io.StringIO(''.join(json.dumps(x)+'\n' for x in commands)))
    output = io.StringIO()
    monkeypatch.setattr(sys, 'stdout', output)
    assert worker.run_worker() == 0
    events = [json.loads(x) for x in output.getvalue().splitlines()]
    assert any(x['event'] == 'ready' for x in events)
    assert any(x['event'] == 'view' and x['factor'] == 3 for x in events)
    assert ('initialize', 12345) in fake.calls
    assert ('property', 'volume', 37) in fake.calls
    assert ('property', 'mute', True) in fake.calls
    assert ('property', 'pause', True) in fake.calls
    assert any(x[:2] == ('property', 'video-zoom') for x in fake.calls)
    assert any(x[:2] == ('property', 'video-align-x') for x in fake.calls)
    assert any(x[:2] == ('property', 'video-align-y') for x in fake.calls)
    assert not ('user:secret' in output.getvalue())


def test_worker_rejects_new_hwnd_after_initializing(monkeypatch):
    fake = FakeNative()
    monkeypatch.setattr(worker, 'MpvClient', lambda: fake)
    monkeypatch.setattr(worker, '_worker_log', lambda _: None)
    messages = [
        {'command': 'attach', 'hwnd': 123},
        {'command': 'play', 'url': 'rtsp://example.local/cam'},
        {'command': 'attach', 'hwnd': 456},
    ]
    monkeypatch.setattr(sys, 'stdin', io.StringIO(''.join(json.dumps(x)+'\n' for x in messages)))
    buffer = io.StringIO()
    monkeypatch.setattr(sys, 'stdout', buffer)
    assert worker.run_worker() == 0
    assert any(x.get('event') == 'command_error' and x.get('command') == 'attach'
               for x in map(json.loads, buffer.getvalue().splitlines()))
