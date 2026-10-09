from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QMimeData, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QDrag, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .zoom import ZoomState
from .windows_mouse_bridge import WindowsMouseBridge
from .models import Stream
from .mpv_backend import MPVBackend, MPVPlayer
from .logging_config import get_logger, redact_url

log = get_logger("grid")

GRID_MIME = "application/x-relayview-grid-tile"
MAX_GRID_TILES = 64  # A practical guardrail against accidentally launching hundreds of mpv processes.


def _prepare_windows_video_host(widget: QWidget) -> int:
    """Return a libmpv-safe native HWND for a Qt video host on Windows."""
    hwnd = int(widget.winId())
    log.debug("Preparing video host widget=%s hwnd=%s platform=%s", id(widget), hwnd, sys.platform)
    if not sys.platform.startswith("win"):
        return hwnd

    # libmpv documents WS_CLIPCHILDREN as required for set_hwnd().
    # WS_CLIPSIBLINGS is also appropriate for a tiled child-window layout.
    import ctypes

    GWL_STYLE = -16
    WS_CLIPCHILDREN = 0x02000000
    WS_CLIPSIBLINGS = 0x04000000
    user32 = ctypes.windll.user32
    get_style = user32.GetWindowLongPtrW
    set_style = user32.SetWindowLongPtrW
    get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
    get_style.restype = ctypes.c_ssize_t
    set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    set_style.restype = ctypes.c_ssize_t
    style = get_style(hwnd, GWL_STYLE)
    required = WS_CLIPCHILDREN | WS_CLIPSIBLINGS
    if (style & required) != required:
        log.debug("Applying HWND styles hwnd=%s old_style=0x%x required=0x%x", hwnd, style, required)
        set_style(hwnd, GWL_STYLE, style | required)
    else:
        log.debug("HWND styles already valid hwnd=%s style=0x%x", hwnd, style)
    return hwnd


class GridSizeDialog(QDialog):
    def __init__(self, rows: int, columns: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure grid")
        self.setModal(True)
        self.setMinimumWidth(340)

        layout = QVBoxLayout(self)
        intro = QLabel("Choose the number of rows and columns for the camera grid.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        form.addWidget(QLabel("Rows"), 0, 0)
        self.rows = QSpinBox()
        self.rows.setRange(1, 32)
        self.rows.setValue(max(1, rows))
        form.addWidget(self.rows, 0, 1)

        form.addWidget(QLabel("Columns"), 1, 0)
        self.columns = QSpinBox()
        self.columns.setRange(1, 32)
        self.columns.setValue(max(1, columns))
        form.addWidget(self.columns, 1, 1)

        self.preview = QLabel()
        self.preview.setObjectName("subtle")
        form.addWidget(self.preview, 2, 0, 1, 2)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.rows.valueChanged.connect(self._update_preview)
        self.columns.valueChanged.connect(self._update_preview)
        self._update_preview()

    def _update_preview(self) -> None:
        cells = self.rows.value() * self.columns.value()
        self.preview.setText(f"{self.rows.value()} × {self.columns.value()} · {cells} camera tiles" + (f" (maximum {MAX_GRID_TILES})" if cells > MAX_GRID_TILES else ""))
        self.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).setEnabled(cells <= MAX_GRID_TILES)

    def dimensions(self) -> tuple[int, int]:
        return self.rows.value(), self.columns.value()


class GridTile(QFrame):
    clicked = Signal(int)
    swap_requested = Signal(int, int)
    zoom_changed = Signal(int)

    def __init__(self, index: int, parent=None) -> None:
        super().__init__(parent)
        self.index = index
        self.stream: Stream | None = None
        self.player: MPVPlayer | None = None
        self._drag_start = QPoint()
        self._pan_start = QPoint()
        self.zoom = ZoomState()

        self.setObjectName("gridTile")
        self.setProperty("active", False)
        self.setAcceptDrops(True)
        self.setMinimumSize(80, 60)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        # Exactly one fixed native HWND per tile. libmpv scales/crops the *image*
        # internally using video-zoom and video-align-x/y. Never resize or move
        # an oversized QWidget to zoom; that caused letterboxing and jitter.
        self.video = QFrame(objectName="gridVideo")
        self.video.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.video.setMinimumSize(60, 40)
        layout.addWidget(self.video, 1)
        self.video.installEventFilter(self)

        footer = QFrame(objectName="gridTileFooter")
        # Footer must receive mouse events: Qt otherwise disables its +/- buttons.
        footer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        footer_l = QHBoxLayout(footer)
        footer_l.setContentsMargins(9, 5, 9, 5)
        footer_l.setSpacing(6)
        self.title = QLabel("Empty tile", objectName="gridTileTitle")
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        footer_l.addWidget(self.title, 1)
        self.health_label = QLabel("", objectName="gridTileIndex")
        self.health_label.setToolTip("Playback status")
        footer_l.addWidget(self.health_label)
        self.position_label = QLabel(str(index + 1), objectName="gridTileIndex")
        footer_l.addWidget(self.position_label)
        self.zoom_label = QLabel("", objectName="gridTileIndex")
        footer_l.addWidget(self.zoom_label)
        self.zoom_out_button = QToolButton()
        self.zoom_out_button.setText("−")
        self.zoom_out_button.setToolTip("Zoom out this camera")
        self.zoom_out_button.clicked.connect(lambda: self.zoom_by(-1))
        footer_l.addWidget(self.zoom_out_button)
        self.zoom_in_button = QToolButton()
        self.zoom_in_button.setText("+")
        self.zoom_in_button.setToolTip("Zoom in this camera")
        self.zoom_in_button.clicked.connect(lambda: self.zoom_by(1))
        footer_l.addWidget(self.zoom_in_button)
        # Always-Qt fallback for diagnosing a native middle-mouse issue.
        # Only appears while zoomed, so an ordinary grid stays uncluttered.
        self.pan_button = QToolButton()
        self.pan_button.setText("✥")
        self.pan_button.setToolTip("Pan zoomed video — useful if middle dragging is unavailable")
        self.pan_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        pan_menu = QMenu(self.pan_button)
        pan_menu.addAction("Pan left", lambda: self.pan_by(-0.2, 0))
        pan_menu.addAction("Pan right", lambda: self.pan_by(0.2, 0))
        pan_menu.addAction("Pan up", lambda: self.pan_by(0, -0.2))
        pan_menu.addAction("Pan down", lambda: self.pan_by(0, 0.2))
        pan_menu.addSeparator()
        pan_menu.addAction("Reset position", self.reset_pan)
        self.pan_button.setMenu(pan_menu)
        footer_l.addWidget(self.pan_button)
        self.pan_button.hide()
        layout.addWidget(footer)

    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def set_stream_label(self, stream: Stream | None) -> None:
        self.stream = stream
        self.title.setText(stream.name if stream else "Empty tile")
        self.health_label.setText("Connecting" if stream else "")
        self.setToolTip(stream.url if stream else "Select this tile, then choose a camera")
        self.zoom.reset()
        self._update_zoom()

    def _update_zoom(self) -> None:
        self.zoom_label.setText(f"{self.zoom.factor:g}×" if self.zoom.factor > 1 else "")
        self.pan_button.setVisible(self.zoom.factor > 1)
        if self.player is not None:
            self.player.set_zoom(self.zoom.factor, self.zoom.cx, self.zoom.cy)
        self.zoom_changed.emit(self.index)

    def zoom_by(self, steps: int) -> None:
        if self.stream:
            previous = self.zoom.factor
            self.zoom.change(steps)
            if self.zoom.factor == previous:
                return
            log.info("Tile zoom input tile=%s old=%.2f new=%.2f source=control", self.index, previous, self.zoom.factor)
            self._update_zoom()

    def reset_zoom(self) -> None:
        self.zoom.reset()
        self._update_zoom()

    def pan_by(self, dx: float, dy: float) -> None:
        if self.stream and self.zoom.factor > 1:
            before = (self.zoom.cx, self.zoom.cy)
            self.zoom.move(dx, dy)
            log.info("Manual pan tile=%s from=%s to=(%.3f, %.3f)",
                     self.index, before, self.zoom.cx, self.zoom.cy)
            self._update_zoom()

    def reset_pan(self) -> None:
        if self.stream and self.zoom.factor > 1:
            self.zoom.cx = 0.5
            self.zoom.cy = 0.5
            self._update_zoom()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if (obj is getattr(self, "video", None) and event.type() == QEvent.Type.Wheel
                and not sys.platform.startswith("win")):
            self.zoom_by(1 if event.angleDelta().y() > 0 else -1)
            return True
        return super().eventFilter(obj, event)

    def wheelEvent(self, event) -> None:  # noqa: N802
        self.zoom_by(1 if event.angleDelta().y() > 0 else -1)
        event.accept()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        menu.addAction("Zoom in", lambda: self.zoom_by(1))
        menu.addAction("Zoom out", lambda: self.zoom_by(-1))
        menu.addAction("Reset zoom", self.reset_zoom)
        if self.zoom.factor > 1:
            menu.addSeparator()
            menu.addAction("Pan left", lambda: self.pan_by(-0.2, 0))
            menu.addAction("Pan right", lambda: self.pan_by(0.2, 0))
            menu.addAction("Pan up", lambda: self.pan_by(0, -0.2))
            menu.addAction("Pan down", lambda: self.pan_by(0, 0.2))
        menu.exec(event.globalPos())

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton and not sys.platform.startswith("win"):
            self._pan_start = event.position().toPoint()
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
            self.clicked.emit(self.index)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if (event.buttons() & Qt.MouseButton.MiddleButton) and not sys.platform.startswith("win"):
            # Windows video tiles use a polled, physical button state instead.
            # Never let both Qt and Windows independently pan the same tile.
            pos = event.position().toPoint()
            delta = pos - self._pan_start
            self._pan_start = pos
            self.pan_by(-delta.x() / max(1, self.video.width()), -delta.y() / max(1, self.video.height()))
            event.accept()
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return super().mouseMoveEvent(event)
        if self.stream is None:
            return super().mouseMoveEvent(event)
        distance = (event.position().toPoint() - self._drag_start).manhattanLength()
        if distance < QApplication.startDragDistance():
            return super().mouseMoveEvent(event)

        mime = QMimeData()
        mime.setData(GRID_MIME, str(self.index).encode("ascii"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(GRID_MIME):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        try:
            source = int(bytes(event.mimeData().data(GRID_MIME)).decode("ascii"))
        except (TypeError, ValueError):
            return
        if source != self.index:
            self.swap_requested.emit(source, self.index)
        event.acceptProposedAction()


class GridView(QWidget):
    active_changed = Signal(int)
    assignments_changed = Signal()

    def __init__(self, backend: MPVBackend | None, parent=None) -> None:
        super().__init__(parent)
        self.backend = backend
        self.rows = 2
        self.columns = 2
        self.tiles: list[GridTile] = []
        self.active_index = 0
        self._volume = 100
        self._muted = False
        self._paused = False
        self._generation = 0

        self.layout_grid = QGridLayout(self)
        self.layout_grid.setContentsMargins(0, 0, 0, 0)
        self.layout_grid.setSpacing(8)
        log.debug("GridView init backend=%s", bool(backend))
        self.configure(2, 2, [])
        self._native_mouse = WindowsMouseBridge(self)

    def configure(self, rows: int, columns: int, streams: list[Stream | None]) -> None:
        rows = max(1, int(rows))
        columns = max(1, int(columns))
        if rows * columns > MAX_GRID_TILES:
            raise ValueError(f"Grid exceeds the {MAX_GRID_TILES}-tile safety limit")
        if self.tiles and rows == self.rows and columns == self.columns:
            # Preserve native HWNDs and the mpv processes when only assignments change.
            if streams is not None:
                changed = False
                for index, tile in enumerate(self.tiles):
                    replacement = streams[index] if index < len(streams) else None
                    if (tile.stream.url if tile.stream else None) != (replacement.url if replacement else None):
                        self.assign_stream(index, replacement)
                        changed = True
                if changed:
                    self.assignments_changed.emit()
            return
        log.info("Grid configure requested rows=%s columns=%s incoming_assignments=%s current_tiles=%s generation=%s", rows, columns, len(streams), len(self.tiles), self._generation)
        # Invalidate any deferred startup callbacks from the previous grid.
        self._generation += 1
        log.debug("Grid generation advanced to %s", self._generation)

        old_rows = self.rows
        old_columns = self.columns
        old_streams = [tile.stream for tile in self.tiles]
        if streams is not None:
            old_streams = list(streams)

        for tile in self.tiles:
            log.debug("Destroying tile index=%s player=%s stream=%s", tile.index, id(tile.player) if tile.player else None, redact_url(tile.stream.url) if tile.stream else None)
            if tile.player and self.backend:
                self.backend.release_player(tile.player)
            self.layout_grid.removeWidget(tile)
            tile.deleteLater()

        for row in range(max(old_rows, rows)):
            self.layout_grid.setRowStretch(row, 0)
        for column in range(max(old_columns, columns)):
            self.layout_grid.setColumnStretch(column, 0)

        self.rows = rows
        self.columns = columns
        self.tiles = []
        count = rows * columns

        for index in range(count):
            tile = GridTile(index, self)
            log.debug("Created grid tile index=%s widget=%s video_widget=%s", index, id(tile), id(tile.video))
            tile.clicked.connect(self.set_active)
            tile.swap_requested.connect(self.swap_tiles)
            tile.zoom_changed.connect(self._update_tile_zoom)
            self.tiles.append(tile)
            self.layout_grid.addWidget(tile, index // columns, index % columns)
            if index < len(old_streams):
                tile.set_stream_label(old_streams[index])

        for row in range(rows):
            self.layout_grid.setRowStretch(row, 1)
        for column in range(columns):
            self.layout_grid.setColumnStretch(column, 1)

        self.set_active(min(self.active_index, count - 1))
        log.info("Grid configure complete rows=%s columns=%s tiles=%s generation=%s", self.rows, self.columns, len(self.tiles), self._generation)
        self.assignments_changed.emit()

    def _update_tile_zoom(self, index: int) -> None:
        if 0 <= index < len(self.tiles):
            tile = self.tiles[index]
            log.debug("libmpv zoom tile=%s factor=%.2f center=(%.3f, %.3f)",
                      index, tile.zoom.factor, tile.zoom.cx, tile.zoom.cy)

    def _ensure_player(self, tile: GridTile) -> MPVPlayer | None:
        if not self.backend:
            return None
        if tile.player is None:
            log.debug("Allocating player for tile=%s", tile.index)
            def update_tile_health(status: str, target=tile) -> None:
                # Called by the Qt watchdog, not from the worker's stdout thread.
                if target in self.tiles and target.stream:
                    compact = status.replace("…", "").split(" — ")[0]
                    target.health_label.setText(compact)
                    target.health_label.setToolTip(status)
            tile.player = self.backend.create_player(update_tile_health)
            tile.player.set_volume(self._volume)
            tile.player.set_muted(self._muted)
        return tile.player

    def _start_assigned_players(self, generation: int | None = None) -> None:
        if generation is not None and generation != self._generation:
            return
        if not self.isVisible():
            return
        for tile in list(self.tiles):
            if tile.stream:
                self._start_tile(tile, generation)

    def _start_tile(self, tile: GridTile, generation: int | None = None) -> None:
        if generation is not None and generation != self._generation:
            log.debug("Skipping stale tile start tile=%s callback_generation=%s current_generation=%s", getattr(tile, "index", None), generation, self._generation)
            return
        if tile not in self.tiles or not tile.stream or not self.isVisible():
            log.debug("Skipping tile start tile=%s in_tiles=%s has_stream=%s visible=%s", getattr(tile, "index", None), tile in self.tiles, bool(getattr(tile, "stream", None)), self.isVisible())
            return
        player = self._ensure_player(tile)
        if not player:
            return
        # Keep one stable native HWND per tile; mpv owns only its internal image transform.
        hwnd = _prepare_windows_video_host(tile.video)
        log.info("Starting grid tile=%s player=%s hwnd=%s stream=%s", tile.index, id(player), hwnd, redact_url(tile.stream.url))
        if (getattr(player, "_current_url", None) == tile.stream.url
                and getattr(player, "_enabled", False)):
            # Existing supervisor owns this feed; avoid killing a healthy worker
            # when opening the same grid or restoring an unchanged profile.
            return
        player.attach_video(hwnd)
        player.set_zoom(tile.zoom.factor, tile.zoom.cx, tile.zoom.cy)
        player.play(tile.stream.url)
        player.set_volume(self._volume)
        player.set_muted(self._muted)
        if self._paused:
            player.set_paused(True)

    def set_active(self, index: int) -> None:
        if not self.tiles:
            return
        index = max(0, min(index, len(self.tiles) - 1))
        self.active_index = index
        for i, tile in enumerate(self.tiles):
            tile.set_active(i == index)
        self.active_changed.emit(index)

    def assign_stream(self, index: int, stream: Stream | None) -> None:
        log.info("Assign stream tile=%s stream=%s", index, redact_url(stream.url) if stream else None)
        if not (0 <= index < len(self.tiles)):
            return
        tile = self.tiles[index]
        if (tile.stream.url if tile.stream else None) == (stream.url if stream else None):
            # No-op assignment must not restart a healthy worker.
            return
        tile.set_stream_label(stream)
        if stream is None:
            if tile.player:
                tile.player.stop()
            self.assignments_changed.emit()
            return

        if self.isVisible():
            player = self._ensure_player(tile)
            if player:
                player.attach_video(_prepare_windows_video_host(tile.video))
                player.set_zoom(tile.zoom.factor, tile.zoom.cx, tile.zoom.cy)
                player.play(stream.url)
                player.set_volume(self._volume)
                player.set_muted(self._muted)
        self.assignments_changed.emit()

    def swap_tiles(self, source: int, target: int) -> None:
        """Move the existing QWidget/video host, not the stream or mpv process.

        libmpv remains attached to each tile's original HWND. Swapping assignments
        would tear down both decoders and cause visible reconnection delays.
        """
        if not (0 <= source < len(self.tiles) and 0 <= target < len(self.tiles)) or source == target:
            return
        first, second = self.tiles[source], self.tiles[target]
        self.layout_grid.removeWidget(first)
        self.layout_grid.removeWidget(second)
        self.layout_grid.addWidget(first, target // self.columns, target % self.columns)
        self.layout_grid.addWidget(second, source // self.columns, source % self.columns)
        self.tiles[source], self.tiles[target] = second, first
        first.index, second.index = target, source
        first.position_label.setText(str(target + 1))
        second.position_label.setText(str(source + 1))
        self.set_active(target)
        self.assignments_changed.emit()

    def stream_assignments(self) -> list[Stream | None]:
        return [tile.stream for tile in self.tiles]

    def urls(self) -> list[str]:
        return [tile.stream.url if tile.stream else "" for tile in self.tiles]

    def play_all(self) -> None:
        log.info("Grid play_all rows=%s columns=%s assigned=%s generation=%s", self.rows, self.columns, sum(1 for t in self.tiles if t.stream), self._generation)
        self._paused = False
        generation = self._generation
        # Defer startup until after QStackedWidget has shown the grid and native
        # video child windows have valid handles. Staggering avoids a decoder/RTSP
        # stampede when opening large grids.
        for offset, tile in enumerate(list(self.tiles)):
            if tile.stream:
                QTimer.singleShot(75 + (offset * 35), lambda t=tile, g=generation: self._start_tile(t, g))

    def stop_all(self) -> None:
        log.info("Grid stop_all begin tiles=%s generation=%s", len(self.tiles), self._generation)
        self._generation += 1
        for tile in self.tiles:
            if tile.player:
                log.debug("Grid tile stop begin tile=%s player=%s", tile.index, id(tile.player))
                tile.player.stop(detach=True)
                log.debug("Grid tile stop complete tile=%s player=%s", tile.index, id(tile.player))
        log.info("Grid stop_all complete generation=%s", self._generation)

    def release_all_players(self) -> None:
        log.info("Grid release_all_players begin tiles=%s generation=%s", len(self.tiles), self._generation)
        self._generation += 1
        for tile in self.tiles:
            if tile.player and self.backend:
                player = tile.player
                tile.player = None
                log.debug("Grid tile release begin tile=%s player=%s", tile.index, id(player))
                self.backend.release_player(player)
                log.debug("Grid tile release complete tile=%s player=%s", tile.index, id(player))
        log.info("Grid release_all_players complete generation=%s", self._generation)

    def toggle_pause_all(self) -> bool:
        self._paused = not self._paused
        for tile in self.tiles:
            if tile.player and tile.stream:
                tile.player.set_paused(self._paused)
        return self._paused

    def set_volume(self, value: int) -> None:
        self._volume = max(0, min(100, int(value)))
        for tile in self.tiles:
            if tile.player:
                tile.player.set_volume(self._volume)

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        for tile in self.tiles:
            if tile.player:
                tile.player.set_muted(self._muted)

    def is_muted(self) -> bool:
        return self._muted
