"""Qt gateway client: central playlist pull/push and Frigate MQTT PTZ commands.

Only the API token and configured gateway URL are stored locally; no camera
credentials are transmitted to MQTT. The gateway handles MQTT itself.
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer, Qt, QUrl, QStandardPaths
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
)

from .models import Stream
from .playlist import parse_m3u_text, save_m3u, serialize_m3u


def camera_ptz_id(stream: Stream | None) -> str:
    return stream.attrs.get("relayview-ptz-camera", "").strip() if stream else ""


class GatewayHttp:
    """Asynchronous HTTP client owned by one Qt dialog."""

    def __init__(self, parent):
        self.manager = QNetworkAccessManager(parent)
        self._pending = set()

    def send(self, url: str, token: str, method: str, path: str, callback, body: bytes = b"",
             etag: str = "") -> None:
        base = url.strip().rstrip("/")
        parsed = QUrl(base)
        if not parsed.isValid() or parsed.scheme() not in ("https", "http") or not parsed.host():
            callback(0, b"", {}, "Enter a valid HTTP(S) gateway URL.")
            return
        if not token:
            callback(0, b"", {}, "Enter the gateway API token.")
            return
        request = QNetworkRequest(QUrl(base + path))
        request.setRawHeader(b"Authorization", ("Bearer " + token.strip()).encode("utf-8"))
        request.setRawHeader(b"Accept", b"*/*")
        request.setTransferTimeout(8000)
        if body:
            request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "audio/x-mpegurl")
        if etag:
            request.setRawHeader(b"If-Match", etag.encode("ascii"))
        if method == "GET":
            reply = self.manager.get(request)
        elif method == "PUT":
            reply = self.manager.put(request, body)
        elif method == "POST":
            request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
            reply = self.manager.post(request, body)
        else:
            raise ValueError("Unsupported HTTP method")
        self._pending.add(reply)

        def finished():
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0
            headers = {bytes(k).decode("ascii", "replace").lower(): bytes(v).decode("utf-8", "replace")
                       for k, v in reply.rawHeaderPairs()}
            data = bytes(reply.readAll())
            error = reply.errorString() if reply.error() != QNetworkReply.NetworkError.NoError else ""
            self._pending.discard(reply)
            reply.deleteLater()
            callback(int(status), data, headers, error)

        reply.finished.connect(finished)


class GatewayDialog(QDialog):
    """User-initiated master playlist sync; never silently overwrites devices."""

    def __init__(self, settings: QSettings, get_streams, apply_playlist, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RelayView gateway / master playlist")
        self.setMinimumWidth(480)
        self.settings = settings
        self.get_streams = get_streams
        self.apply_playlist = apply_playlist
        self.http = GatewayHttp(self)
        root = QVBoxLayout(self)
        description = QLabel(
            "The gateway stores a shared master playlist and sends PTZ commands through Frigate. "
            "Pull replaces this device's camera list; Push replaces the master playlist."
        )
        description.setWordWrap(True)
        root.addWidget(description)
        form = QFormLayout()
        self.url_edit = QLineEdit(str(settings.value("gateway_url", "")))
        self.url_edit.setPlaceholderText("https://relayview.example.com")
        form.addRow("Gateway URL", self.url_edit)
        self.token_edit = QLineEdit(str(settings.value("gateway_token", "")))
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setPlaceholderText("Private API token")
        form.addRow("API token", self.token_edit)
        root.addLayout(form)
        buttons = QHBoxLayout()
        save = QPushButton("Save connection")
        save.clicked.connect(self._save_connection)
        buttons.addWidget(save)
        pull = QPushButton("↓ Pull master playlist")
        pull.setObjectName("gatewayPullPlaylist")
        pull.clicked.connect(self._pull)
        buttons.addWidget(pull)
        push = QPushButton("↑ Push local playlist")
        push.setObjectName("gatewayPushPlaylist")
        push.clicked.connect(self._push)
        buttons.addWidget(push)
        root.addLayout(buttons)
        self.status = QLabel("Configure an HTTPS URL and token, then Pull or Push.")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        root.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)

    def _credentials(self) -> tuple[str, str]:
        return self.url_edit.text().strip().rstrip("/"), self.token_edit.text().strip()

    def _save_connection(self) -> None:
        url, token = self._credentials()
        if not QUrl(url).isValid() or not url.startswith(("https://", "http://")) or not token:
            self.status.setText("Please enter a valid gateway URL and API token.")
            return
        self.settings.setValue("gateway_url", url)
        self.settings.setValue("gateway_token", token)
        self.status.setText("Connection details saved locally. Use HTTPS outside a trusted LAN.")

    def _pull(self) -> None:
        self._save_connection()
        url, token = self._credentials()
        self.status.setText("Downloading master playlist…")

        def received(status, data, headers, error):
            if status != 200:
                self.status.setText(f"Pull failed (HTTP {status}): {error}")
                return
            try:
                text = data.decode("utf-8-sig")
                streams = parse_m3u_text(text)
                if not text.lstrip().startswith("#EXTM3U"):
                    raise ValueError("Not an M3U playlist")
            except (UnicodeDecodeError, ValueError) as exc:
                self.status.setText(f"Invalid master playlist: {exc}")
                return
            answer = QMessageBox.question(
                self, "Replace local playlist?",
                f"Replace this device's local playlist with {len(streams)} master cameras? "
                "Unsynchronised local camera edits will be lost.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.status.setText("Pull cancelled.")
                return
            try:
                self.apply_playlist(streams)
                self.status.setText(f"Pulled {len(streams)} cameras successfully.")
            except Exception as exc:
                self.status.setText(f"Could not save local playlist: {exc}")

        self.http.send(url, token, "GET", "/api/v1/playlist", received)

    def _push(self) -> None:
        streams = self.get_streams()
        if not streams:
            self.status.setText("No local cameras to push.")
            return
        answer = QMessageBox.question(self, "Replace master playlist?",
            f"Upload this device's {len(streams)} cameras and replace the central master playlist?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._save_connection()
        url, token = self._credentials()
        body = serialize_m3u(streams).encode("utf-8")
        self.status.setText("Checking master playlist version…")

        def got_master(status, data, headers, error):
            if status != 200 or not headers.get("etag"):
                self.status.setText(f"Cannot check master playlist (HTTP {status}): {error}")
                return
            self.status.setText("Uploading master playlist…")

            def uploaded(code, body, headers, error):
                if code == 200:
                    self.status.setText(f"Master playlist updated with {len(streams)} cameras.")
                elif code == 412:
                    self.status.setText("Another device updated the master. Pull and review before retrying.")
                else:
                    self.status.setText(f"Push failed (HTTP {code}): {error}")

            self.http.send(url, token, "PUT", "/api/v1/playlist", uploaded,
                           body=body, etag=headers["etag"])

        self.http.send(url, token, "GET", "/api/v1/playlist", got_master)


class PtzDialog(QDialog):
    """Hold-to-move control panel for the current Windows camera or active tile."""

    def __init__(self, settings: QSettings, current_stream, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Physical PTZ · Frigate")
        self.setMinimumWidth(340)
        self.settings = settings
        self.current_stream = current_stream
        self.http = GatewayHttp(self)
        self.active_camera = ""
        self.active_command = ""
        self.tick = QTimer(self)
        self.tick.setInterval(250)
        self.tick.timeout.connect(self._repeat)
        root = QVBoxLayout(self)
        label = QLabel("Hold a direction to move the actual camera. Digital zoom/pan is unchanged.")
        label.setWordWrap(True)
        root.addWidget(label)
        self.camera_label = QLabel()
        root.addWidget(self.camera_label)
        grid = QGridLayout()
        controls = [
            ("▲", "MOVE_UP", 0, 1), ("◀", "MOVE_LEFT", 1, 0),
            ("STOP", "STOP", 1, 1), ("▶", "MOVE_RIGHT", 1, 2),
            ("▼", "MOVE_DOWN", 2, 1), ("Zoom +", "ZOOM_IN", 3, 0),
            ("Zoom −", "ZOOM_OUT", 3, 2),
        ]
        for label, command, row, col in controls:
            button = QPushButton(label)
            button.setMinimumHeight(42)
            button.setObjectName("ptz" + command)
            if command == "STOP":
                button.clicked.connect(self._stop)
            else:
                button.pressed.connect(lambda cmd=command: self._start(cmd))
                button.released.connect(self._stop)
            grid.addWidget(button, row, col)
        root.addLayout(grid)
        presets = QHBoxLayout()
        self.preset_edit = QLineEdit()
        self.preset_edit.setPlaceholderText("Preset name")
        presets.addWidget(self.preset_edit)
        go = QPushButton("Go to preset")
        go.clicked.connect(self._preset)
        presets.addWidget(go)
        root.addLayout(presets)
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.refresh = QTimer(self)
        self.refresh.setInterval(600)
        self.refresh.timeout.connect(self._update_camera)
        self.refresh.start()
        self._update_camera()

    def _update_camera(self):
        stream = self.current_stream()
        self.camera_label.setText(
            f"Camera: {stream.name if stream else 'None'} · "
            f"Frigate ID: {camera_ptz_id(stream) or '(not configured)'}"
        )

    def _command(self, camera: str, command: str):
        url = str(self.settings.value("gateway_url", ""))
        token = str(self.settings.value("gateway_token", ""))
        if not camera:
            self.status.setText("Set the Frigate PTZ camera ID in the playlist editor.")
            return
        self.http.send(url, token, "POST", f"/api/v1/ptz/{camera}/command",
                       lambda code, data, headers, error: self.status.setText(
                           "" if code == 200 else f"PTZ unavailable (HTTP {code}): {error}"
                       ), body=json.dumps({"command": command}).encode("utf-8"))

    def _start(self, command: str):
        self._stop()
        camera = camera_ptz_id(self.current_stream())
        if not camera:
            self.status.setText("This stream has no Frigate PTZ camera ID.")
            return
        self.active_camera = camera
        self.active_command = command
        self._command(camera, command)
        self.tick.start()

    def _repeat(self):
        if self.active_camera and self.active_command:
            self._command(self.active_camera, self.active_command)

    def _stop(self):
        self.tick.stop()
        if self.active_camera:
            self._command(self.active_camera, "STOP")
        self.active_camera = ""
        self.active_command = ""

    def _preset(self):
        import re
        value = self.preset_edit.text().strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
            self.status.setText("Preset name must use letters, numbers, hyphen or underscore.")
            return
        self._stop()
        self._command(camera_ptz_id(self.current_stream()), "preset_" + value)

    def closeEvent(self, event):
        self._stop()
        super().closeEvent(event)
