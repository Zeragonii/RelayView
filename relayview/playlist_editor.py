from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .models import Stream
from .playlist import save_m3u


class PlaylistEditorDialog(QDialog):
    def __init__(self, playlist_path: str, streams: list[Stream], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit playlist · RelayView")
        self.resize(900, 620)
        self.setMinimumSize(760, 500)
        self.playlist_path = playlist_path
        self.streams = list(streams)
        # Stable row identity survives edited and duplicate camera URLs.
        self._stream_keys = list(range(len(self.streams)))
        self._next_stream_key = len(self.streams)
        self._loading_fields = False

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel("Playlist editor", objectName="dialogTitle")
        root.addWidget(title)
        hint = QLabel(
            "Add, remove, or drag cameras to reorder them. Changes are kept in memory until you save.",
            objectName="subtle",
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 8, 0)
        left_l.setSpacing(8)
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("playlistEditorList")
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.currentRowChanged.connect(self._load_row)
        self.list_widget.model().rowsMoved.connect(self._sync_order_from_list)
        left_l.addWidget(self.list_widget, 1)
        list_actions = QHBoxLayout()
        self.add_button = QPushButton("+ Add camera")
        self.add_button.setObjectName("playlistEditorAddCamera")
        self.add_button.clicked.connect(self._add_camera)
        list_actions.addWidget(self.add_button)
        self.remove_button = QPushButton("Remove selected")
        self.remove_button.setObjectName("playlistEditorRemoveCamera")
        self.remove_button.clicked.connect(self._remove_selected)
        self.remove_button.setEnabled(False)
        list_actions.addWidget(self.remove_button)
        left_l.addLayout(list_actions)
        splitter.addWidget(left)

        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(8, 0, 0, 0)
        form = QFormLayout()
        form.setSpacing(10)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Front Door")
        self.name_edit.textEdited.connect(self._field_changed)
        form.addRow("Display name", self.name_edit)

        self.group_edit = QLineEdit()
        self.group_edit.setPlaceholderText("Outside")
        self.group_edit.textEdited.connect(self._field_changed)
        form.addRow("Group", self.group_edit)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("rtsp://…")
        self.url_edit.textEdited.connect(self._field_changed)
        form.addRow("Stream URL", self.url_edit)

        self.favorite_check = QCheckBox("Favourite")
        self.favorite_check.toggled.connect(self._field_changed)
        form.addRow("", self.favorite_check)

        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("Optional notes about this camera…")
        self.notes_edit.setFixedHeight(110)
        self.notes_edit.textChanged.connect(self._field_changed)
        form.addRow("Notes", self.notes_edit)

        right_l.addLayout(form)
        right_l.addStretch()

        tip = QLabel(
            "Favourite and Notes are saved as RelayView-specific EXTINF attributes. Other M3U players can safely ignore them.",
            objectName="subtle",
        )
        tip.setWordWrap(True)
        right_l.addWidget(tip)
        splitter.addWidget(right)
        splitter.setSizes([330, 550])

        footer = QHBoxLayout()
        self.path_label = QLabel(Path(playlist_path).name, objectName="subtle")
        self.path_label.setToolTip(playlist_path)
        footer.addWidget(self.path_label)
        footer.addStretch()

        save_as = QPushButton("Save As…")
        save_as.clicked.connect(self._save_as)
        footer.addWidget(save_as)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        footer.addWidget(buttons)
        root.addLayout(footer)

        self._populate()

    def _populate(self) -> None:
        self.list_widget.clear()
        for stream, key in zip(self.streams, self._stream_keys):
            self._add_item(stream, key)
        if self.streams:
            self.list_widget.setCurrentRow(0)

    def _add_item(self, stream: Stream, key: int) -> None:
        star = "★  " if stream.favorite else ""
        text = f"{star}{stream.name or 'New camera'}"
        if stream.group:
            text += f"\n{stream.group}"
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, key)
        tooltip = stream.url
        if stream.notes:
            tooltip += f"\n\n{stream.notes}"
        item.setToolTip(tooltip)
        self.list_widget.addItem(item)

    def _add_camera(self) -> None:
        stream = Stream(name="", url="")
        key = self._next_stream_key
        self._next_stream_key += 1
        self.streams.append(stream)
        self._stream_keys.append(key)
        self._add_item(stream, key)
        self.list_widget.setCurrentRow(self.list_widget.count() - 1)
        self.name_edit.setFocus()

    def _remove_selected(self) -> None:
        row = self.list_widget.currentRow()
        if not (0 <= row < len(self.streams)):
            return
        self.streams.pop(row)
        self._stream_keys.pop(row)
        self.list_widget.takeItem(row)
        self.list_widget.setCurrentRow(min(row, self.list_widget.count() - 1))
        self._load_row(self.list_widget.currentRow())

    def _load_row(self, row: int) -> None:
        self._loading_fields = True
        enabled = 0 <= row < len(self.streams)
        self.remove_button.setEnabled(enabled)
        for widget in (self.name_edit, self.group_edit, self.url_edit, self.favorite_check, self.notes_edit):
            widget.setEnabled(enabled)
        if enabled:
            stream = self.streams[row]
            self.name_edit.setText(stream.name)
            self.group_edit.setText(stream.group)
            self.url_edit.setText(stream.url)
            self.favorite_check.setChecked(stream.favorite)
            self.notes_edit.setPlainText(stream.notes)
        else:
            self.name_edit.clear()
            self.group_edit.clear()
            self.url_edit.clear()
            self.favorite_check.setChecked(False)
            self.notes_edit.clear()
        self._loading_fields = False

    def _field_changed(self, *_args) -> None:
        if self._loading_fields:
            return
        row = self.list_widget.currentRow()
        if not (0 <= row < len(self.streams)):
            return
        old = self.streams[row]
        updated = replace(
            old,
            name=self.name_edit.text().strip(),
            group=self.group_edit.text().strip(),
            url=self.url_edit.text().strip(),
            favorite=self.favorite_check.isChecked(),
            notes=self.notes_edit.toPlainText().strip(),
        )
        self.streams[row] = updated
        item = self.list_widget.item(row)
        star = "★  " if updated.favorite else ""
        item.setText(f"{star}{updated.name or 'New camera'}" + (f"\n{updated.group}" if updated.group else ""))
        item.setToolTip(updated.url + (f"\n\n{updated.notes}" if updated.notes else ""))

    def _sync_order_from_list(self, *_args) -> None:
        # QListWidget finishes the internal move before rowsMoved fires. Use
        # stable IDs instead of URLs: different cameras may share a stream URL.
        keys = [self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.list_widget.count())]
        streams_by_key = dict(zip(self._stream_keys, self.streams))
        if len(keys) != len(streams_by_key) or set(keys) != set(streams_by_key):
            return
        self.streams = [streams_by_key[key] for key in keys]
        self._stream_keys = keys
        self._load_row(self.list_widget.currentRow())

    def _validate(self) -> bool:
        if not self.streams:
            QMessageBox.warning(self, "Nothing to save", "The playlist contains no streams.")
            return False
        for index, stream in enumerate(self.streams, 1):
            if not stream.name.strip():
                QMessageBox.warning(self, "Missing name", f"Stream {index} has no display name.")
                return False
            if not stream.url.strip():
                QMessageBox.warning(self, "Missing URL", f"{stream.name} has no stream URL.")
                return False
        return True

    def _write(self, path: str) -> bool:
        if not self._validate():
            return False
        try:
            save_m3u(path, self.streams)
        except OSError as exc:
            QMessageBox.critical(self, "Could not save playlist", str(exc))
            return False
        self.playlist_path = path
        return True

    def _save(self) -> None:
        if self._write(self.playlist_path):
            self.accept()

    def _save_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save playlist as",
            self.playlist_path,
            "M3U playlists (*.m3u *.m3u8);;All files (*.*)",
        )
        if not path:
            return
        if not path.lower().endswith((".m3u", ".m3u8")):
            path += ".m3u"
        if self._write(path):
            self.path_label.setText(Path(path).name)
            self.path_label.setToolTip(path)
            self.accept()
