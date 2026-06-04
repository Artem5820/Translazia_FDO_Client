from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..models import StreamRoom


class ManualStreamDialog(QDialog):
    def __init__(self, streams: list[StreamRoom], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.streams = streams
        self.setWindowTitle("Ручной выбор аудиторий")
        self.resize(1080, 680)
        self.setMinimumSize(980, 620)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        title = QLabel("Выберите аудитории для трансляций")
        title.setObjectName("panelTitle")
        subtitle = QLabel("Отметьте аудитории, затем укажите время и описание занятия вручную.")
        subtitle.setObjectName("subtitleLabel")
        root.addWidget(title)
        root.addWidget(subtitle)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["", "Аудитория", "Время", "Описание"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setMinimumHeight(480)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 54)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 150)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 220)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for stream in self.streams:
            self._add_stream_row(stream)
        root.addWidget(self.table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Применить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _add_stream_row(self, stream: StreamRoom) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        check = QTableWidgetItem()
        check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        check.setCheckState(Qt.CheckState.Unchecked)
        self.table.setItem(row, 0, check)

        room = QTableWidgetItem(stream.room)
        room.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.table.setItem(row, 1, room)

        time = QTableWidgetItem(stream.time or "")
        time.setToolTip("Например: 18:00-21:05")
        self.table.setItem(row, 2, time)

        description = QTableWidgetItem(" | ".join(part for part in (stream.subject, stream.teacher, stream.group) if part))
        description.setToolTip("Описание занятия")
        self.table.setItem(row, 3, description)

    def selected_streams(self) -> list[StreamRoom]:
        selected: list[StreamRoom] = []
        for row, stream in enumerate(self.streams):
            check = self.table.item(row, 0)
            if check is None or check.checkState() != Qt.CheckState.Checked:
                continue
            time = (self.table.item(row, 2).text() if self.table.item(row, 2) else "").strip()
            description = (self.table.item(row, 3).text() if self.table.item(row, 3) else "").strip()
            selected.append(replace(stream, time=time, subject=description, source="manual"))
        return selected
