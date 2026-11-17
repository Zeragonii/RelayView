from pathlib import Path

import pytest

QtWidgets = pytest.importorskip("PySide6.QtWidgets")
QtCore = pytest.importorskip("PySide6.QtCore")
QtTest = pytest.importorskip("PySide6.QtTest")

from relayview.models import Stream
from relayview.playlist import load_m3u, save_m3u
from relayview.playlist_editor import PlaylistEditorDialog


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_add_camera_then_save_and_reload(app, tmp_path):
    path = tmp_path / "cameras.m3u"
    save_m3u(path, [Stream(name="Existing", url="rtsp://localhost/existing")])
    dialog = PlaylistEditorDialog(str(path), load_m3u(path))
    dialog.add_button.click()
    assert len(dialog.streams) == 2
    assert dialog.list_widget.currentRow() == 1
    QtTest.QTest.keyClicks(dialog.name_edit, "New Camera")
    QtTest.QTest.keyClicks(dialog.url_edit, "rtsp://localhost/new")
    dialog.group_edit.setFocus()
    QtTest.QTest.keyClicks(dialog.group_edit, "Outside")
    assert dialog._validate()
    dialog._save()
    saved = load_m3u(path)
    assert [s.name for s in saved] == ["Existing", "New Camera"]
    assert saved[1].url == "rtsp://localhost/new"
    assert saved[1].group == "Outside"
    dialog.deleteLater()


def test_remove_camera_and_discard_without_writing(app, tmp_path):
    path = tmp_path / "cameras.m3u"
    original = [Stream("A", "rtsp://localhost/a"), Stream("B", "rtsp://localhost/b")]
    save_m3u(path, original)
    previous_bytes = path.read_bytes()
    dialog = PlaylistEditorDialog(str(path), original)
    dialog.list_widget.setCurrentRow(0)
    dialog.remove_button.click()
    assert [s.name for s in dialog.streams] == ["B"]
    dialog.reject()
    assert path.read_bytes() == previous_bytes
    dialog.deleteLater()


def test_duplicate_url_order_uses_stable_id(app, tmp_path):
    shared = "rtsp://localhost/shared"
    dialog = PlaylistEditorDialog(str(tmp_path / "cams.m3u"), [
        Stream("First", shared), Stream("Second", shared), Stream("Third", "rtsp://localhost/third")
    ])
    moved = dialog.list_widget.takeItem(1)
    dialog.list_widget.insertItem(0, moved)
    dialog._sync_order_from_list()
    assert [s.name for s in dialog.streams] == ["Second", "First", "Third"]
    dialog.deleteLater()


def test_empty_playlist_allows_adding_first_camera(app, tmp_path):
    dialog = PlaylistEditorDialog(str(tmp_path / "new.m3u"), [])
    assert not dialog.remove_button.isEnabled()
    dialog.add_button.click()
    assert dialog.remove_button.isEnabled()
    QtTest.QTest.keyClicks(dialog.name_edit, "Front Door")
    QtTest.QTest.keyClicks(dialog.url_edit, "rtsp://localhost/front")
    assert dialog._validate()
    dialog.deleteLater()
