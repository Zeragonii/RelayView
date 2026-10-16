"""Regression tests for Windows/DPI wheel capture without a Windows runner.

The real hook methods are extracted from the source, and the Windows/Qt
interfaces are replaced with deterministic fakes. This deliberately catches
performing expensive playback work inside a WH_MOUSE_LL callback and mixing
Windows physical pixels with Qt's device-independent coordinates.
"""
import ast
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).parents[1] / 'relayview' / 'windows_mouse_bridge.py'


def _load_real_wheel_methods(fake_cursor, scheduled):
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    win = next(node for node in tree.body if isinstance(node, ast.If)
               and any(isinstance(x, ast.ClassDef) and x.name == 'WindowsMouseBridge' for x in node.body))
    bridge = next(x for x in win.body if isinstance(x, ast.ClassDef) and x.name == 'WindowsMouseBridge')
    methods = [x for x in bridge.body if isinstance(x, ast.FunctionDef)
               and x.name in ('_callback', '_dispatch_wheels', '_valid_target', '_tile_at')]
    new_class = ast.ClassDef(name='TestableBridge', bases=[], keywords=[], body=methods, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[new_class], type_ignores=[]))

    class FakeCTypes:
        @staticmethod
        def POINTER(struct):
            return struct

        @staticmethod
        def cast(event, _pointer):
            return SimpleNamespace(contents=event)

        @staticmethod
        def c_short(value):
            return SimpleNamespace(value=(value & 0xffff) - 65536 if value & 0x8000 else value & 0xffff)

    class FakeQCursor:
        @staticmethod
        def pos():
            return fake_cursor

    class FakeQTimer:
        @staticmethod
        def singleShot(delay, callback):
            assert delay == 0
            scheduled.append(callback)

    class FakeLog:
        def info(self, *_args):
            pass

        def exception(self, *_args):
            raise AssertionError('Unexpected wheel-hook exception')

    scope = {'ctypes': FakeCTypes, '_MSLLHOOKSTRUCT': object,
             'QCursor': FakeQCursor, 'QTimer': FakeQTimer,
             'WM_MOUSEWHEEL': 0x020A, 'log': FakeLog()}
    exec(compile(module, str(SOURCE), 'exec'), scope)
    return scope['TestableBridge']


def test_wheel_uses_qt_coordinates_and_deferred_dispatch():
    # At 200% Windows scaling, raw Windows pixels differ from Qt coordinates.
    qt_cursor_position = object()
    scheduled = []
    Bridge = _load_real_wheel_methods(qt_cursor_position, scheduled)
    zoom_calls = []
    tile = SimpleNamespace(index=2, stream=object(),
                           isVisible=lambda: True,
                           zoom_by=lambda steps: zoom_calls.append(steps))
    bridge = Bridge()
    bridge._active = lambda: True
    bridge._tile_at = lambda position: tile if position is qt_cursor_position else None
    bridge.grid = SimpleNamespace(tiles=[tile])
    bridge.single_target = None
    bridge._wheel_remainder = 0
    bridge._pending_wheels = []
    bridge._wheel_dispatch_scheduled = False
    bridge._hook = 'hook'
    bridge._user32 = SimpleNamespace(CallNextHookEx=lambda *args: 0)

    # Physical point is intentionally different from logical cursor position.
    event = SimpleNamespace(pt=SimpleNamespace(x=240, y=240), mouseData=120 << 16)
    assert bridge._callback(0, 0x020A, event) == 1
    assert zoom_calls == []  # playback work must never run in the hook
    assert len(scheduled) == 1
    scheduled.pop()()
    assert zoom_calls == [1]
    assert not bridge._wheel_dispatch_scheduled


def test_wheel_forwards_when_not_over_camera():
    scheduled = []
    Bridge = _load_real_wheel_methods(object(), scheduled)
    bridge = Bridge()
    bridge._active = lambda: True
    bridge._tile_at = lambda pos: None
    bridge._hook = 'hook'
    calls = []
    bridge._user32 = SimpleNamespace(CallNextHookEx=lambda *args: calls.append(args) or 42)
    bridge._wheel_remainder = 0
    assert bridge._callback(0, 0x020A, object()) == 42
    assert len(calls) == 1
    assert not scheduled


def test_qt_fallback_is_available_on_windows():
    source = (SOURCE.parent / 'grid_view.py').read_text(encoding='utf-8')
    assert 'obj is getattr(self, "video", None) and event.type() == QEvent.Type.Wheel:' in source
    assert 'event.accept()' in source
    assert 'and not sys.platform.startswith("win")):' not in source.split('def eventFilter')[1].split('def wheelEvent')[0]


def test_native_wheel_zoom_routes_to_single_camera_when_grid_hidden():
    """Real wheel callback + queued dispatch with a registered primary target."""
    cursor = object()
    scheduled = []
    Bridge = _load_real_wheel_methods(cursor, scheduled)
    zoom_calls = []
    single = SimpleNamespace(index=-1, stream=object(),
                             isVisible=lambda: True,
                             zoom_by=lambda steps: zoom_calls.append(steps))
    bridge = Bridge()
    bridge.grid = SimpleNamespace(tiles=[], isVisible=lambda: False)
    bridge.single_target = single
    bridge._active = lambda: True
    bridge._tile_at = lambda pos: single if pos is cursor else None
    bridge._wheel_remainder = 0
    bridge._pending_wheels = []
    bridge._wheel_dispatch_scheduled = False
    bridge._hook = "hook"
    bridge._user32 = SimpleNamespace(CallNextHookEx=lambda *args: 0)

    assert bridge._callback(0, 0x020A, SimpleNamespace(mouseData=120 << 16)) == 1
    assert not zoom_calls
    scheduled.pop()()
    assert zoom_calls == [1]


def test_native_hit_testing_selects_only_visible_view_and_checks_video_rect():
    Bridge = _load_real_wheel_methods(object(), [])
    class Rect:
        def contains(self, pos):
            return pos == "inside"
    video = SimpleNamespace(isVisible=lambda: True,
                            mapFromGlobal=lambda pos: pos,
                            rect=lambda: Rect())
    single = SimpleNamespace(stream=object(), video=video,
                             isVisible=lambda: True)
    tile = SimpleNamespace(stream=object(), video=video,
                           isVisible=lambda: True)
    bridge = Bridge()
    state = [False]
    bridge.grid = SimpleNamespace(tiles=[tile], isVisible=lambda: state[0])
    bridge.single_target = single

    assert bridge._tile_at("inside") is single
    assert bridge._tile_at("outside") is None
    state[0] = True
    assert bridge._tile_at("inside") is tile


def test_single_view_wheel_fallback_registered_on_native_video_frame():
    source = (SOURCE.parent / "main_window.py").read_text(encoding="utf-8")
    assert 'self.grid_view._native_mouse.set_single_view_target(self.single_zoom)' in source
    assert 'event.type() == QEvent.Type.Wheel and self.single_zoom.stream' in source
    assert 'self.single_zoom.zoom_by(1 if delta > 0 else -1)' in source
