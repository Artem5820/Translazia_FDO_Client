from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QBrush, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..analysis import AnalysisSummary
from ..resources import LOGO_SMALL_PATH, app_icon
from ..services.analysis_messages import analysis_problem_category, compact_analysis_details, short_analysis_message
from ..services.client_logger import log_event


class TwoDigitSpinBox(QSpinBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setKeyboardTracking(False)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.lineEdit().setCursor(Qt.CursorShape.ArrowCursor)

    def textFromValue(self, value: int) -> str:
        return f"{value:02d}"


class NotificationWindow(QMainWindow):
    mute_all_requested = Signal(bool)
    close_streams_requested = Signal()
    record_all_requested = Signal()
    auto_recording_changed = Signal(bool, int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.total_events = 0
        self.error_events = 0
        self.neural_events = 0
        self.compact_mode = False
        self._all_audio_muted = False
        self._auto_recording_enabled = False
        self._record_hour = 17
        self._record_minute = 55
        self._syncing_record_controls = False
        self.compact_lines: list[str] = []
        self.setWindowTitle("Уведомления и ошибки")
        self.setWindowIcon(app_icon())
        self.resize(760, 560)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.header_frame = QFrame()
        self.header_frame.setObjectName("brandHeaderCompact")
        header = QHBoxLayout(self.header_frame)
        header.setContentsMargins(12, 10, 12, 10)
        logo = QLabel()
        logo.setObjectName("brandLogoCompact")
        logo.setFixedSize(54, 54)
        pixmap = QPixmap(str(LOGO_SMALL_PATH))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(50, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(logo)
        title_box = QVBoxLayout()
        title = QLabel("Уведомления и ошибки")
        title.setObjectName("brandTitleLabel")
        subtitle = QLabel("Сюда попадают предупреждения запуска, ошибки и находки нейросетей.")
        subtitle.setObjectName("brandSubtitleLabel")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        self.header_mute_btn = QPushButton("Откл. звук")
        self.header_mute_btn.setToolTip("Отключить или включить звук во всех окнах трансляций")
        self.header_mute_btn.clicked.connect(self._toggle_all_audio_mute)
        header.addWidget(self.header_mute_btn)
        self.header_close_streams_btn = QPushButton("Закрыть трансляции")
        self.header_close_streams_btn.setObjectName("dangerButton")
        self.header_close_streams_btn.setToolTip("Быстро закрыть все открытые окна трансляций")
        self.header_close_streams_btn.clicked.connect(self.close_streams_requested.emit)
        header.addWidget(self.header_close_streams_btn)
        export_btn = QPushButton("Экспорт")
        export_btn.clicked.connect(self.export_dialog)
        clear_btn = QPushButton("Очистить")
        clear_btn.clicked.connect(self.clear)
        header.addWidget(export_btn)
        header.addWidget(clear_btn)
        layout.addWidget(self.header_frame)

        self.badge = QLabel("Событий пока нет")
        self.badge.setObjectName("notificationBadge")
        layout.addWidget(self.badge)
        self.record_controls_frame = self._record_controls(compact=False)
        layout.addWidget(self.record_controls_frame)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Время", "Уровень", "Аудитория", "Сообщение"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 2)

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Подробности выбранных событий и результаты анализа.")
        layout.addWidget(self.details, 1)

        self.compact_panel = QFrame()
        self.compact_panel.setObjectName("notificationStrip")
        compact_layout = QVBoxLayout(self.compact_panel)
        compact_layout.setContentsMargins(6, 8, 6, 8)
        compact_layout.setSpacing(8)
        compact_logo = QLabel()
        compact_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        compact_logo.setFixedSize(38, 38)
        if not pixmap.isNull():
            compact_logo.setPixmap(pixmap.scaled(34, 34, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.compact_total = QLabel("0")
        self.compact_total.setObjectName("stripTotal")
        self.compact_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        total_metric = self._compact_metric(self.compact_total, "События")
        self.compact_errors = QLabel("0")
        self.compact_errors.setObjectName("stripErrors")
        self.compact_errors.setAlignment(Qt.AlignmentFlag.AlignCenter)
        errors_metric = self._compact_metric(self.compact_errors, "Ошибки")
        self.compact_neural = QLabel("0")
        self.compact_neural.setObjectName("stripNeural")
        self.compact_neural.setAlignment(Qt.AlignmentFlag.AlignCenter)
        neural_metric = self._compact_metric(self.compact_neural, "Нейросеть")
        self.compact_mute_btn = QPushButton("Откл. звук")
        self.compact_mute_btn.setToolTip("Отключить или включить звук во всех окнах")
        self.compact_mute_btn.setFixedHeight(30)
        self.compact_mute_btn.clicked.connect(self._toggle_all_audio_mute)
        self.compact_close_streams_btn = QPushButton("Закрыть")
        self.compact_close_streams_btn.setObjectName("stripCloseStreamsButton")
        self.compact_close_streams_btn.setToolTip("Закрыть все трансляции")
        self.compact_close_streams_btn.setFixedHeight(30)
        self.compact_close_streams_btn.clicked.connect(self.close_streams_requested.emit)
        self.compact_record_controls_frame = self._record_controls(compact=True)
        self.compact_log = QTextEdit()
        self.compact_log.setObjectName("stripLog")
        self.compact_log.setReadOnly(True)
        self.compact_log.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.compact_log.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.compact_log.setPlaceholderText("События и ошибки")
        compact_layout.addWidget(compact_logo)
        compact_layout.addWidget(total_metric)
        compact_layout.addWidget(errors_metric)
        compact_layout.addWidget(neural_metric)
        compact_layout.addWidget(self.compact_mute_btn)
        compact_layout.addWidget(self.compact_close_streams_btn)
        compact_layout.addWidget(self.compact_record_controls_frame)
        compact_layout.addWidget(self.compact_log, 1)
        self.compact_panel.hide()
        layout.addWidget(self.compact_panel, 1)
        self.setCentralWidget(root)
        self._sync_record_controls()
        self._update_compact_counts()
        self.set_all_audio_muted(False)

    def _record_controls(self, compact: bool) -> QFrame:
        frame = QFrame()
        frame.setObjectName("stripRecordControlBar" if compact else "recordControlBar")
        root = QVBoxLayout(frame)
        root.setContentsMargins(4 if compact else 8, 6, 4 if compact else 8, 6)
        root.setSpacing(5 if compact else 6)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(6)

        record_btn = QPushButton("Запись")
        record_btn.setObjectName("recordManualButton")
        record_btn.setToolTip("Поставить запись вручную на всех открытых вкладках")
        record_btn.clicked.connect(self.record_all_requested.emit)
        record_btn.setFixedWidth(84 if compact else 116)

        hour_spin = TwoDigitSpinBox()
        hour_spin.setObjectName("recordTimeSpin")
        hour_spin.setRange(0, 23)
        hour_spin.setFixedWidth(94 if compact else 92)
        hour_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hour_spin.setWrapping(True)

        colon = QLabel(":")
        colon.setObjectName("recordTimeColon")
        colon.setFixedWidth(14)
        colon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        minute_spin = TwoDigitSpinBox()
        minute_spin.setObjectName("recordTimeSpin")
        minute_spin.setRange(0, 59)
        minute_spin.setFixedWidth(94 if compact else 92)
        minute_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        minute_spin.setWrapping(True)

        auto_btn = QPushButton("Авто")
        auto_btn.setObjectName("recordAutoButton")
        auto_btn.setCheckable(True)
        auto_btn.setToolTip("Автоматически поставить запись в указанное время")
        auto_btn.toggled.connect(lambda checked: self._set_auto_recording_enabled(checked, emit_signal=True))
        auto_btn.setFixedWidth(72 if compact else 94)

        confirm_btn = QPushButton("OK")
        confirm_btn.setObjectName("recordConfirmButton")
        confirm_btn.setToolTip("Подтвердить автозапись на сегодня")
        confirm_btn.setFixedWidth(48 if compact else 62)
        confirm_btn.clicked.connect(self._confirm_auto_recording)

        hour_spin.valueChanged.connect(lambda value: self._set_record_time(value, minute_spin.value()))
        minute_spin.valueChanged.connect(lambda value: self._set_record_time(hour_spin.value(), value))

        time_row_frame = QWidget()
        time_row_frame.setObjectName("recordTimeRow")
        time_row = QHBoxLayout(time_row_frame)
        time_row.setContentsMargins(0, 0, 0, 0)
        time_row.setSpacing(6)
        time_row.addWidget(hour_spin)
        time_row.addWidget(colon)
        time_row.addWidget(minute_spin)

        button_row.addWidget(record_btn)
        button_row.addWidget(auto_btn)
        button_row.addWidget(confirm_btn)
        root.addLayout(button_row)
        root.addWidget(time_row_frame)

        if compact:
            self.compact_record_btn = record_btn
            self.compact_record_hour_spin = hour_spin
            self.compact_record_colon = colon
            self.compact_record_minute_spin = minute_spin
            self.compact_record_time_row = time_row_frame
            self.compact_auto_record_btn = auto_btn
            self.compact_record_confirm_btn = confirm_btn
        else:
            self.header_record_btn = record_btn
            self.header_record_hour_spin = hour_spin
            self.header_record_colon = colon
            self.header_record_minute_spin = minute_spin
            self.header_record_time_row = time_row_frame
            self.header_auto_record_btn = auto_btn
            self.header_record_confirm_btn = confirm_btn
        return frame

    def _compact_metric(self, value_label: QLabel, caption: str) -> QFrame:
        card = QFrame()
        card.setObjectName("stripMetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(4, 5, 4, 5)
        layout.setSpacing(0)
        caption_label = QLabel(caption)
        caption_label.setObjectName("stripMetricCaption")
        caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(value_label)
        layout.addWidget(caption_label)
        return card

    def _record_time_widgets(self) -> list[QWidget]:
        widgets: list[QWidget] = []
        for prefix in ("header", "compact"):
            for name in ("record_time_row", "record_hour_spin", "record_colon", "record_minute_spin", "record_confirm_btn"):
                widget = getattr(self, f"{prefix}_{name}", None)
                if widget is not None:
                    widgets.append(widget)
        return widgets

    def _sync_record_controls(self) -> None:
        if self._syncing_record_controls:
            return
        self._syncing_record_controls = True
        try:
            for prefix in ("header", "compact"):
                hour_spin = getattr(self, f"{prefix}_record_hour_spin", None)
                minute_spin = getattr(self, f"{prefix}_record_minute_spin", None)
                auto_btn = getattr(self, f"{prefix}_auto_record_btn", None)
                if hour_spin is not None:
                    hour_spin.setValue(self._record_hour)
                if minute_spin is not None:
                    minute_spin.setValue(self._record_minute)
                if auto_btn is not None:
                    auto_btn.setChecked(self._auto_recording_enabled)
            for widget in self._record_time_widgets():
                widget.setVisible(self._auto_recording_enabled)
        finally:
            self._syncing_record_controls = False

    def _set_record_time(self, hour: int, minute: int) -> None:
        if self._syncing_record_controls:
            return
        self._record_hour = int(hour)
        self._record_minute = int(minute)
        self._sync_record_controls()

    def _set_auto_recording_enabled(self, enabled: bool, emit_signal: bool = False) -> None:
        if self._syncing_record_controls:
            return
        self._auto_recording_enabled = bool(enabled)
        self._sync_record_controls()
        if emit_signal and not self._auto_recording_enabled:
            self.auto_recording_changed.emit(False, self._record_hour, self._record_minute)

    @Slot()
    def _confirm_auto_recording(self) -> None:
        if not self._auto_recording_enabled:
            return
        self.auto_recording_changed.emit(True, self._record_hour, self._record_minute)

    def clear(self) -> None:
        self.table.setRowCount(0)
        self.details.clear()
        self.total_events = 0
        self.error_events = 0
        self.neural_events = 0
        self.compact_lines.clear()
        self.compact_log.clear()
        self.badge.setText("Событий пока нет")
        self._update_compact_counts()

    def add_event(self, level: str, room: str, message: str, details: str = "", category: str = "") -> None:
        self.total_events += 1
        if level == "Ошибка":
            self.error_events += 1
        if level == "Нейросеть":
            self.neural_events += 1
        row = self.table.rowCount()
        self.table.insertRow(row)
        display_message = _message_without_room(message, room)
        values = [datetime.now().strftime("%H:%M:%S"), level, room or "—", display_message]
        event_category = category or analysis_problem_category(message=message, details=details)
        color = _event_color(level, event_category)
        background = _event_background(event_category)
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if color is not None:
                item.setForeground(QBrush(color))
            if background is not None:
                item.setBackground(QBrush(background))
            self.table.setItem(row, column, item)
        self.table.scrollToBottom()
        self.badge.setText(
            f"Событий: {self.total_events}; ошибок: {self.error_events}; находок нейросети: {self.neural_events}"
        )
        self._append_compact_event(values[0], level, room, display_message, details, event_category)
        self._update_compact_counts()
        if details:
            self.details.append(f"[{values[0]}] {level} {room or 'система'}")
            self.details.append(details)
            self.details.append("")
        log_event(f"{level} | {room or 'система'} | {message}" + (f" | {details}" if details else ""), level)

    def set_compact_mode(self, compact: bool) -> None:
        if self.compact_mode == compact:
            return
        self.compact_mode = compact
        self.header_frame.setVisible(not compact)
        self.badge.setVisible(not compact)
        self.record_controls_frame.setVisible(not compact)
        self.table.setVisible(not compact)
        self.details.setVisible(not compact)
        self.compact_panel.setVisible(compact)
        if compact:
            self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowStaysOnTopHint)
            self.setFixedWidth(240)
        else:
            self.setWindowFlags(Qt.WindowType.Window)
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)
            self.resize(760, 560)

    def set_all_audio_muted(self, muted: bool) -> None:
        self._all_audio_muted = bool(muted)
        text = "Вкл. звук" if self._all_audio_muted else "Откл. звук"
        tooltip = "Включить звук во всех окнах трансляций" if self._all_audio_muted else "Отключить звук во всех окнах трансляций"
        self.header_mute_btn.setText(text)
        self.header_mute_btn.setToolTip(tooltip)
        self.compact_mute_btn.setText(text)
        self.compact_mute_btn.setToolTip(tooltip)

    @Slot()
    def _toggle_all_audio_mute(self) -> None:
        muted = not self._all_audio_muted
        self.set_all_audio_muted(muted)
        self.mute_all_requested.emit(muted)

    def _update_compact_counts(self) -> None:
        if not hasattr(self, "compact_total"):
            return
        self.compact_total.setText(str(self.total_events))
        self.compact_errors.setText(str(self.error_events))
        self.compact_neural.setText(str(self.neural_events))
        self.compact_panel.setToolTip(
            f"Событий: {self.total_events}\nОшибок: {self.error_events}\nНаходок нейросети: {self.neural_events}"
        )

    def _append_compact_event(self, stamp: str, level: str, room: str, message: str, details: str, category: str) -> None:
        scrollbar = self.compact_log.verticalScrollBar()
        old_scroll_value = scrollbar.value()
        should_autoscroll = scrollbar.value() >= scrollbar.maximum() - 8
        room_text = room or "система"
        title = f"{room_text}: {message}" if room else message
        if room and message.lower().startswith(room.lower()):
            title = f"{room_text}: {_message_without_room(message, room)}"
        color = _event_hex_color(level, category)
        background = _event_hex_background(category)
        details_line = ""
        if details:
            compact_details = _first_compact_detail(details)
            if compact_details:
                details_line = f"<div class='details'>{escape(compact_details)}</div>"
        line = (
            f"<div class='event' style='border-left-color:{color};background:{background};'>"
            f"<div class='meta'>[{escape(stamp)}] {escape(level)}</div>"
            f"<div class='title' style='color:{color};'>{escape(title)}</div>"
            f"{details_line}"
            "</div>"
        )
        self.compact_lines.append(line)
        self.compact_lines = self.compact_lines[-500:]
        self.compact_log.setHtml(_compact_log_html(self.compact_lines))
        if should_autoscroll:
            self.compact_log.verticalScrollBar().setValue(self.compact_log.verticalScrollBar().maximum())
        else:
            scrollbar = self.compact_log.verticalScrollBar()
            scrollbar.setValue(min(old_scroll_value, scrollbar.maximum()))

    def add_analysis_result(self, room: str, video_path: str, summary: AnalysisSummary | None, error: str) -> None:
        if error:
            category = analysis_problem_category(error=error)
            self.add_event("Ошибка", room, short_analysis_message(room, error=error), compact_analysis_details(error=error, video_path=video_path), category)
            return
        if summary is None:
            self.add_event("Ошибка", room, f"{room} - нет результата", video_path)
            return

        if summary.issues_count > 0:
            category = analysis_problem_category(summary)
            self.add_event(
                "Нейросеть",
                room,
                short_analysis_message(room, summary),
                compact_analysis_details(summary, video_path=video_path),
                category,
            )
            return

        self.add_event("Проверка", room, f"{room} - норма", summary.message, "ok")

    def export_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт уведомлений",
            "translazia_notifications.txt",
            "Text (*.txt);;All files (*.*)",
        )
        if path:
            self.export_to_file(path)

    def export_to_file(self, path: str) -> None:
        lines = [
            "Уведомления и ошибки Translazia FDO",
            self.badge.text(),
            "",
        ]
        for row in range(self.table.rowCount()):
            values = []
            for column in range(self.table.columnCount()):
                item = self.table.item(row, column)
                values.append(item.text() if item else "")
            lines.append(" | ".join(values))
        details = self.details.toPlainText().strip()
        if details:
            lines.extend(["", "Подробности:", details])
        with open(path, "w", encoding="utf-8") as file:
            file.write("\n".join(lines))


def _event_color(level: str, category: str = "") -> QColor | None:
    if category == "audio":
        return QColor("#064f9f")
    if category == "video":
        return QColor("#8a4b00")
    if category == "mixed":
        return QColor("#5d2d91")
    if category == "ok":
        return QColor("#245a3d")
    if category == "waiting":
        return QColor("#4f6478")
    if category == "connection":
        return QColor("#8a4b00")
    if level in {"Ошибка", "Нейросеть"}:
        return QColor("#8b2f28")
    if level == "Предупреждение":
        return QColor("#7a5a00")
    if level == "Проверка":
        return QColor("#2e6d50")
    return None


def _event_background(category: str = "") -> QColor | None:
    if category == "audio":
        return QColor("#e8f2ff")
    if category == "video":
        return QColor("#fff3df")
    if category == "mixed":
        return QColor("#f1e9ff")
    if category == "ok":
        return QColor("#eff8f1")
    if category == "waiting":
        return QColor("#eef3f8")
    if category == "connection":
        return QColor("#fff6e8")
    return None


def _event_hex_color(level: str, category: str = "") -> str:
    color = _event_color(level, category)
    return color.name() if color is not None else "#102033"


def _event_hex_background(category: str = "") -> str:
    color = _event_background(category)
    return color.name() if color is not None else "#ffffff"


def _message_without_room(message: str, room: str) -> str:
    text = message.strip()
    if not room:
        return text
    prefixes = (
        f"{room}:",
        f"{room} -",
        f"{room} —",
        f"{room} –",
    )
    lowered = text.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix.lower()):
            return text[len(prefix) :].strip()
    return text


def _first_compact_detail(details: str) -> str:
    for raw_line in details.splitlines():
        line = raw_line.strip()
        if line and not line.lower().startswith("фрагмент:"):
            return line[:120]
    return ""


def _compact_log_html(lines: list[str]) -> str:
    body = "".join(lines)
    return f"""
<html>
<head>
<style>
body {{
    margin: 0;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 12px;
    color: #102033;
}}
.event {{
    border-left: 4px solid #102033;
    border-radius: 7px;
    margin: 0 0 8px 0;
    padding: 7px 8px;
}}
.meta {{
    color: #5d7191;
    font-size: 11px;
    margin-bottom: 3px;
}}
.title {{
    font-weight: 700;
    line-height: 1.35;
}}
.details {{
    color: #4d617d;
    margin-top: 3px;
    line-height: 1.3;
}}
</style>
</head>
<body>{body}</body>
</html>
"""


def _format_problem_details(payload: dict[str, Any]) -> str:
    problems = payload.get("проблемы", [])
    if not isinstance(problems, list) or not problems:
        return str(payload)

    lines: list[str] = []
    for index, problem in enumerate(problems, 1):
        if not isinstance(problem, dict):
            lines.append(f"{index}. {problem}")
            continue
        source = problem.get("источник", "нейросеть")
        title = problem.get("тип") or problem.get("решение") or "Проблема"
        level = problem.get("уровень", "—")
        duration = problem.get("длительность_сек", "—")
        description = problem.get("описание", "")
        lines.append(f"{index}. [{source}] {title}; уровень: {level}; длительность: {duration} сек.")
        if description:
            lines.append(f"   {description}")
        metrics = problem.get("метрики", {})
        if isinstance(metrics, dict):
            compact_metrics = _compact_audio_metrics(metrics)
            if compact_metrics:
                lines.append(f"   Метрики: {compact_metrics}")
    return "\n".join(lines)


def _compact_audio_metrics(metrics: dict[str, Any]) -> str:
    names = {
        "rms_dbfs": "громкость",
        "silence_ratio": "тишина",
        "speech_ratio": "речь",
        "snr_estimate_db": "SNR",
        "clipping_ratio": "перегруз",
    }
    parts: list[str] = []
    for key, title in names.items():
        if key in metrics:
            parts.append(f"{title}={metrics[key]}")
    return "; ".join(parts)
