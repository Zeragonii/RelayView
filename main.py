from __future__ import annotations

import sys

import velopack

# Velopack must run before normal application startup. It may handle an install/update
# event and exit/restart the process before Qt is initialised.
velopack.App().run()

from PySide6.QtWidgets import QApplication  # noqa: E402

from relayview.main_window import MainWindow  # noqa: E402
from relayview.theme import APP_STYLE  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("RelayView")
    app.setOrganizationName("RelayView")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
