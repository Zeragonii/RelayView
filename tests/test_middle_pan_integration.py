"""Exercise the actual Windows polling implementation with deterministic fakes.

No Windows API or PySide6 installation is needed to verify that a middle press,
mouse movement, and release update the camera's normalized pan state.
"""
import ast
from pathlib import Path

import pytest

from relayview.mouse_pan import anchored_pan_center


SOURCE = Path(__file__).parents[1] / 'relayview' / 'windows_mouse_bridge.py'


class Point:
    def __init__(self, x, y):
        self._x, self._y = x, y

    def x(self):
        return self._x

    def y(self):
        return self._y


class Logger:
    def info(self, *args):
        pass

    def debug(self, *args):
        pass

    def exception(self, *args):
        pytest.fail('Unexpected exception inside Windows pan poll')


def _load_real_poll_methods(cursor):
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    win = next(node for node in tree.body if isinstance(node, ast.If)
               and any(isinstance(x, ast.ClassDef) and x.name == 'WindowsMouseBridge' for x in node.body))
    win_class = next(x for x in win.body if isinstance(x, ast.ClassDef) and x.name == 'WindowsMouseBridge')
    methods = [x for x in win_class.body if isinstance(x, ast.FunctionDef)
               and x.name in ('_poll_pan', '_apply_pan', '_clear_pan')]
    klass = ast.ClassDef(name='RealPanPoll', bases=[], keywords=[], body=methods, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[klass], type_ignores=[]))

    class FakeCursor:
        @staticmethod
        def pos():
            return cursor[0]

    scope = {
        'QCursor': FakeCursor,
        'VK_MBUTTON': 0x04,
        'anchored_pan_center': anchored_pan_center,
        'log': Logger(),
    }
    exec(compile(module, str(SOURCE), 'exec'), scope)
    return scope['RealPanPoll']


def test_actual_middle_pan_poll_starts_moves_and_stays_after_release():
    cursor = [Point(100, 100)]
    pressed = [True]
    Bridge = _load_real_poll_methods(cursor)

    class Native:
        def GetAsyncKeyState(self, vk):
            assert vk == 4
            return 0x8000 if pressed[0] else 0

    class Zoom:
        factor = 2
        cx = 0.5
        cy = 0.5

    class Video:
        def width(self):
            return 800

        def height(self):
            return 400

    class Tile:
        zoom = Zoom()
        video = Video()
        stream = object()
        index = 1

        def __init__(self):
            self.sent = []

        def isVisible(self):
            return True

        def _update_zoom(self):
            self.sent.append((self.zoom.cx, self.zoom.cy))

    tile = Tile()
    bridge = Bridge()
    bridge._user32 = Native()
    bridge._pan_tile = bridge._pan_origin = bridge._pan_center = None
    bridge.grid = type('Grid', (), {'tiles': [tile]})()
    bridge._active = lambda: True
    bridge._tile_at = lambda _: tile

    bridge._poll_pan()  # press/anchor
    assert bridge._pan_tile is tile
    assert not tile.sent

    cursor[0] = Point(300, 140)
    bridge._poll_pan()
    assert tile.sent[-1] == pytest.approx((.375, .45))

    cursor[0] = Point(500, 140)
    bridge._poll_pan()
    assert tile.sent[-1] == pytest.approx((.25, .45))

    pressed[0] = False
    bridge._poll_pan()  # release, with position retained
    assert bridge._pan_tile is None
    assert (tile.zoom.cx, tile.zoom.cy) == pytest.approx((.25, .45))
    assert len(tile.sent) == 2


def test_poll_ignores_middle_button_if_not_zoomed():
    cursor = [Point(20, 20)]
    Bridge = _load_real_poll_methods(cursor)
    bridge = Bridge()
    bridge._pan_tile = bridge._pan_origin = bridge._pan_center = None
    bridge._user32 = type('Native', (), {'GetAsyncKeyState': lambda self, _: 0x8000})()
    bridge._active = lambda: True
    tile = type('Tile', (), {'zoom': type('Zoom', (), {'factor': 1.0})()})()
    bridge._tile_at = lambda _: tile
    bridge._poll_pan()
    assert bridge._pan_tile is None
