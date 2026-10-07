from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .models import Stream
from .grid_view import GridSizeDialog, GridView
from .playlist import load_m3u
from .vlc_backend import VLCBackend
from .updater import UpdateCheckThread, UpdateDownloadThread, apply_pending_update
from . import __version__


class MainWindow(QMainWindow):
    vlc_status = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RelayView")
        self.resize(1280, 780)
        self.setMinimumSize(900, 560)
        self.setAcceptDrops(True)

        icon_path = Path(__file__).resolve().parent.parent / "assets" / "relayview.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.settings = QSettings("RelayView", "RelayView")
        self.streams: list[Stream] = []
        self.filtered_indexes: list[int] = []
        self.current_index = -1
        self._fullscreen = False
        self._sidebar_width = 288
        self._sidebar_was_visible_before_fullscreen = True
        self._view_mode = "single"
        self._update_check_thread = None
        self._update_download_thread = None

        self.vlc_status.connect(self._set_status)
        try:
            self.backend = VLCBackend(lambda text: self.vlc_status.emit(text))
        except RuntimeError as exc:
            self.backend = None
            QTimer.singleShot(0, lambda: self._fatal_player_error(str(exc)))

        self._build_ui()
        self._bind_shortcuts()
        self._restore()
        if self.backend:
            self.backend.set_volume(self.volume_slider.value())
        if self.settings.value("auto_update_check", True, type=bool):
            QTimer.singleShot(3500, lambda: self.check_for_updates(silent=True))

    def _fatal_player_error(self, message: str) -> None:
        QMessageBox.critical(self, "Playback engine unavailable", message)

    def _build_ui(self) -> None:
        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        root_layout.addWidget(self.splitter)

        # Sidebar
        self.sidebar = QFrame(objectName="sidebar")
        self.sidebar.setMinimumWidth(220)
        self.sidebar.setMaximumWidth(420)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(18, 18, 14, 16)
        side.setSpacing(12)

        header = QHBoxLayout()
        brand = QLabel("RelayView", objectName="brand")
        header.addWidget(brand)
        header.addStretch()
        menu_btn = QPushButton("•••", objectName="iconButton")
        menu_btn.setToolTip("Menu")
        menu_btn.clicked.connect(self._show_menu)
        header.addWidget(menu_btn)
        side.addLayout(header)

        self.playlist_label = QLabel("No playlist loaded", objectName="subtle")
        self.playlist_label.setWordWrap(True)
        side.addWidget(self.playlist_label)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter cameras…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._refresh_list)
        side.addWidget(self.search)

        self.camera_list = QListWidget()
        self.camera_list.itemActivated.connect(self._activate_item)
        self.camera_list.itemClicked.connect(self._activate_item)
        side.addWidget(self.camera_list, 1)

        open_btn = QPushButton("Open playlist", objectName="primaryButton")
        open_btn.clicked.connect(self.open_playlist_dialog)
        side.addWidget(open_btn)

        self.splitter.addWidget(self.sidebar)

        # Main player area
        content = QWidget()
        main = QVBoxLayout(content)
        main.setContentsMargins(18, 18, 18, 18)
        main.setSpacing(12)

        top = QFrame(objectName="topBar")
        top_l = QHBoxLayout(top)
        top_l.setContentsMargins(13, 9, 10, 9)
        self.sidebar_btn = QPushButton("☰  Cameras", objectName="cameraToggleButton")
        self.sidebar_btn.setToolTip("Show or hide the camera list (Tab)")
        self.sidebar_btn.clicked.connect(self.toggle_sidebar)
        top_l.addWidget(self.sidebar_btn)

        self.single_view_btn = QPushButton("Single", objectName="viewModeButton")
        self.single_view_btn.setToolTip("Single-camera view")
        self.single_view_btn.clicked.connect(self.show_single_view)
        top_l.addWidget(self.single_view_btn)

        self.grid_btn = QPushButton("▦  Grid…", objectName="viewModeButton")
        self.grid_btn.setToolTip("Configure and open a camera grid")
        self.grid_btn.clicked.connect(self.configure_grid_dialog)
        top_l.addWidget(self.grid_btn)

        self.stream_title = QLabel("Choose a camera", objectName="streamTitle")
        self.stream_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        top_l.addWidget(self.stream_title)
        top_l.addStretch()
        self.status_badge = QLabel("Idle", objectName="liveBadge")
        top_l.addWidget(self.status_badge)
        main.addWidget(top)

        self.viewer_stack = QStackedWidget()

        self.video_frame = QFrame(objectName="videoFrame")
        self.video_frame.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.video_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_frame.setToolTip("Double-click for fullscreen")
        self.video_frame.installEventFilter(self)
        self.viewer_stack.addWidget(self.video_frame)

        self.grid_view = GridView(self.backend)
        grid_rows = max(1, self.settings.value("grid_rows", 2, type=int))
        grid_columns = max(1, self.settings.value("grid_columns", 2, type=int))
        self.grid_view.configure(grid_rows, grid_columns, [])
        self.grid_view.assignments_changed.connect(self._save_grid_state)
        self.grid_view.active_changed.connect(self._grid_active_changed)
        self.viewer_stack.addWidget(self.grid_view)

        main.addWidget(self.viewer_stack, 1)

        controls = QFrame(objectName="controlBar")
        cl = QHBoxLayout(controls)
        cl.setContentsMargins(10, 8, 10, 8)
        cl.setSpacing(8)

        self.prev_btn = QPushButton("‹  Previous")
        self.prev_btn.clicked.connect(self.previous_stream)
        self.prev_btn.setEnabled(False)
        cl.addWidget(self.prev_btn)

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.pause_btn.setEnabled(False)
        cl.addWidget(self.pause_btn)

        self.next_btn = QPushButton("Next  ›")
        self.next_btn.clicked.connect(self.next_stream)
        self.next_btn.setEnabled(False)
        cl.addWidget(self.next_btn)

        cl.addStretch()
        self.status_text = QLabel("Open an .m3u playlist to begin", objectName="statusText")
        cl.addWidget(self.status_text)
        cl.addStretch()

        self.mute_btn = QPushButton("Mute")
        self.mute_btn.clicked.connect(self.toggle_mute)
        self.mute_btn.setEnabled(False)
        cl.addWidget(self.mute_btn)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setObjectName("volumeSlider")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setSingleStep(5)
        self.volume_slider.setPageStep(10)
        self.volume_slider.setFixedWidth(120)
        self.volume_slider.setToolTip("Volume")
        saved_volume = max(0, min(100, self.settings.value("volume", 100, type=int)))
        self.volume_slider.setValue(saved_volume)
        self.volume_slider.valueChanged.connect(self.set_volume)
        cl.addWidget(self.volume_slider)

        self.volume_label = QLabel(f"{saved_volume}%", objectName="volumeLabel")
        self.volume_label.setMinimumWidth(38)
        cl.addWidget(self.volume_label)

        full_btn = QPushButton("Fullscreen")
        full_btn.clicked.connect(self.toggle_fullscreen)
        cl.addWidget(full_btn)

        main.addWidget(controls)
        self.splitter.addWidget(content)
        self.splitter.setSizes([self._sidebar_width, 992])
        self._set_view_button_state()

        # Attaching after native widget creation avoids the player taking over another handle.
        QTimer.singleShot(100, self._attach_video)

    def _attach_video(self) -> None:
        if self.backend:
            self.backend.attach_video(int(self.video_frame.winId()))
            self.grid_view.set_volume(self.volume_slider.value())

    def _bind_shortcuts(self) -> None:
        self._shortcuts: list[QShortcut] = []
        bindings = [
            (QKeySequence(Qt.Key.Key_Left), self.previous_stream),
            (QKeySequence(Qt.Key.Key_Right), self.next_stream),
            (QKeySequence(Qt.Key.Key_Space), self.toggle_pause),
            (QKeySequence("F"), self.toggle_fullscreen),
            (QKeySequence("M"), self.toggle_mute),
            (QKeySequence(Qt.Key.Key_Tab), self.toggle_sidebar),
            (QKeySequence("Ctrl+O"), self.open_playlist_dialog),
            (QKeySequence(Qt.Key.Key_Escape), self._exit_fullscreen),
        ]
        for key, callback in bindings:
            shortcut = QShortcut(key, self)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if watched is self.video_frame and event.type() == QEvent.Type.MouseButtonDblClick:
            self.toggle_fullscreen()
            return True
        return super().eventFilter(watched, event)

    def _show_menu(self) -> None:
        menu = QMenu(self)
        open_action = QAction("Open playlist…", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self.open_playlist_dialog)
        menu.addAction(open_action)

        reload_action = QAction("Reload current playlist", self)
        reload_action.setEnabled(bool(self.settings.value("playlist_path", "")))
        reload_action.triggered.connect(self.reload_playlist)
        menu.addAction(reload_action)
        menu.addSeparator()

        sidebar_action = QAction("Toggle camera list", self)
        sidebar_action.setShortcut(QKeySequence("Tab"))
        sidebar_action.triggered.connect(self.toggle_sidebar)
        menu.addAction(sidebar_action)

        full_action = QAction("Fullscreen", self)
        full_action.setShortcut(QKeySequence("F"))
        full_action.triggered.connect(self.toggle_fullscreen)
        menu.addAction(full_action)

        single_action = QAction("Single-camera view", self)
        single_action.triggered.connect(self.show_single_view)
        menu.addAction(single_action)

        grid_action = QAction("Configure grid…", self)
        grid_action.triggered.connect(self.configure_grid_dialog)
        menu.addAction(grid_action)
        menu.addSeparator()

        update_action = QAction("Check for updates…", self)
        update_action.triggered.connect(lambda: self.check_for_updates(silent=False))
        menu.addAction(update_action)

        auto_update_action = QAction("Check for updates automatically", self)
        auto_update_action.setCheckable(True)
        auto_update_action.setChecked(self.settings.value("auto_update_check", True, type=bool))
        auto_update_action.toggled.connect(lambda checked: self.settings.setValue("auto_update_check", checked))
        menu.addAction(auto_update_action)

        about_action = QAction(f"About RelayView {__version__}", self)
        about_action.setEnabled(False)
        menu.addAction(about_action)

        menu.exec(self.sidebar.mapToGlobal(self.sidebar.rect().topRight()))

    def open_playlist_dialog(self) -> None:
        saved_path = str(self.settings.value("playlist_path", ""))
        start = str(Path(saved_path).parent if saved_path else Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open camera playlist",
            start,
            "M3U playlists (*.m3u *.m3u8);;All files (*.*)",
        )
        if path:
            self.load_playlist(path)

    def load_playlist(self, path: str, restore_stream: bool = False) -> None:
        try:
            streams = load_m3u(path)
        except OSError as exc:
            QMessageBox.warning(self, "Could not open playlist", str(exc))
            return

        if not streams:
            QMessageBox.warning(self, "Empty playlist", "No stream URLs were found in that playlist.")
            return

        self.streams = streams
        self.settings.setValue("playlist_path", path)
        self.playlist_label.setText(Path(path).name)
        self.playlist_label.setToolTip(path)
        self.current_index = -1
        self._refresh_list()
        self._update_nav_buttons()
        self.status_text.setText(f"{len(streams)} streams loaded")

        last_url = self.settings.value("last_stream_url", "") if restore_stream else ""
        target = next((i for i, stream in enumerate(streams) if stream.url == last_url), 0)
        self.select_stream(target)
        self._restore_grid_assignments()
        if self._view_mode == "grid" or (restore_stream and self.settings.value("view_mode", "single") == "grid"):
            self.activate_grid()

    def reload_playlist(self) -> None:
        path = self.settings.value("playlist_path", "")
        if path:
            self.load_playlist(str(path), restore_stream=True)

    def _refresh_list(self) -> None:
        needle = self.search.text().strip().lower()
        self.camera_list.clear()
        self.filtered_indexes.clear()
        for index, stream in enumerate(self.streams):
            haystack = f"{stream.name} {stream.group}".lower()
            if needle and needle not in haystack:
                continue
            label = stream.name if not stream.group else f"{stream.name}\n{stream.group}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(stream.url)
            self.camera_list.addItem(item)
            self.filtered_indexes.append(index)
            if index == self.current_index:
                self.camera_list.setCurrentItem(item)

    def _activate_item(self, item: QListWidgetItem) -> None:
        index = int(item.data(Qt.ItemDataRole.UserRole))
        if self._view_mode == "grid":
            self.grid_view.assign_stream(self.grid_view.active_index, self.streams[index])
            self.status_text.setText(f"Assigned {self.streams[index].name} to tile {self.grid_view.active_index + 1}")
            self.mute_btn.setEnabled(True)
            self.pause_btn.setEnabled(True)
        else:
            self.select_stream(index)

    def select_stream(self, index: int) -> None:
        if not self.streams or self.backend is None:
            return
        index %= len(self.streams)
        stream = self.streams[index]
        self.current_index = index
        self.settings.setValue("last_stream_url", stream.url)
        self._refresh_list()
        self._update_nav_buttons()
        if self._view_mode == "grid":
            return
        self.stream_title.setText(stream.name)
        self.status_text.setText("Connecting…")
        self.status_badge.setText("Connecting")
        self.backend.play(stream.url)
        self.pause_btn.setEnabled(True)
        self.mute_btn.setEnabled(True)
        self.pause_btn.setText("Pause")

    def previous_stream(self) -> None:
        if self._view_mode == "grid":
            return
        if self.streams:
            self.select_stream((self.current_index - 1) % len(self.streams))

    def next_stream(self) -> None:
        if self._view_mode == "grid":
            return
        if self.streams:
            self.select_stream((self.current_index + 1) % len(self.streams))

    def _update_nav_buttons(self) -> None:
        enabled = self._view_mode == "single" and len(self.streams) > 1
        self.prev_btn.setEnabled(enabled)
        self.next_btn.setEnabled(enabled)

    def toggle_pause(self) -> None:
        if not self.backend:
            return
        if self._view_mode == "grid":
            paused = self.grid_view.toggle_pause_all()
            self.pause_btn.setText("Resume all" if paused else "Pause all")
            return
        if self.current_index < 0:
            return
        paused = self.backend.toggle_pause()
        self.pause_btn.setText("Resume" if paused else "Pause")

    def toggle_mute(self) -> None:
        if not self.backend:
            return
        if self._view_mode == "single" and self.current_index < 0:
            return
        muted = not self.backend.is_muted()
        self.backend.set_muted(muted)
        self.grid_view.set_muted(muted)
        self.mute_btn.setText("Unmute" if muted else "Mute")

    def set_volume(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        self.volume_label.setText(f"{value}%")
        self.settings.setValue("volume", value)
        if self.backend:
            self.backend.set_volume(value)
        if hasattr(self, "grid_view"):
            self.grid_view.set_volume(value)

    def _set_status(self, status: str) -> None:
        self.status_text.setText(status)
        self.status_badge.setText(status.replace("…", ""))

    def configure_grid_dialog(self) -> None:
        dialog = GridSizeDialog(self.grid_view.rows, self.grid_view.columns, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        rows, columns = dialog.dimensions()
        self.activate_grid(rows, columns, reconfigure=True)

    def activate_grid(self, rows: int | None = None, columns: int | None = None, reconfigure: bool = False) -> None:
        if rows is not None and columns is not None:
            existing = self.grid_view.stream_assignments()
            count = rows * columns
            assignments = existing[:count]
            assignments.extend([None] * max(0, count - len(assignments)))

            if reconfigure and self.streams:
                used = {stream.url for stream in assignments if stream}
                unused = [stream for stream in self.streams if stream.url not in used]
                for i in range(len(assignments)):
                    if assignments[i] is None and unused:
                        assignments[i] = unused.pop(0)

            self.grid_view.configure(rows, columns, assignments)
            self.settings.setValue("grid_rows", rows)
            self.settings.setValue("grid_columns", columns)

        if self.backend:
            self.backend.stop_primary()
        self.viewer_stack.setCurrentWidget(self.grid_view)
        self._view_mode = "grid"
        self.settings.setValue("view_mode", "grid")
        self.grid_view.set_volume(self.volume_slider.value())
        if self.backend:
            self.grid_view.set_muted(self.backend.is_muted())
        self.grid_view.play_all()
        self.stream_title.setText(f"Grid {self.grid_view.rows}×{self.grid_view.columns}")
        active = sum(1 for stream in self.grid_view.stream_assignments() if stream)
        self.status_text.setText(f"{active} active feed{'s' if active != 1 else ''} · drag tiles to rearrange")
        self.status_badge.setText("Grid")
        self.pause_btn.setText("Pause all")
        self.pause_btn.setEnabled(active > 0)
        self.mute_btn.setEnabled(active > 0)
        self.grid_btn.setText(f"▦  Grid {self.grid_view.rows}×{self.grid_view.columns}")
        self._set_view_button_state()
        self._update_nav_buttons()
        self._save_grid_state()

    def show_single_view(self) -> None:
        if self._view_mode == "single":
            return
        self.grid_view.stop_all()
        self.viewer_stack.setCurrentWidget(self.video_frame)
        self._view_mode = "single"
        self.settings.setValue("view_mode", "single")
        self.pause_btn.setText("Pause")
        if self.current_index >= 0 and self.streams and self.backend:
            stream = self.streams[self.current_index]
            self.stream_title.setText(stream.name)
            self.status_text.setText("Connecting…")
            self.status_badge.setText("Connecting")
            self.backend.play(stream.url)
            self.pause_btn.setEnabled(True)
            self.mute_btn.setEnabled(True)
        else:
            self.stream_title.setText("Choose a camera")
            self.status_text.setText("Choose a camera")
            self.status_badge.setText("Idle")
        self._set_view_button_state()
        self._update_nav_buttons()

    def _set_view_button_state(self) -> None:
        single_active = self._view_mode == "single"
        self.single_view_btn.setProperty("active", single_active)
        self.grid_btn.setProperty("active", not single_active)
        for button in (self.single_view_btn, self.grid_btn):
            button.style().unpolish(button)
            button.style().polish(button)

    def _grid_active_changed(self, index: int) -> None:
        if self._view_mode != "grid":
            return
        stream = self.grid_view.tiles[index].stream if self.grid_view.tiles else None
        if stream:
            self.status_text.setText(f"Tile {index + 1}: {stream.name} · choose a camera to replace it")
        else:
            self.status_text.setText(f"Tile {index + 1} selected · choose a camera from the list")

    def _save_grid_state(self) -> None:
        if not hasattr(self, "grid_view"):
            return
        self.settings.setValue("grid_rows", self.grid_view.rows)
        self.settings.setValue("grid_columns", self.grid_view.columns)
        self.settings.setValue("grid_urls", self.grid_view.urls())

    def _restore_grid_assignments(self) -> None:
        if not self.streams:
            return
        rows = max(1, self.settings.value("grid_rows", 2, type=int))
        columns = max(1, self.settings.value("grid_columns", 2, type=int))
        raw_urls = self.settings.value("grid_urls", [])
        if isinstance(raw_urls, str):
            urls = [raw_urls] if raw_urls else []
        else:
            urls = list(raw_urls or [])

        by_url = {stream.url: stream for stream in self.streams}
        count = rows * columns
        assignments: list[Stream | None] = []
        if urls:
            assignments = [by_url.get(url) if url else None for url in urls[:count]]
            assignments.extend([None] * max(0, count - len(assignments)))
        else:
            assignments = list(self.streams[:count])
            assignments.extend([None] * max(0, count - len(assignments)))
        self.grid_view.configure(rows, columns, assignments)
        self.grid_btn.setText(f"▦  Grid {rows}×{columns}")
        self._save_grid_state()

    def toggle_sidebar(self) -> None:
        visible = self.sidebar.isVisible()
        if visible:
            self._sidebar_width = max(220, self.sidebar.width())
            self.sidebar.hide()
            self.sidebar_btn.setText("☰  Show cameras")
        else:
            self.sidebar.show()
            self.splitter.setSizes([self._sidebar_width, max(600, self.width() - self._sidebar_width)])
            self.sidebar_btn.setText("☰  Cameras")

    def toggle_fullscreen(self) -> None:
        if self._fullscreen:
            self._exit_fullscreen()
            return
        self._fullscreen = True
        self._sidebar_was_visible_before_fullscreen = self.sidebar.isVisible()
        self.sidebar.hide()
        self.menuBar().hide()
        self.showFullScreen()

    def _exit_fullscreen(self) -> None:
        if not self._fullscreen:
            return
        self._fullscreen = False
        self.showNormal()
        if self._sidebar_was_visible_before_fullscreen:
            self.sidebar.show()
            self.sidebar_btn.setText("☰  Cameras")
        else:
            self.sidebar.hide()
            self.sidebar_btn.setText("☰  Show cameras")

    def _restore(self) -> None:
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        path = self.settings.value("playlist_path", "")
        if path and Path(str(path)).exists():
            QTimer.singleShot(150, lambda: self.load_playlist(str(path), restore_stream=True))

    def check_for_updates(self, silent: bool = False) -> None:
        if self._update_check_thread and self._update_check_thread.isRunning():
            if not silent:
                self.status_text.setText("Already checking for updates…")
            return

        if not silent:
            self.status_text.setText("Checking for updates…")

        thread = UpdateCheckThread(self)
        self._update_check_thread = thread

        def finished(available: bool, error: str) -> None:
            if error:
                if not silent:
                    QMessageBox.warning(self, "Update check failed", error)
                    self.status_text.setText("Update check failed")
                return
            if not available:
                if not silent:
                    QMessageBox.information(self, "RelayView", "You're already running the latest version.")
                    self.status_text.setText("RelayView is up to date")
                return

            answer = QMessageBox.question(
                self,
                "RelayView update available",
                "A newer version of RelayView is available. Download it now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._download_update()

        thread.finished_check.connect(finished)
        thread.start()

    def _download_update(self) -> None:
        if self._update_download_thread and self._update_download_thread.isRunning():
            return

        self.status_text.setText("Downloading update… 0%")
        thread = UpdateDownloadThread(self)
        self._update_download_thread = thread
        thread.progress.connect(lambda value: self.status_text.setText(f"Downloading update… {value}%"))

        def finished(ok: bool, error: str) -> None:
            if not ok:
                QMessageBox.warning(self, "Update failed", error or "The update could not be downloaded.")
                self.status_text.setText("Update failed")
                return

            self.status_text.setText("Update ready")
            answer = QMessageBox.question(
                self,
                "Update ready",
                "The update has been downloaded. Restart RelayView now to install it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

            self.settings.sync()
            if self.backend:
                self.backend.stop()

            # Return control to Qt for one event-loop turn so the dialog closes
            # and the UI can repaint before Velopack exits/restarts the process.
            def apply_now() -> None:
                try:
                    self.status_text.setText("Restarting to install update…")
                    apply_pending_update()
                except Exception as exc:
                    QMessageBox.critical(self, "Could not apply update", str(exc))
                    self.status_text.setText("Update install failed")

            QTimer.singleShot(0, apply_now)

        thread.downloaded.connect(finished)
        thread.start()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.settings.setValue("geometry", self.saveGeometry())
        self._save_grid_state()
        if self.backend:
            self.backend.stop()
        super().closeEvent(event)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt API
        urls = event.mimeData().urls()
        if any(url.toLocalFile().lower().endswith((".m3u", ".m3u8")) for url in urls):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt API
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".m3u", ".m3u8")):
                self.load_playlist(path)
                event.acceptProposedAction()
                break
