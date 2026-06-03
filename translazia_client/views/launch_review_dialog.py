from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..models import StreamRoom


class LaunchReviewDialog(QDialog):
    def __init__(self, streams: list[StreamRoom], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.streams = streams
        self.setWindowTitle("Проверка перед запуском")
        self.resize(620, 520)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        title = QLabel("Подтвердите аудитории перед открытием трансляций")
        title.setObjectName("panelTitle")
        subtitle = QLabel("Если занятие отменилось, снимите галочку. Окно уведомлений будет добавлено автоматически.")
        subtitle.setObjectName("subtitleLabel")
        root.addWidget(title)
        root.addWidget(subtitle)

        self.list_widget = QListWidget()
        for stream in self.streams:
            item = QListWidgetItem(stream.label)
            item.setData(Qt.ItemDataRole.UserRole, stream)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.list_widget.addItem(item)
        root.addWidget(self.list_widget, 1)

        actions = QHBoxLayout()
        select_all = QLabel('<a href="select">Выбрать все</a>')
        clear_all = QLabel('<a href="clear">Снять все</a>')
        select_all.linkActivated.connect(lambda _: self._set_all(Qt.CheckState.Checked))
        clear_all.linkActivated.connect(lambda _: self._set_all(Qt.CheckState.Unchecked))
        actions.addWidget(select_all)
        actions.addWidget(clear_all)
        actions.addStretch(1)
        root.addLayout(actions)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Открыть выбранные")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def selected_streams(self) -> list[StreamRoom]:
        selected: list[StreamRoom] = []
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.data(Qt.ItemDataRole.UserRole))
        return selected

    def _set_all(self, state: Qt.CheckState) -> None:
        for index in range(self.list_widget.count()):
            self.list_widget.item(index).setCheckState(state)
