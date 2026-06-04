from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QAction, QColor, QBrush, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..analysis import AnalysisSummary
from ..services.analysis_messages import analysis_problem_category, short_analysis_message
from ..services.client_logger import log_event
from ..config import AppSettings
from ..models import StreamRoom
from ..resources import LOGO_SMALL_PATH, app_icon


class MainWindow(QMainWindow):
    refresh_requested = Signal()
    launch_requested = Signal()
    manual_streams_requested = Signal()
    settings_requested = Signal()
    notifications_requested = Signal()
    vk_login_requested = Signal()
    vk_auth_check_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.streams: list[StreamRoom] = []
        self.setWindowTitle("ФДО Онлайн | Translazia")
        self.setWindowIcon(app_icon())
        self.resize(1180, 760)
        self._build_ui()
        self._setup_tray()
        self._install_actions()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)

        header_frame = QFrame()
        header_frame.setObjectName("brandHeader")
        header = QHBoxLayout(header_frame)
        header.setContentsMargins(16, 14, 16, 14)
        header.setSpacing(14)
        logo = QLabel()
        logo.setObjectName("brandLogo")
        logo.setFixedSize(74, 74)
        pixmap = QPixmap(str(LOGO_SMALL_PATH))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(68, 68, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(logo)

        title_box = QVBoxLayout()
        title = QLabel("Онлайн трансляции ФДО")
        title.setObjectName("brandTitleLabel")
        subtitle = QLabel("Факультет дистанционного образования | мониторинг вечерних занятий")
        subtitle.setObjectName("brandSubtitleLabel")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)

        self.refresh_btn = QPushButton("Обновить расписание")
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        self.launch_btn = QPushButton("Запустить трансляции")
        self.launch_btn.setObjectName("primaryButton")
        self.launch_btn.clicked.connect(self.launch_requested.emit)
        self.notifications_btn = QPushButton("Уведомления")
        self.notifications_btn.clicked.connect(self.notifications_requested.emit)
        self.vk_login_btn = QPushButton("VK вход")
        self.vk_login_btn.clicked.connect(self.vk_login_requested.emit)
        self.settings_btn = QPushButton("Настройки")
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        header.addWidget(self.launch_btn)
        header.addWidget(self.refresh_btn)
        header.addWidget(self.notifications_btn)
        header.addWidget(self.vk_login_btn)
        header.addWidget(self.settings_btn)
        root.addWidget(header_frame)

        metrics = QHBoxLayout()
        self.source_card = self._metric_card("Источник", "—")
        self.rooms_card = self._metric_card("Аудитории", "0")
        self.screens_card = self._metric_card("Мониторы", str(len(QApplication.screens())))
        self.checks_card = self._metric_card("Проверки", "—")
        self.vk_card = self._metric_card("VK", "Проверяется")
        metrics.addWidget(self.source_card)
        metrics.addWidget(self.rooms_card)
        metrics.addWidget(self.screens_card)
        metrics.addWidget(self.checks_card)
        metrics.addWidget(self.vk_card)
        root.addLayout(metrics)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        selection_bar = QHBoxLayout()
        self.selected_count_label = QLabel("Выбрано: 0")
        self.selected_count_label.setObjectName("selectionCounter")
        select_all_btn = QPushButton("Все")
        select_all_btn.clicked.connect(self.select_all_streams)
        clear_all_btn = QPushButton("Ничего")
        clear_all_btn.clicked.connect(self.clear_stream_selection)
        invert_btn = QPushButton("Инвертировать")
        invert_btn.clicked.connect(self.invert_stream_selection)
        self.manual_streams_btn = QPushButton("Ручной режим")
        self.manual_streams_btn.clicked.connect(self.manual_streams_requested.emit)
        selection_bar.addWidget(self.selected_count_label)
        selection_bar.addStretch(1)
        selection_bar.addWidget(select_all_btn)
        selection_bar.addWidget(clear_all_btn)
        selection_bar.addWidget(invert_btn)
        selection_bar.addWidget(self.manual_streams_btn)
        left_layout.addLayout(selection_bar)

        self.stream_table = QTableWidget(0, 5)
        self.stream_table.setHorizontalHeaderLabels(["", "Аудитория", "Время", "Описание", "Ссылка"])
        self.stream_table.verticalHeader().setVisible(False)
        self.stream_table.setAlternatingRowColors(True)
        self.stream_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.stream_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stream_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.stream_table.setColumnWidth(0, 42)
        self.stream_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.stream_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.stream_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.stream_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.stream_table.itemChanged.connect(lambda _: self.update_selected_count())
        left_layout.addWidget(self.stream_table, 1)
        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 0, 0, 0)
        status_title = QLabel("Журнал проверок")
        status_title.setObjectName("panelTitle")
        self.analysis_table = QTableWidget(0, 5)
        self.analysis_table.setHorizontalHeaderLabels(["Время", "Аудитория", "Статус", "Проблемы", "Фрагмент"])
        self.analysis_table.verticalHeader().setVisible(False)
        self.analysis_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.analysis_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.analysis_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.analysis_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.analysis_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.raw_log = QTextEdit()
        self.raw_log.setReadOnly(True)
        self.raw_log.setPlaceholderText("Здесь появятся сообщения клиента и результаты модулей анализа.")
        right_layout.addWidget(status_title)
        right_layout.addWidget(self.analysis_table, 2)
        right_layout.addWidget(self.raw_log, 1)
        splitter.addWidget(right_panel)
        splitter.setSizes([720, 460])
        root.addWidget(splitter, 1)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

    def _metric_card(self, title: str, value: str) -> QFrame:
        card = QFrame()
        card.setObjectName("metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        title_label = QLabel(title)
        title_label.setObjectName("metricTitle")
        value_label = QLabel(value)
        value_label.setObjectName("metricValue")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        card.value_label = value_label  # type: ignore[attr-defined]
        return card

    def _setup_tray(self) -> None:
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("ФДО Онлайн")
        self.tray.show()

    def _install_actions(self) -> None:
        refresh_action = QAction("Обновить", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.refresh_requested.emit)
        self.addAction(refresh_action)

    def update_cards(self, settings: AppSettings) -> None:
        mode = {"vk_bot": "VK-бот", "vk_web": "VK Web"}.get(settings.source.mode, "Файл")
        self.source_card.value_label.setText(mode)  # type: ignore[attr-defined]
        self.rooms_card.value_label.setText(str(len(self.streams)))  # type: ignore[attr-defined]
        checks = "выкл."
        if settings.analysis.enabled:
            checks = f"{settings.analysis.interval_minutes} мин. / {settings.analysis.duration_seconds} сек."
        self.checks_card.value_label.setText(checks)  # type: ignore[attr-defined]
        self.screens_card.value_label.setText(str(len(QApplication.screens())))  # type: ignore[attr-defined]

    def set_vk_auth_status(self, authorized: bool | None, message: str) -> None:
        self.vk_card.value_label.setText(message)  # type: ignore[attr-defined]
        state = "unknown"
        if authorized is True:
            state = "ok"
        elif authorized is False:
            state = "warn"
        self.vk_card.setProperty("state", state)
        self.vk_card.style().unpolish(self.vk_card)
        self.vk_card.style().polish(self.vk_card)

    def set_loading(self, is_loading: bool) -> None:
        self.refresh_btn.setEnabled(not is_loading)
        if is_loading:
            self.statusBar().showMessage("Загружаю расписание трансляций...")

    def set_streams(self, streams: list[StreamRoom], selected_keys: set[str] | None = None) -> None:
        self.stream_table.blockSignals(True)
        self.streams = streams
        self.stream_table.setRowCount(0)
        self.stream_table.clearSpans()
        if not self.streams:
            self.stream_table.insertRow(0)
            item = QTableWidgetItem("Занятий нет")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.stream_table.setItem(0, 0, item)
            self.stream_table.setSpan(0, 0, 1, self.stream_table.columnCount())
            self._update_empty_stream_row_height()
            self.stream_table.blockSignals(False)
            self.update_selected_count()
            return
        for stream in self.streams:
            row = self.stream_table.rowCount()
            self.stream_table.insertRow(row)
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            is_selected = selected_keys is None or _stream_key(stream) in selected_keys
            check.setCheckState(Qt.CheckState.Checked if is_selected else Qt.CheckState.Unchecked)
            self.stream_table.setItem(row, 0, check)
            self.stream_table.setItem(row, 1, QTableWidgetItem(stream.room))
            self.stream_table.setItem(row, 2, QTableWidgetItem(stream.time or stream.pair or "—"))
            description = " | ".join(part for part in (stream.subject, stream.teacher, stream.group) if part) or "—"
            self.stream_table.setItem(row, 3, QTableWidgetItem(description))
            self.stream_table.setItem(row, 4, QTableWidgetItem(stream.url))
        self.stream_table.blockSignals(False)
        self.update_selected_count()

    def selected_streams(self) -> list[StreamRoom]:
        selected: list[StreamRoom] = []
        for row, stream in enumerate(self.streams):
            item = self.stream_table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                selected.append(stream)
        return selected

    def selected_stream_keys(self) -> set[str]:
        return {_stream_key(stream) for stream in self.selected_streams()}

    def update_selected_count(self) -> None:
        selected = len(self.selected_streams())
        total = len(self.streams)
        self.selected_count_label.setText(f"Выбрано: {selected} из {total}")

    def select_all_streams(self) -> None:
        self._set_all_streams(Qt.CheckState.Checked)

    def clear_stream_selection(self) -> None:
        self._set_all_streams(Qt.CheckState.Unchecked)

    def invert_stream_selection(self) -> None:
        for row in range(self.stream_table.rowCount()):
            item = self.stream_table.item(row, 0)
            if item is None:
                continue
            next_state = Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
            item.setCheckState(next_state)
        self.update_selected_count()

    def _set_all_streams(self, state: Qt.CheckState) -> None:
        for row in range(self.stream_table.rowCount()):
            item = self.stream_table.item(row, 0)
            if item is not None:
                item.setCheckState(state)
        self.update_selected_count()

    def _update_empty_stream_row_height(self) -> None:
        if self.streams or self.stream_table.rowCount() != 1:
            return
        height = max(220, self.stream_table.viewport().height() - 8)
        self.stream_table.setRowHeight(0, height)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._update_empty_stream_row_height()

    def add_analysis_row(self, room: str, path: str, summary: AnalysisSummary | None, error: str) -> None:
        row = self.analysis_table.rowCount()
        self.analysis_table.insertRow(row)
        self.analysis_table.setItem(row, 0, QTableWidgetItem(datetime.now().strftime("%H:%M:%S")))
        self.analysis_table.setItem(row, 1, QTableWidgetItem(room))
        row_background = "#f7f7f7"
        row_foreground = "#4e5550"
        if error:
            self.analysis_table.setItem(row, 2, QTableWidgetItem(short_analysis_message(room, error=error)))
            self.analysis_table.setItem(row, 3, QTableWidgetItem("—"))
            row_background, row_foreground = _analysis_colors(analysis_problem_category(error=error))
        elif summary:
            self.analysis_table.setItem(row, 2, QTableWidgetItem(short_analysis_message(room, summary)))
            self.analysis_table.setItem(row, 3, QTableWidgetItem(str(summary.issues_count)))
            if summary.issues_count:
                row_background, row_foreground = _analysis_colors(analysis_problem_category(summary))
            else:
                row_background, row_foreground = _analysis_colors("ok")
        else:
            self.analysis_table.setItem(row, 2, QTableWidgetItem("Нет результата"))
            self.analysis_table.setItem(row, 3, QTableWidgetItem("—"))
        self.analysis_table.setItem(row, 4, QTableWidgetItem(path or "—"))
        self._color_analysis_row(row, row_background, row_foreground)
        self.analysis_table.scrollToBottom()

    def _color_analysis_row(self, row: int, background: str, foreground: str) -> None:
        bg = QBrush(QColor(background))
        fg = QBrush(QColor(foreground))
        for column in range(self.analysis_table.columnCount()):
            item = self.analysis_table.item(row, column)
            if item is not None:
                item.setBackground(bg)
                item.setForeground(fg)

    def append_log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.raw_log.append(f"[{stamp}] {message}")
        log_event(message)

    def show_status(self, message: str, timeout_ms: int = 7000) -> None:
        self.statusBar().showMessage(message, timeout_ms)

    def show_warning(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    def show_info(self, title: str, message: str) -> None:
        QMessageBox.information(self, title, message)

    def show_tray_message(self, title: str, message: str, warning: bool = False) -> None:
        return

    @Slot()
    def bring_to_front(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()


def _stream_key(stream: StreamRoom) -> str:
    return f"{stream.room}|{stream.url}"


def _analysis_colors(category: str) -> tuple[str, str]:
    if category == "audio":
        return "#e8f2ff", "#064f9f"
    if category == "video":
        return "#fff3df", "#8a4b00"
    if category == "mixed":
        return "#f1e9ff", "#5d2d91"
    if category == "ok":
        return "#eff8f1", "#245a3d"
    return "#fff1ee", "#8b2f28"
