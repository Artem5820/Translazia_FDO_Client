APP_STYLESHEET = """
QWidget {
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
    color: #102033;
}
QMainWindow, QDialog {
    background: #f3f7ff;
}
#brandHeader, #brandHeaderCompact {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0635b8, stop:0.55 #075fe8, stop:1 #0b7cff);
    border: 1px solid #0a48c7;
    border-radius: 8px;
}
#brandLogo, #brandLogoCompact {
    background: transparent;
    border: 0;
    border-radius: 8px;
}
#brandTitleLabel {
    font-size: 24px;
    font-weight: 800;
    color: #ffffff;
}
#brandSubtitleLabel {
    color: #dceaff;
    font-size: 13px;
}
#titleLabel {
    font-size: 24px;
    font-weight: 700;
    color: #0a2f83;
}
#subtitleLabel {
    color: #557099;
}
#panelTitle {
    font-size: 15px;
    font-weight: 800;
    color: #0e347f;
}
QPushButton, QToolButton {
    border: 1px solid #b9c9e6;
    border-radius: 7px;
    padding: 8px 12px;
    background: #ffffff;
    color: #102033;
}
QPushButton:hover, QToolButton:hover {
    background: #eef5ff;
    border-color: #1d67d8;
    color: #073ca8;
}
QPushButton:pressed, QToolButton:pressed {
    background: #dbeaff;
}
#brandHeader QPushButton, #brandHeader QToolButton,
#brandHeaderCompact QPushButton, #brandHeaderCompact QToolButton {
    background: rgba(255, 255, 255, 0.96);
    color: #0635a8;
    border-color: rgba(255, 255, 255, 0.72);
    font-weight: 600;
}
#brandHeader QPushButton:hover, #brandHeader QToolButton:hover,
#brandHeaderCompact QPushButton:hover, #brandHeaderCompact QToolButton:hover {
    background: #ffffff;
    border-color: #ffffff;
}
#primaryButton {
    background: #ffffff;
    color: #0635b8;
    border: 1px solid #ffffff;
    font-weight: 800;
    padding: 9px 16px;
}
#primaryButton:hover {
    background: #eaf3ff;
    color: #052f96;
    border-color: #ffffff;
}
#brandHeader #primaryButton {
    background: #ffffff;
    color: #0635b8;
    border: 1px solid #ffffff;
    font-weight: 900;
    padding: 10px 18px;
}
#brandHeader #primaryButton:hover {
    background: #eaf3ff;
    color: #052f96;
    border-color: #ffffff;
}
#dangerButton {
    background: #9a2d2a;
    color: white;
    border-color: #9a2d2a;
    font-weight: 700;
}
#metricCard {
    background: #ffffff;
    border: 1px solid #d3def2;
    border-radius: 8px;
}
#metricCard[state="ok"] {
    background: #eef8ff;
    border-color: #5aa9f5;
}
#metricCard[state="warn"] {
    background: #fff7ed;
    border-color: #f2b366;
}
#metricTitle {
    color: #5a729c;
    font-size: 12px;
}
#metricValue {
    color: #0635a8;
    font-size: 19px;
    font-weight: 800;
}
#selectionCounter {
    color: #0e347f;
    font-weight: 800;
    padding: 6px 0;
}
QTableWidget {
    background: #ffffff;
    alternate-background-color: #f4f8ff;
    border: 1px solid #d3def2;
    border-radius: 8px;
    gridline-color: #dbe5f5;
}
QHeaderView::section {
    background: #e6f0ff;
    color: #0b347f;
    border: 0;
    border-right: 1px solid #cfdef3;
    padding: 8px;
    font-weight: 800;
}
QTableWidget::item {
    padding: 7px;
}
QTableWidget::item:selected {
    background: #cfe2ff;
    color: #062b7a;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTimeEdit, QTextEdit, QListWidget {
    background: #ffffff;
    border: 1px solid #c7d6ed;
    border-radius: 7px;
    padding: 6px;
    selection-background-color: #cfe2ff;
}
QTextEdit {
    color: #1b304a;
}
QTabWidget::pane {
    border: 1px solid #d3def2;
    border-radius: 8px;
    background: #ffffff;
}
QTabBar::tab {
    padding: 8px 14px;
    margin-right: 3px;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    background: #e6f0ff;
    color: #0e347f;
}
QTabBar::tab:selected {
    background: #ffffff;
    font-weight: 800;
}
#streamHeader {
    background: #0635b8;
    border-bottom: 1px solid #052778;
}
#streamRoom {
    color: white;
    font-size: 15px;
    font-weight: 800;
}
#streamStatus {
    color: #dceaff;
}
#streamHeader QToolButton {
    background: #ffffff;
    color: #0635b8;
    padding: 5px 10px;
}
#notificationBadge {
    background: #eaf3ff;
    border: 1px solid #9abcf2;
    border-radius: 7px;
    color: #073ca8;
    padding: 8px 10px;
    font-weight: 700;
}
#notificationStrip {
    background: #0635b8;
    border: 0;
}
#stripTotal, #stripErrors, #stripNeural {
    background: #ffffff;
    border-radius: 8px;
    color: #0635b8;
    font-size: 14px;
    font-weight: 900;
    padding: 6px 0;
}
#stripErrors {
    color: #9a2d2a;
}
#stripNeural {
    color: #7a4f00;
}
#stripLog {
    background: #ffffff;
    border: 1px solid #9abcf2;
    border-radius: 8px;
    color: #102033;
    font-size: 12px;
    padding: 6px;
}
QStatusBar {
    background: #f3f7ff;
    color: #557099;
}
"""
