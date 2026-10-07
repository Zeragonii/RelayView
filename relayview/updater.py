from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .build_info import REPOSITORY_URL


class UpdateCheckThread(QThread):
    finished_check = Signal(bool, str)

    def run(self) -> None:
        if not REPOSITORY_URL:
            self.finished_check.emit(False, "Update source is only configured in packaged GitHub builds.")
            return
        try:
            import velopack
            manager = velopack.UpdateManager(REPOSITORY_URL)
            update = manager.check_for_updates()
            self.finished_check.emit(bool(update), "")
        except Exception as exc:  # pragma: no cover - network/platform specific
            self.finished_check.emit(False, str(exc))


class UpdateDownloadThread(QThread):
    progress = Signal(int)
    downloaded = Signal(bool, str)

    def run(self) -> None:
        if not REPOSITORY_URL:
            self.downloaded.emit(False, "Update source is not configured.")
            return
        try:
            import velopack
            manager = velopack.UpdateManager(REPOSITORY_URL)
            update = manager.check_for_updates()
            if not update:
                self.downloaded.emit(False, "No update is available anymore.")
                return
            manager.download_updates(update, lambda value: self.progress.emit(int(value)))
            self.downloaded.emit(True, "")
        except Exception as exc:  # pragma: no cover - network/platform specific
            self.downloaded.emit(False, str(exc))


def apply_pending_update() -> None:
    """Exit RelayView, apply the already-downloaded update, then restart.

    Velopack's Python binding provides apply_updates_and_restart() for exactly
    this flow. Using wait_exit_then_apply_updates() from the GUI thread can
    deadlock if the application waits for that call to return before exiting.
    """
    if not REPOSITORY_URL:
        raise RuntimeError("Update source is not configured.")

    import velopack
    manager = velopack.UpdateManager(REPOSITORY_URL)
    pending = manager.get_update_pending_restart()
    if pending is None:
        raise RuntimeError("The downloaded update could not be found.")

    # This helper terminates the current app, applies the update and relaunches
    # RelayView. It avoids the wait-for-exit handoff used by the C/C++ API.
    manager.apply_updates_and_restart(pending)
