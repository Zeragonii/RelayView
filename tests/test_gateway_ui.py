import pytest

QtWidgets = pytest.importorskip("PySide6.QtWidgets")
QtCore = pytest.importorskip("PySide6.QtCore")
pytest.importorskip("PySide6.QtNetwork")

from relayview.models import Stream
from relayview.playlist import serialize_m3u, parse_m3u_text
from relayview.playlist_editor import PlaylistEditorDialog
from relayview.gateway_ui import GatewayDialog, PtzDialog, camera_ptz_id


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_m3u_ptz_mapping_round_trip():
    streams = [Stream("Driveway", "rtsp://localhost/drive",
                      attrs={"relayview-ptz-camera": "driveway"})]
    restored = parse_m3u_text(serialize_m3u(streams))
    assert camera_ptz_id(restored[0]) == "driveway"


def test_playlist_editor_persists_ptz_camera_id(app, tmp_path):
    stream = Stream("Front", "rtsp://localhost/front")
    dialog = PlaylistEditorDialog(str(tmp_path / "cams.m3u"), [stream])
    dialog.ptz_camera_edit.setText("front_garden")
    dialog.ptz_camera_edit.textEdited.emit("front_garden")
    assert dialog.streams[0].attrs["relayview-ptz-camera"] == "front_garden"
    assert dialog._validate()
    dialog.deleteLater()


def test_gateway_settings_dialog_has_pull_push(app, tmp_path):
    settings = QtCore.QSettings(str(tmp_path / "settings.ini"), QtCore.QSettings.Format.IniFormat)
    pulled = []
    dialog = GatewayDialog(settings, lambda: [Stream("A", "rtsp://localhost/a")],
                           lambda streams: pulled.extend(streams))
    assert dialog.findChild(QtWidgets.QPushButton, "gatewayPullPlaylist") is not None
    assert dialog.findChild(QtWidgets.QPushButton, "gatewayPushPlaylist") is not None
    dialog.deleteLater()


def test_ptz_controls_available_for_mapped_camera(app, tmp_path):
    settings = QtCore.QSettings(str(tmp_path / "settings.ini"), QtCore.QSettings.Format.IniFormat)
    stream = Stream("PTZ", "rtsp://localhost/a", attrs={"relayview-ptz-camera": "ptz"})
    dialog = PtzDialog(settings, lambda: stream)
    assert "ptz" in dialog.camera_label.text()
    assert dialog.findChild(QtWidgets.QPushButton, "ptzMOVE_LEFT") is not None
    assert dialog.findChild(QtWidgets.QPushButton, "ptzSTOP") is not None
    dialog.close()
    dialog.deleteLater()
