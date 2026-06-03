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

    def test_main_window_has_no_close_streams_button(self) -> None:
        _app()
        window = MainWindow()

        self.assertFalse(hasattr(window, "close_btn"))
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

    def test_notification_compact_metrics_have_captions(self) -> None:
        _app()
        window = NotificationWindow()
        captions = {label.text() for label in window.compact_panel.findChildren(type(window.compact_total))}

        self.assertIn("События", captions)
        self.assertIn("Ошибки", captions)
        self.assertIn("Нейросеть", captions)
        window.close()

    def test_notification_record_controls_toggle_time_inputs(self) -> None:
        _app()
        window = NotificationWindow()

        self.assertEqual(window.header_record_hour_spin.value(), 17)
        self.assertEqual(window.header_record_minute_spin.value(), 55)
        self.assertTrue(window.header_record_time_row.isHidden())
        self.assertTrue(window.header_record_hour_spin.isHidden())
        self.assertTrue(window.header_record_minute_spin.isHidden())

        window.header_auto_record_btn.click()

        self.assertFalse(window.header_record_time_row.isHidden())
        self.assertFalse(window.header_record_confirm_btn.isHidden())
        self.assertFalse(window.header_record_hour_spin.isHidden())
        self.assertFalse(window.header_record_minute_spin.isHidden())
        self.assertFalse(window.compact_record_time_row.isHidden())
        self.assertTrue(window.compact_auto_record_btn.isChecked())
        window.close()

    def test_notification_record_controls_emit_signals(self) -> None:
        _app()
        window = NotificationWindow()
        manual_requests: list[str] = []
        auto_requests: list[tuple[bool, int, int]] = []
        window.record_all_requested.connect(lambda: manual_requests.append("record"))
        window.auto_recording_changed.connect(lambda enabled, hour, minute: auto_requests.append((enabled, hour, minute)))

        window.header_record_btn.click()
        window.compact_record_btn.click()
        window.header_auto_record_btn.click()
        window.header_record_hour_spin.setValue(18)
        self.assertEqual(auto_requests, [])
        window.header_record_confirm_btn.click()
        window.header_auto_record_btn.click()

        self.assertEqual(manual_requests, ["record", "record"])
        self.assertEqual(auto_requests, [(True, 18, 55), (False, 18, 55)])
        window.close()

    def test_notification_close_streams_buttons_emit_signal(self) -> None:
        _app()
        window = NotificationWindow()
        requests: list[str] = []
        window.close_streams_requested.connect(lambda: requests.append("close"))

        window.header_close_streams_btn.click()
        window.compact_close_streams_btn.click()

        self.assertEqual(requests, ["close", "close"])
        window.close()
