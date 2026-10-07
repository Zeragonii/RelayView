APP_STYLE = r"""
* {
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 10pt;
}
QMainWindow, QWidget#root, QDialog {
    background: #0b0e14;
    color: #e8edf5;
}
QFrame#sidebar {
    background: #10151e;
    border-right: 1px solid #202938;
}
QLabel#brand {
    font-size: 18pt;
    font-weight: 700;
    color: #f4f7fb;
}
QLabel#subtle, QLabel#statusText {
    color: #8794a8;
}
QLineEdit, QTextEdit {
    background: #161d28;
    border: 1px solid #263142;
    border-radius: 10px;
    padding: 9px 11px;
    color: #eaf0f8;
    selection-background-color: #4c7dff;
}
QLineEdit:focus, QTextEdit:focus { border: 1px solid #4c7dff; }
QLabel#dialogTitle {
    font-size: 16pt;
    font-weight: 700;
    color: #f4f7fb;
}
QCheckBox { color: #dbe4f0; spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; }
QListWidget#playlistEditorList::item { padding: 10px; }
QListWidget {
    background: transparent;
    border: none;
    outline: none;
    padding: 4px;
}
QListWidget::item {
    border-radius: 9px;
    padding: 11px 10px;
    margin: 2px 0;
    color: #b8c2d1;
}
QListWidget::item:hover { background: #182130; color: #ffffff; }
QListWidget::item:selected { background: #20304b; color: #ffffff; }
QFrame#videoFrame {
    background: #020304;
    border: 1px solid #1d2634;
    border-radius: 14px;
}
QFrame#topBar, QFrame#controlBar {
    background: #10151ecc;
    border: 1px solid #202938;
    border-radius: 12px;
}
QPushButton {
    background: #171f2b;
    color: #dbe4f0;
    border: 1px solid #273346;
    border-radius: 9px;
    padding: 8px 12px;
    min-height: 18px;
}
QPushButton:hover { background: #202b3b; border-color: #35445b; }
QPushButton:pressed { background: #111721; }
QPushButton#primaryButton {
    background: #4c7dff;
    border-color: #4c7dff;
    color: white;
    font-weight: 600;
}
QPushButton#primaryButton:hover { background: #5a87ff; }
QPushButton#iconButton { min-width: 35px; padding: 7px; }

QPushButton#cameraToggleButton {
    background: transparent;
    border: 1px solid #273346;
    padding: 6px 10px;
}
QPushButton#cameraToggleButton:hover { background: #182130; }
QLabel#volumeLabel {
    color: #8794a8;
    font-size: 9pt;
}
QSlider#volumeSlider::groove:horizontal {
    height: 4px;
    background: #273346;
    border-radius: 2px;
}
QSlider#volumeSlider::sub-page:horizontal {
    background: #4c7dff;
    border-radius: 2px;
}
QSlider#volumeSlider::handle:horizontal {
    width: 14px;
    height: 14px;
    margin: -5px 0;
    background: #e8edf5;
    border: 2px solid #4c7dff;
    border-radius: 7px;
}
QSlider#volumeSlider::handle:horizontal:hover { background: #ffffff; }

QPushButton#viewModeButton {
    background: transparent;
    border: 1px solid #273346;
    padding: 6px 10px;
}
QPushButton#viewModeButton:hover { background: #182130; }
QPushButton#viewModeButton[active="true"] {
    background: #20304b;
    border-color: #4c7dff;
    color: #ffffff;
}
QFrame#gridTile {
    background: #070a0f;
    border: 1px solid #202938;
    border-radius: 10px;
}
QFrame#gridTile[active="true"] {
    border: 2px solid #4c7dff;
}
QFrame#gridVideo { background: #020304; border: none; }
QFrame#gridTileFooter {
    background: #10151e;
    border: none;
    border-top: 1px solid #202938;
}
QLabel#gridTileTitle {
    color: #dbe4f0;
    font-size: 9pt;
    font-weight: 600;
}
QLabel#gridTileIndex {
    color: #738197;
    font-size: 8pt;
}
QSpinBox {
    background: #161d28;
    border: 1px solid #263142;
    border-radius: 8px;
    padding: 7px 9px;
    color: #eaf0f8;
}

QLabel#streamTitle { font-size: 13pt; font-weight: 650; color: white; }
QLabel#liveBadge {
    color: #9df7be;
    background: #12351f;
    border: 1px solid #245c37;
    border-radius: 8px;
    padding: 4px 8px;
    font-weight: 600;
}
QMenu {
    background: #151b25;
    color: #e5ebf4;
    border: 1px solid #2a3546;
    padding: 5px;
}
QMenu::item { padding: 7px 24px 7px 10px; border-radius: 6px; }
QMenu::item:selected { background: #243149; }
QScrollBar:vertical { width: 9px; background: transparent; }
QScrollBar::handle:vertical { background: #2d394b; min-height: 30px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
"""
