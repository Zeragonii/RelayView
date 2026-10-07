from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from relayview.main_window import MainWindow
from relayview.theme import APP_STYLE


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
