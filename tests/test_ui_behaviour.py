from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from translazia_client.models import StreamRoom
from translazia_client.views.main_window import MainWindow
from translazia_client.views.notification_window import NotificationWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class UiBehaviourTests(unittest.TestCase):
    def test_stream_selection_can_be_preserved_after_refresh(self) -> None:
        _app()
        streams = [
            StreamRoom(room="В-200", url="https://vk.com/call/join/a"),
            StreamRoom(room="В-201", url="https://vk.com/call/join/b"),
        ]
        window = MainWindow()
        window.set_streams(streams)
        window.stream_table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)
        selected = window.selected_stream_keys()

        window.set_streams(streams, selected)

        self.assertEqual([stream.room for stream in window.selected_streams()], ["В-200"])
        self.assertEqual(window.selected_count_label.text(), "Выбрано: 1 из 2")
        window.close()

    def test_notification_export_writes_events(self) -> None:
        _app()
        window = NotificationWindow()
        window.add_event("Ошибка", "В-200", "Тестовая ошибка", "Подробности")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "notifications.txt"
            window.export_to_file(str(path))
            text = path.read_text(encoding="utf-8")

        self.assertIn("Тестовая ошибка", text)
        self.assertIn("Подробности", text)
        window.close()

    def test_notification_mute_button_toggles_all_stream_audio_state(self) -> None:
        _app()
        window = NotificationWindow()
        states: list[bool] = []
        window.mute_all_requested.connect(states.append)

        window.compact_mute_btn.click()

        self.assertEqual(states, [True])
        self.assertEqual(window.compact_mute_btn.text(), "Вкл. звук")
        self.assertEqual(window.header_mute_btn.text(), "Вкл. звук")
        window.close()
