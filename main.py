from __future__ import annotations

import sys

# Playback workers deliberately bypass Velopack and Qt. In packaged builds the
# same RelayView.exe is reused as a hidden child process, keeping deployment small.
if "--player-worker" in sys.argv:
    from relayview.player_worker import run_worker
    raise SystemExit(run_worker())

import velopack

from relayview.diagnostics import enable_crash_logging
from relayview.logging_config import get_logger, install_exception_hook, set_log_level, setup_logging

setup_logging("ERROR")
install_exception_hook()
log = get_logger("startup")
crash_path = enable_crash_logging()
log.debug("Process starting argv=%r crash_log=%s", sys.argv, crash_path)

try:
    log.debug("Entering Velopack bootstrap")
    velopack.App().run()
    log.debug("Velopack bootstrap complete")
except Exception:
    log.exception("Velopack bootstrap failed")
    raise

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from relayview.main_window import MainWindow  # noqa: E402
from relayview.theme import APP_STYLE  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("RelayView")
    app.setOrganizationName("RelayView")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)

    settings = QSettings("RelayView", "RelayView")
    saved_level = str(settings.value("log_level", "ERROR")).upper()
    set_log_level(saved_level)
    log.info("Qt application initialised log_level=%s", saved_level)

    window = MainWindow()
    window.show()
    rc = app.exec()
    log.info("Qt event loop exited rc=%s", rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
