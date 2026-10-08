from __future__ import annotations

from pathlib import Path
import json

from PySide6.QtCore import QEvent, QSettings, Qt, QTimer, Signal, QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
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
from .grid_view import GridSizeDialog, GridView, MAX_GRID_TILES
from .grid_profiles import validate_profile, resolve_assignments
from .playlist import load_m3u
from .playlist_editor import PlaylistEditorDialog
from .vlc_backend import VLCBackend
from .updater import UpdateCheckThread, UpdateDownloadThread, handoff_update_and_restart
from . import __version__
from .diagnostics import diagnostic_summary
from .logging_config import current_log_path, get_log_level, get_logger, log_dir, set_log_level

log = get_logger("ui")


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
        log.info("MainWindow initialising version=%s log_level=%s", __version__, get_log_level())
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

        # Lightweight crash detection on the Qt thread (no worker GUI callbacks).
        self._worker_watchdog = QTimer(self)
        self._worker_watchdog.setInterval(1000)
        self._worker_watchdog.timeout.connect(self._poll_workers)
        self._worker_watchdog.start()

        self._build_ui()
        self._bind_shortcuts()
        self._restore()
        if self.backend:
            self.backend.set_volume(self.volume_slider.value())
        if self.settings.value("auto_update_check", True, type=bool):
            QTimer.singleShot(3500, lambda: self.check_for_updates(silent=True))

    def _poll_workers(self) -> None:
        if not self.backend:
            return
        if self._view_mode == "single":
            self.backend.primary.check_health()
        else:
            for player in list(self.backend._extra_players):
                player.check_health()

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

        playlist_buttons = QHBoxLayout()
        playlist_buttons.setSpacing(8)
        open_btn = QPushButton("Open playlist", objectName="primaryButton")
        open_btn.clicked.connect(self.open_playlist_dialog)
        playlist_buttons.addWidget(open_btn, 1)
        self.edit_playlist_btn = QPushButton("Edit…")
        self.edit_playlist_btn.setToolTip("Rename, reorder and edit stream metadata")
        self.edit_playlist_btn.setEnabled(False)
        self.edit_playlist_btn.clicked.connect(self.edit_playlist)
        playlist_buttons.addWidget(self.edit_playlist_btn)
        side.addLayout(playlist_buttons)

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

        edit_action = QAction("Edit playlist…", self)
        edit_action.setEnabled(bool(self.streams) and bool(self.settings.value("playlist_path", "")))
        edit_action.triggered.connect(self.edit_playlist)
        menu.addAction(edit_action)
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
        layouts_menu = menu.addMenu("Saved camera layouts")
        save_layout = QAction("Save current layout…", self)
        save_layout.triggered.connect(self.save_named_layout)
        layouts_menu.addAction(save_layout)
        delete_layout = layouts_menu.addMenu("Delete layout")
        profiles = self._named_layouts()
        if not profiles:
            empty = layouts_menu.addAction("No saved layouts")
            empty.setEnabled(False)
        for name in sorted(profiles, key=str.casefold):
            action = layouts_menu.addAction(name)
            action.triggered.connect(lambda checked=False, selected=name: self.load_named_layout(selected))
            remove = delete_layout.addAction(name)
            remove.triggered.connect(lambda checked=False, selected=name: self.delete_named_layout(selected))
        menu.addSeparator()

        logging_menu = menu.addMenu("Logging")
        level_group = QActionGroup(self)
        level_group.setExclusive(True)
        current_level = get_log_level()
        for level in ("ERROR", "WARNING", "INFO", "DEBUG"):
            action = QAction(level.title(), self)
            action.setCheckable(True)
            action.setChecked(level == current_level)
            action.triggered.connect(lambda checked, selected=level: checked and self._set_log_level(selected))
            level_group.addAction(action)
            logging_menu.addAction(action)
        logging_menu.addSeparator()
        open_logs = QAction("Open log folder", self)
        open_logs.triggered.connect(self._open_log_folder)
        logging_menu.addAction(open_logs)
        copy_diag = QAction("Copy diagnostic summary", self)
        copy_diag.triggered.connect(self._copy_diagnostic_summary)
        logging_menu.addAction(copy_diag)

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

    def _set_log_level(self, level: str) -> None:
        level = set_log_level(level)
        self.settings.setValue("log_level", level)
        self.settings.sync()
        log.warning("Runtime logging level selected=%s", level)
        self.status_text.setText(f"Logging set to {level}")

    def _open_log_folder(self) -> None:
        path = log_dir()
        log.info("Opening log folder path=%s", path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _copy_diagnostic_summary(self) -> None:
        playlist_path = str(self.settings.value("playlist_path", ""))
        summary = diagnostic_summary(
            version=__version__,
            playlist_name=Path(playlist_path).name if playlist_path else "",
            view_mode=self._view_mode,
            grid_rows=self.grid_view.rows,
            grid_columns=self.grid_view.columns,
            active_grid_feeds=sum(1 for stream in self.grid_view.stream_assignments() if stream),
            player_details=[self.backend.primary.diagnostics()] + [pl.diagnostics() for pl in self.backend._extra_players] if self.backend else [],
        )
        QApplication.clipboard().setText(summary)
        log.info("Diagnostic summary copied log=%s", current_log_path())
        self.status_text.setText("Diagnostic summary copied")

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
        self.edit_playlist_btn.setEnabled(True)
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

    def edit_playlist(self) -> None:
        path = str(self.settings.value("playlist_path", ""))
        if not path or not self.streams:
            QMessageBox.information(self, "No playlist", "Open a playlist before editing it.")
            return
        dialog = PlaylistEditorDialog(path, self.streams, self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.settings.setValue("playlist_path", dialog.playlist_path)
            self.load_playlist(dialog.playlist_path, restore_stream=True)
            self.status_text.setText(f"Playlist saved · {len(self.streams)} streams")

    def _refresh_list(self) -> None:
        needle = self.search.text().strip().lower()
        self.camera_list.clear()
        self.filtered_indexes.clear()
        for index, stream in enumerate(self.streams):
            haystack = f"{stream.name} {stream.group} {stream.notes}".lower()
            if needle and needle not in haystack:
                continue
            star = "★  " if stream.favorite else ""
            label = f"{star}{stream.name}" if not stream.group else f"{star}{stream.name}\n{stream.group}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, index)
            tooltip = stream.url
            if stream.notes:
                tooltip += f"\n\n{stream.notes}"
            item.setToolTip(tooltip)
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

    def _named_layouts(self) -> dict:
        """Read profiles defensively; existing unnamed grid settings remain intact."""
        try:
            profiles = json.loads(self.settings.value("named_grid_layouts", "{}"))
            return profiles if isinstance(profiles, dict) else {}
        except (ValueError, TypeError):
            log.warning("Ignoring invalid named layout settings")
            return {}

    def save_named_layout(self) -> None:
        name, accepted = QInputDialog.getText(self, "Save camera layout", "Layout name:")
        name = name.strip()
        if not accepted or not name:
            return
        profiles = self._named_layouts()
        if name in profiles and QMessageBox.question(self, "Replace layout?", f"Replace saved layout '{name}'?") != QMessageBox.StandardButton.Yes:
            return
        profiles[name] = {"rows": self.grid_view.rows, "columns": self.grid_view.columns,
                          "urls": self.grid_view.urls()}
        self.settings.setValue("named_grid_layouts", json.dumps(profiles))
        self.status_text.setText(f"Saved layout: {name}")

    def load_named_layout(self, name: str) -> None:
        profile = self._named_layouts().get(name)
        if not isinstance(profile, dict):
            return
        try:
            rows, columns, urls = validate_profile(profile)
        except ValueError:
            QMessageBox.warning(self, "Invalid layout", "The saved layout is invalid or exceeds the grid limit.")
            return
        assignments = resolve_assignments(urls, rows, columns, self.streams)
        # Switching from single-view must release the primary HWND first.
        if self._view_mode == "single" and self.backend:
            self.backend.quiesce_primary()
        self.grid_view.configure(rows, columns, assignments)
        self.activate_grid()
        self.status_text.setText(f"Layout: {name}")

    def delete_named_layout(self, name: str) -> None:
        if QMessageBox.question(self, "Delete camera layout", f"Delete saved layout '{name}'?") != QMessageBox.StandardButton.Yes:
            return
        profiles = self._named_layouts()
        profiles.pop(name, None)
        self.settings.setValue("named_grid_layouts", json.dumps(profiles))

    def configure_grid_dialog(self) -> None:
        log.info("Opening grid configuration current=%sx%s", self.grid_view.rows, self.grid_view.columns)
        dialog = GridSizeDialog(self.grid_view.rows, self.grid_view.columns, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        rows, columns = dialog.dimensions()
        log.info("Grid configuration accepted rows=%s columns=%s", rows, columns)
        self.activate_grid(rows, columns, reconfigure=True)

    def activate_grid(self, rows: int | None = None, columns: int | None = None, reconfigure: bool = False) -> None:
        log.info("activate_grid begin rows=%s columns=%s reconfigure=%s view_mode=%s", rows, columns, reconfigure, self._view_mode)
        if rows is not None and columns is not None and (rows < 1 or columns < 1 or rows * columns > MAX_GRID_TILES):
            QMessageBox.warning(self, "Grid too large", f"A grid can contain at most {MAX_GRID_TILES} tiles.")
            return

        # The single player must be detached and fully stopped while its QWidget/HWND
        # is still alive. Only after VLC has returned from stop() do we rebuild/show
        # grid widgets. This avoids native video-output teardown racing Qt window changes.
        if self.backend and self._view_mode == "single":
            log.info("Transition single->grid: quiescing primary before grid changes")
            self.backend.quiesce_primary()
            log.info("Transition single->grid: primary quiesced")

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

            log.info("Transition grid: configuring widgets after playback teardown")
            self.grid_view.configure(rows, columns, assignments)
            self.settings.setValue("grid_rows", rows)
            self.settings.setValue("grid_columns", columns)

        log.debug("Transition single->grid: switching viewer stack")
        self.viewer_stack.setCurrentWidget(self.grid_view)
        self._view_mode = "grid"
        self.settings.setValue("view_mode", "grid")
        self.grid_view.set_volume(self.volume_slider.value())
        if self.backend:
            self.grid_view.set_muted(self.backend.is_muted())
        log.info("Transition single->grid: starting assigned grid players")
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
        log.info("activate_grid complete grid=%sx%s active=%s", self.grid_view.rows, self.grid_view.columns, active)

    def show_single_view(self) -> None:
        if self._view_mode == "single":
            return
        log.info("Transition grid->single begin")
        # Release grid players completely while their host widgets still exist.
        # This mirrors the single->grid path and prevents native VLC video output
        # from retaining HWNDs after Qt changes the visible page.
        self.grid_view.release_all_players()
        log.info("Transition grid->single: grid players released")
        self.viewer_stack.setCurrentWidget(self.video_frame)
        self._view_mode = "single"
        self.settings.setValue("view_mode", "single")
        self.pause_btn.setText("Pause")
        if self.current_index >= 0 and self.streams and self.backend:
            stream = self.streams[self.current_index]
            self.stream_title.setText(stream.name)
            self.status_text.setText("Connecting…")
            self.status_badge.setText("Connecting")
            log.debug("Transition grid->single: reattaching primary video host hwnd=%s", int(self.video_frame.winId()))
            self.backend.attach_video(int(self.video_frame.winId()))
            self.backend.play(stream.url)
            self.pause_btn.setEnabled(True)
            self.mute_btn.setEnabled(True)
        else:
            self.stream_title.setText("Choose a camera")
            self.status_text.setText("Choose a camera")
            self.status_badge.setText("Idle")
        self._set_view_button_state()
        self._update_nav_buttons()
        log.info("Transition grid->single complete")

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
        if rows * columns > MAX_GRID_TILES:
            rows, columns = 2, 2
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
        log.info("Update check requested silent=%s", silent)
        if self._update_check_thread and self._update_check_thread.isRunning():
            if not silent:
                self.status_text.setText("Already checking for updates…")
            return

        if not silent:
            self.status_text.setText("Checking for updates…")

        thread = UpdateCheckThread(self)
        self._update_check_thread = thread

        def finished(available: bool, error: str) -> None:
            log.info("Update check callback available=%s error=%r", available, error)
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
        log.info("Update download requested")
        if self._update_download_thread and self._update_download_thread.isRunning():
            return

        self.status_text.setText("Downloading update… 0%")
        thread = UpdateDownloadThread(self)
        self._update_download_thread = thread
        thread.progress.connect(lambda value: self.status_text.setText(f"Downloading update… {value}%"))

        def finished(ok: bool, error: str) -> None:
            log.info("Update download callback ok=%s error=%r", ok, error)
            if not ok:
                QMessageBox.warning(self, "Update failed", error or "The update could not be downloaded.")
                self.status_text.setText("Update failed")
                return

            self.status_text.setText("Update downloaded — restart required")
            answer = QMessageBox.question(
                self,
                "Update downloaded",
                "The update has been downloaded successfully.\n\n"
                "Install the update and automatically reopen RelayView?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

            # Velopack's external updater waits for this process to exit, then
            # applies the package and relaunches the installed application.
            self.settings.setValue("geometry", self.saveGeometry())
            self._save_grid_state()
            self.settings.sync()
            if self.backend:
                log.info("Shutting down backend before update-close handoff")
                self.backend.shutdown()
                log.info("Backend shutdown returned before update-close handoff")

            try:
                handoff_update_and_restart()
            except Exception as exc:
                log.exception("Unable to launch external updater")
                QMessageBox.warning(self, "Update installation failed", str(exc) + "\n\nRelayView will remain open.")
                self.status_text.setText("Update ready — install failed")
                return
            self.status_text.setText("Installing update — RelayView will reopen…")
            log.warning("Exiting for Velopack update and automatic restart")
            QTimer.singleShot(0, QApplication.instance().quit)

        thread.downloaded.connect(finished)
        thread.start()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        log.info("MainWindow closeEvent view_mode=%s grid=%sx%s", self._view_mode, self.grid_view.rows, self.grid_view.columns)
        self.settings.setValue("geometry", self.saveGeometry())
        self._save_grid_state()
        if self.backend:
            log.info("closeEvent: VLC backend shutdown begin")
            self.backend.shutdown()
            log.info("closeEvent: VLC backend shutdown returned")
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
