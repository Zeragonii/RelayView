from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .build_info import REPOSITORY_URL
from .logging_config import get_logger

log = get_logger("updater")


class UpdateCheckThread(QThread):
    finished_check = Signal(bool, str)

    def run(self) -> None:
        log.debug("Update check thread started repository=%s", REPOSITORY_URL or "<unset>")
        if not REPOSITORY_URL:
            message = "Update source is only configured in packaged GitHub builds."
            log.error(message)
            self.finished_check.emit(False, message)
            return
        try:
            import velopack
            log.debug("Creating Velopack UpdateManager")
            manager = velopack.UpdateManager(REPOSITORY_URL)
            update = manager.check_for_updates()
            log.info("Update check complete available=%s update=%r", bool(update), update)
            self.finished_check.emit(bool(update), "")
        except Exception as exc:  # pragma: no cover - network/platform specific
            log.exception("Update check failed")
            self.finished_check.emit(False, str(exc))


class UpdateDownloadThread(QThread):
    progress = Signal(int)
    downloaded = Signal(bool, str)

    def run(self) -> None:
        log.debug("Update download thread started repository=%s", REPOSITORY_URL or "<unset>")
        if not REPOSITORY_URL:
            message = "Update source is not configured."
            log.error(message)
            self.downloaded.emit(False, message)
            return
        try:
            import velopack
            manager = velopack.UpdateManager(REPOSITORY_URL)
            log.debug("Rechecking for update before download")
            update = manager.check_for_updates()
            if not update:
                message = "No update is available anymore."
                log.warning(message)
                self.downloaded.emit(False, message)
                return

            def report(value: int) -> None:
                ivalue = int(value)
                log.debug("Update download progress=%s%%", ivalue)
                self.progress.emit(ivalue)

            log.info("Downloading update update=%r", update)
            manager.download_updates(update, report)
            log.info("Update download completed")
            self.downloaded.emit(True, "")
        except Exception as exc:  # pragma: no cover - network/platform specific
            log.exception("Update download failed")
            self.downloaded.emit(False, str(exc))


def handoff_update_and_restart() -> None:
    """Spawn Velopack's external updater, wait for our exit, then relaunch.

    Must be called on the main GUI thread after state is saved. The process
    must quit promptly after this call (Velopack waits up to 60 seconds).
    """
    if not REPOSITORY_URL:
        raise RuntimeError("Update source is not configured for this build")
    import velopack
    manager = velopack.UpdateManager(REPOSITORY_URL)
    pending = manager.get_update_pending_restart()
    if pending is None:
        raise RuntimeError("No downloaded update is pending installation")
    manager.wait_exit_then_apply_updates(pending, silent=False, restart=True)
    log.info("External Velopack updater launched; application will exit")
