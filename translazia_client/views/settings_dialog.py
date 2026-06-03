from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ..config import AppSettings


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Настройки клиента")
        self.resize(760, 560)
        self.settings = deepcopy(settings)
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs)

        source_page = QWidget()
        source_layout = QFormLayout(source_page)
        self.source_mode = QComboBox()
        self.source_mode.addItem("Локальный файл со ссылками", "file")
        self.source_mode.addItem("VK-бот", "vk_bot")
        self.source_mode.addItem("VK Web-сессия", "vk_web")
        source_layout.addRow("Источник расписания", self.source_mode)

        file_row = QHBoxLayout()
        self.local_file = QLineEdit()
        browse_file = QPushButton("Выбрать")
        browse_file.clicked.connect(self._browse_local_file)
        file_row.addWidget(self.local_file, 1)
        file_row.addWidget(browse_file)
        source_layout.addRow("Файл ссылок", file_row)

        self.vk_peer_id = QLineEdit()
        self.vk_access_token = QLineEdit()
        self.vk_access_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.vk_bot_url = QLineEdit()
        self.vk_web_command = QLineEdit()
        self.vk_command = QLineEdit()
        self.vk_api_version = QLineEdit()
        self.vk_poll_timeout = QSpinBox()
        self.vk_poll_timeout.setRange(3, 180)
        self.vk_poll_timeout.setSuffix(" сек.")
        source_layout.addRow("VK Web ссылка бота", self.vk_bot_url)
        source_layout.addRow("VK Web кнопка", self.vk_web_command)
        source_layout.addRow("VK peer_id", self.vk_peer_id)
        source_layout.addRow("VK access token", self.vk_access_token)
        source_layout.addRow("Команда боту", self.vk_command)
        source_layout.addRow("VK API version", self.vk_api_version)
        source_layout.addRow("Ожидание ответа", self.vk_poll_timeout)
        tabs.addTab(source_page, "Расписание")

        launch_page = QWidget()
        launch_layout = QFormLayout(launch_page)
        self.launch_time = QTimeEdit()
        self.launch_time.setDisplayFormat("HH:mm")
        self.remind_minutes = QSpinBox()
        self.remind_minutes.setRange(1, 120)
        self.remind_minutes.setSuffix(" мин.")
        self.auto_launch = QCheckBox("Автоматически открыть выбранные аудитории в это время")
        launch_layout.addRow("Время запуска по Москве", self.launch_time)
        launch_layout.addRow("Уведомить заранее", self.remind_minutes)
        launch_layout.addRow("", self.auto_launch)
        tabs.addTab(launch_page, "Запуск")

        analysis_page = QWidget()
        analysis_layout = QFormLayout(analysis_page)
        self.analysis_enabled = QCheckBox("Включить видеоанализ трансляций")
        self.interval_minutes = QSpinBox()
        self.interval_minutes.setRange(1, 240)
        self.interval_minutes.setSuffix(" мин.")
        self.duration_seconds = QSpinBox()
        self.duration_seconds.setRange(5, 900)
        self.duration_seconds.setSuffix(" сек.")
        self.capture_fps = QDoubleSpinBox()
        self.capture_fps.setRange(0.2, 10.0)
        self.capture_fps.setDecimals(1)
        self.capture_fps.setSingleStep(0.5)
        self.sample_interval = QDoubleSpinBox()
        self.sample_interval.setRange(0.5, 30.0)
        self.sample_interval.setDecimals(1)
        self.sample_interval.setSuffix(" сек.")
        self.person_conf = QDoubleSpinBox()
        self.person_conf.setRange(0.05, 0.95)
        self.person_conf.setDecimals(2)
        self.person_conf.setSingleStep(0.05)
        self.device = QLineEdit()
        self.max_parallel = QSpinBox()
        self.max_parallel.setRange(1, 4)
        output_row = QHBoxLayout()
        self.output_dir = QLineEdit()
        browse_output = QPushButton("Выбрать")
        browse_output.clicked.connect(self._browse_output_dir)
        output_row.addWidget(self.output_dir, 1)
        output_row.addWidget(browse_output)
        self.keep_video = QCheckBox("Оставлять видеофрагменты после проверки")
        self.audio_enabled = QCheckBox("Пробовать аудиоанализ для файлов с аудиодорожкой")

        analysis_layout.addRow("", self.analysis_enabled)
        analysis_layout.addRow("Интервал проверок", self.interval_minutes)
        analysis_layout.addRow("Длительность фрагмента", self.duration_seconds)
        analysis_layout.addRow("FPS захвата окна", self.capture_fps)
        analysis_layout.addRow("Шаг анализа нейросети", self.sample_interval)
        analysis_layout.addRow("Порог человека YOLO", self.person_conf)
        analysis_layout.addRow("Устройство YOLO", self.device)
        analysis_layout.addRow("Параллельных анализов", self.max_parallel)
        analysis_layout.addRow("Папка фрагментов", output_row)
        analysis_layout.addRow("", self.keep_video)
        analysis_layout.addRow("", self.audio_enabled)
        tabs.addTab(analysis_page, "Проверки")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _load_values(self) -> None:
        s = self.settings
        self.source_mode.setCurrentIndex(max(0, self.source_mode.findData(s.source.mode)))
        self.local_file.setText(s.source.local_file)
        self.vk_bot_url.setText(s.source.vk_bot_url)
        self.vk_web_command.setText(s.source.vk_web_command)
        self.vk_peer_id.setText(s.source.vk_peer_id)
        self.vk_access_token.setText(s.source.vk_access_token)
        self.vk_command.setText(s.source.vk_command)
        self.vk_api_version.setText(s.source.vk_api_version)
        self.vk_poll_timeout.setValue(int(s.source.vk_poll_timeout_sec))

        launch_time = QTime.fromString(s.launch.launch_time_msk, "HH:mm")
        self.launch_time.setTime(launch_time if launch_time.isValid() else QTime(17, 0))
        self.remind_minutes.setValue(int(s.launch.remind_minutes_before))
        self.auto_launch.setChecked(bool(s.launch.auto_launch_at_time))

        self.analysis_enabled.setChecked(bool(s.analysis.enabled))
        self.interval_minutes.setValue(int(s.analysis.interval_minutes))
        self.duration_seconds.setValue(int(s.analysis.duration_seconds))
        self.capture_fps.setValue(float(s.analysis.capture_fps))
        self.sample_interval.setValue(float(s.analysis.sample_interval_seconds))
        self.person_conf.setValue(float(s.analysis.person_confidence))
        self.device.setText(s.analysis.device)
        self.max_parallel.setValue(int(s.analysis.max_parallel_analyzers))
        self.output_dir.setText(s.analysis.output_dir)
        self.keep_video.setChecked(bool(s.analysis.keep_video_fragments))
        self.audio_enabled.setChecked(bool(s.analysis.audio_analysis_enabled))

    def accept(self) -> None:
        s = self.settings
        s.source.mode = str(self.source_mode.currentData())
        s.source.local_file = self.local_file.text().strip()
        s.source.vk_bot_url = self.vk_bot_url.text().strip()
        s.source.vk_web_command = self.vk_web_command.text().strip()
        s.source.vk_peer_id = self.vk_peer_id.text().strip()
        s.source.vk_access_token = self.vk_access_token.text().strip()
        s.source.vk_command = self.vk_command.text().strip()
        s.source.vk_api_version = self.vk_api_version.text().strip() or "5.199"
        s.source.vk_poll_timeout_sec = int(self.vk_poll_timeout.value())

        s.launch.launch_time_msk = self.launch_time.time().toString("HH:mm")
        s.launch.remind_minutes_before = int(self.remind_minutes.value())
        s.launch.auto_launch_at_time = bool(self.auto_launch.isChecked())

        s.analysis.enabled = bool(self.analysis_enabled.isChecked())
        s.analysis.interval_minutes = int(self.interval_minutes.value())
        s.analysis.duration_seconds = int(self.duration_seconds.value())
        s.analysis.capture_fps = float(self.capture_fps.value())
        s.analysis.sample_interval_seconds = float(self.sample_interval.value())
        s.analysis.person_confidence = float(self.person_conf.value())
        s.analysis.device = self.device.text().strip()
        s.analysis.max_parallel_analyzers = int(self.max_parallel.value())
        s.analysis.output_dir = self.output_dir.text().strip()
        s.analysis.keep_video_fragments = bool(self.keep_video.isChecked())
        s.analysis.audio_analysis_enabled = bool(self.audio_enabled.isChecked())
        super().accept()

    def _browse_local_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Файл со ссылками",
            self.local_file.text(),
            "Text (*.txt);;All files (*.*)",
        )
        if path:
            self.local_file.setText(path)

    def _browse_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Папка для фрагментов", self.output_dir.text())
        if path:
            self.output_dir.setText(path)
