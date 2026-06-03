from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import json
import threading

from PySide6.QtCore import QObject, QRect, QTimer, QUrl, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QDialog

from ..analysis import AnalysisManager, AnalysisSummary
from ..config import DATA_DIR, AppSettings, load_settings, save_settings
from ..layout import ScreenRect, WindowPlacement, compute_window_placements
from ..models import StreamRoom
from ..services.healthcheck import run_startup_healthcheck
from ..services.analysis_messages import short_analysis_message, short_problem
from ..services.results_cleanup import cleanup_results_folder
from ..services.schedule_service import load_streams
from ..services.time_service import now_moscow, parse_hhmm
from ..services.vk_auth_service import VkAuthChecker
from ..services.vk_web_schedule import parse_vk_web_schedule
from ..views.main_window import MainWindow
from ..views.notification_window import NotificationWindow
from ..views.settings_dialog import SettingsDialog
from ..views.stream_window import StreamWindow
from ..views.vk_auth_window import VkAuthWindow
from .bridge import AppBridge


_WINDOW_TRANSITION_BATCH_SIZE = 3
_WINDOW_TRANSITION_BATCH_INTERVAL_MS = 20
_RECORDING_VERIFY_DELAY_MS = 30_000
_RECORDING_VERIFY_CALLBACK_WAIT_MS = 4_000
_MAX_RECORDING_ATTEMPTS = 3


class MainController(QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.settings: AppSettings = load_settings()
        self.bridge = AppBridge()
        self.analysis_manager = AnalysisManager(self.settings.analysis)
        self.main_window = MainWindow()
        self.notification_window = NotificationWindow()
        self.vk_auth_checker = VkAuthChecker(self)
        self.vk_auth_window: VkAuthWindow | None = None
        self._last_vk_schedule_signature = ""
        self._vk_authorized = self._load_vk_auth_hint()
        self._vk_schedule_request_active = False
        self._vk_schedule_request_id = 0
        self._all_stream_audio_muted = False
        self._focused_stream_room: str | None = None
        self._focus_geometry_change = False
        self._focus_transition_id = 0
        self._auto_recording_enabled = False
        self._auto_recording_hour = 17
        self._auto_recording_minute = 55
        self._last_auto_recording_date = ""
        self._recording_generation = 0
        self._recording_attempts: dict[str, int] = {}
        self._recording_confirmed_rooms: set[str] = set()
        self._recording_check_results: dict[str, dict[str, object]] = {}
        self._stream_launch_retry_rooms: set[str] = set()
        self._lesson_not_started_rooms: set[str] = set()
        self._lesson_started_rooms: set[str] = set()
        self._lesson_ended_rooms: set[str] = set()
        self.stream_windows: dict[str, StreamWindow] = {}
        self._retired_stream_windows: list[StreamWindow] = []
        self._stream_close_queue: list[StreamWindow] = []
        self.last_reminder_date = ""
        self.last_auto_launch_date = ""
        self._connect()
        self._setup_scheduler()
        self._cleanup_results_folder("при запуске")
        self.main_window.update_cards(self.settings)
        self.main_window.set_vk_auth_status(True if self._vk_authorized else None, "Авторизовано" if self._vk_authorized else "Проверяется")
        self._run_startup_healthcheck()
        if not self._vk_authorized:
            self.check_vk_auth_status()
        self.refresh_schedule()

    def show(self) -> None:
        self.main_window.show()

    def _connect(self) -> None:
        self.main_window.refresh_requested.connect(self.refresh_schedule)
        self.main_window.launch_requested.connect(self.launch_selected)
        self.main_window.settings_requested.connect(self.open_settings)
        self.main_window.notifications_requested.connect(self.show_notifications)
        self.main_window.vk_login_requested.connect(self.open_vk_login)
        self.main_window.vk_auth_check_requested.connect(self.check_vk_auth_status)
        self.notification_window.mute_all_requested.connect(self.set_all_stream_audio_muted)
        self.notification_window.close_streams_requested.connect(self.close_stream_windows)
        self.notification_window.record_all_requested.connect(self.record_all_streams)
        self.notification_window.auto_recording_changed.connect(self.set_auto_recording)
        self.vk_auth_checker.finished.connect(self._on_vk_auth_checked)
        self.bridge.schedule_loaded.connect(self._on_schedule_loaded)
        self.bridge.schedule_failed.connect(self._on_schedule_failed)
        self.bridge.analysis_finished.connect(self._on_analysis_finished)

    def _setup_scheduler(self) -> None:
        self.scheduler_timer = QTimer(self)
        self.scheduler_timer.timeout.connect(self._check_launch_schedule)
        self.scheduler_timer.timeout.connect(self._check_recording_schedule)
        self.scheduler_timer.start(30_000)
        self.cleanup_timer = QTimer(self)
        self.cleanup_timer.timeout.connect(lambda: self._cleanup_results_folder("по таймеру"))
        self.cleanup_timer.start(30 * 60 * 1000)

    @Slot()
    def refresh_schedule(self) -> None:
        if self.settings.source.mode == "vk_web" or self._vk_authorized:
            self.main_window.set_loading(False)
            self.request_vk_today_schedule(show_window=not self._vk_authorized, force=True)
            return
        self.main_window.set_loading(True)

        def worker() -> None:
            try:
                streams, label = load_streams(self.settings.source)
                self.bridge.schedule_loaded.emit(streams, label)
            except Exception as exc:
                self.bridge.schedule_failed.emit(str(exc))

        threading.Thread(target=worker, daemon=True).start()

    @Slot(object, str)
    def _on_schedule_loaded(self, streams: object, label: str) -> None:
        loaded = list(streams) if isinstance(streams, list) else []
        selected_keys = self.main_window.selected_stream_keys() if self.main_window.streams else None
        self.main_window.set_loading(False)
        self.main_window.set_streams(loaded, selected_keys)
        self.main_window.update_cards(self.settings)
        self.main_window.show_status(f"Расписание загружено: {len(loaded)} аудиторий ({label})")
        self.main_window.append_log(f"Расписание загружено: {len(loaded)} аудиторий. Источник: {label}.")
        self.notification_window.add_event("Информация", "", f"Расписание загружено: {len(loaded)} аудиторий")

    @Slot(str)
    def _on_schedule_failed(self, error: str) -> None:
        self.main_window.set_loading(False)
        self.main_window.show_status("Не удалось загрузить расписание")
        self.main_window.append_log(f"Ошибка загрузки расписания: {error}")
        self.notification_window.add_event("Ошибка", "", "Не удалось загрузить расписание", error)
        self.show_notifications()
        self.main_window.show_warning("Расписание не загружено", error)

    @Slot()
    def launch_selected(self) -> None:
        selected = self.main_window.selected_streams()
        if not selected:
            self.main_window.show_info("Нет аудиторий", "Отметьте хотя бы одну аудиторию для запуска.")
            return
        self.close_stream_windows()
        self._lesson_not_started_rooms = set()
        self._lesson_started_rooms = set()
        self._lesson_ended_rooms = set()
        screens, notification_placement = _screens_with_notification_strip()
        stream_placements = compute_window_placements(screens, len(selected))

        for stream, placement in zip(selected, stream_placements):
            window = StreamWindow(stream, self.settings, self.analysis_manager, self.bridge)
            window.setGeometry(QRect(placement.x, placement.y, placement.width, placement.height))
            window.set_audio_muted(self._all_stream_audio_muted, emit_signal=False)
            window.audio_muted_changed.connect(self._on_stream_audio_muted_changed)
            window.launch_state_changed.connect(self._on_stream_launch_state_changed)
            window.focus_mode_requested.connect(self._enter_stream_focus_mode)
            window.focus_mode_exited.connect(self._exit_stream_focus_mode)
            window.next_stream_requested.connect(lambda room, step=1: self._switch_focused_stream(room, step))
            window.previous_stream_requested.connect(lambda room, step=-1: self._switch_focused_stream(room, step))
            window.multiwindow_requested.connect(self._exit_stream_focus_mode)
            window.closed.connect(self._on_stream_window_closed)
            window.show()
            self.stream_windows[stream.room] = window
            QTimer.singleShot(30_000, lambda room=stream.room: self._check_stream_launch(room))

        self.notification_window.set_compact_mode(True)
        self.notification_window.set_all_audio_muted(self._all_stream_audio_muted)
        self.notification_window.setGeometry(QRect(notification_placement.x, notification_placement.y, notification_placement.width, notification_placement.height))
        self.notification_window.show()
        self.notification_window.raise_()
        self.notification_window.add_event(
            "Информация",
            "",
            f"Открыто окон: {len(selected)} трансляций + окно уведомлений",
        )
        self.main_window.append_log(f"Открыто окон трансляций: {len(selected)}. Дополнительно открыто окно уведомлений.")
        self.main_window.show_status(f"Открыто окон: {len(selected)} + уведомления")

    @Slot()
    def close_stream_windows(self) -> None:
        if not self.stream_windows:
            self.notification_window.set_compact_mode(False)
            return
        closing_windows = list(self.stream_windows.values())
        self.stream_windows.clear()
        self._focused_stream_room = None
        self._focus_geometry_change = False
        self._recording_generation += 1
        self._recording_attempts.clear()
        self._recording_confirmed_rooms.clear()
        self._recording_check_results.clear()
        self._stream_launch_retry_rooms.clear()
        self._lesson_not_started_rooms.clear()
        self._lesson_started_rooms.clear()
        self._lesson_ended_rooms.update(window.stream.room for window in closing_windows)
        for window in closing_windows:
            try:
                window.closed.disconnect(self._on_stream_window_closed)
            except (RuntimeError, TypeError):
                pass
            try:
                window.audio_muted_changed.disconnect(self._on_stream_audio_muted_changed)
            except (RuntimeError, TypeError):
                pass
            try:
                window.launch_state_changed.disconnect(self._on_stream_launch_state_changed)
            except (RuntimeError, TypeError):
                pass
            try:
                window.focus_mode_requested.disconnect(self._enter_stream_focus_mode)
                window.focus_mode_exited.disconnect(self._exit_stream_focus_mode)
                window.multiwindow_requested.disconnect(self._exit_stream_focus_mode)
            except (RuntimeError, TypeError):
                pass
            window.prepare_for_close(emit_closed=False)
            self._stream_close_queue.append(window)
        self._hide_next_stream_window()

    def _hide_next_stream_window(self) -> None:
        if not self._stream_close_queue:
            self.notification_window.set_compact_mode(False)
            self.main_window.append_log("Окна трансляций закрыты.")
            return
        window = self._stream_close_queue.pop(0)
        window.hide()
        if window not in self._retired_stream_windows:
            self._retired_stream_windows.append(window)
        QTimer.singleShot(140, self._hide_next_stream_window)

    @Slot(str)
    def _on_stream_window_closed(self, room: str) -> None:
        was_focused = self._focused_stream_room == room
        window = self.stream_windows.pop(room, None)
        self._lesson_not_started_rooms.discard(room)
        self._lesson_started_rooms.discard(room)
        self._lesson_ended_rooms.add(room)
        if window is not None and window not in self._retired_stream_windows:
            self._retired_stream_windows.append(window)
        if not self.stream_windows:
            self.notification_window.set_compact_mode(False)
            self.main_window.append_log("Все окна трансляций закрыты.")
            return
        if was_focused:
            self._focused_stream_room = next(iter(self.stream_windows))
            self._show_focused_stream(self._focused_stream_room)
            self.main_window.append_log(f"{room}: трансляция закрыта, открыта следующая аудитория.")
            return
        self._reflow_stream_windows()

    def _reflow_stream_windows(self) -> None:
        if self._focused_stream_room:
            return
        screens, notification_placement = _screens_with_notification_strip()
        placements = list(zip(self.stream_windows.values(), compute_window_placements(screens, len(self.stream_windows))))
        self._focus_transition_id += 1
        transition_id = self._focus_transition_id
        self._focus_geometry_change = True
        self.notification_window.set_compact_mode(True)
        self.notification_window.setGeometry(QRect(notification_placement.x, notification_placement.y, notification_placement.width, notification_placement.height))
        self.notification_window.show()
        self.notification_window.raise_()
        self._reflow_stream_windows_batch(placements, transition_id, 0)

    @Slot(str)
    def _enter_stream_focus_mode(self, room: str) -> None:
        window = self.stream_windows.get(room)
        if window is None:
            return
        if self._focused_stream_room == room:
            return
        self._focused_stream_room = room
        self._show_focused_stream(room)
        self.main_window.append_log(f"{room}: окно раскрыто. Переключение: стрелки или кнопки по краям.")

    @Slot()
    def _exit_stream_focus_mode(self) -> None:
        if self._focus_geometry_change:
            return
        if not self._focused_stream_room:
            return
        self._focused_stream_room = None
        self._reflow_stream_windows()

    def _switch_focused_stream(self, room: str, step: int) -> None:
        if not self._focused_stream_room:
            return
        rooms = list(self.stream_windows.keys())
        if not rooms or room not in rooms:
            return
        current = self.stream_windows.get(room)
        index = rooms.index(room)
        target_room = rooms[(index + step) % len(rooms)]
        if current is not None:
            current.hide()
            current.set_focus_mode_active(False)
        self._focused_stream_room = target_room
        self._show_focused_stream(target_room)

    def _show_focused_stream(self, room: str) -> None:
        window = self.stream_windows.get(room)
        if window is None:
            return
        focus_rect = self._focus_rect_for_window(window)
        self._focus_transition_id += 1
        transition_id = self._focus_transition_id
        self._focus_geometry_change = True
        try:
            self._place_stream_window(window, focus_rect, show=True)
            window.set_focus_mode_active(True)
            window.raise_()
            window.activateWindow()
        finally:
            QTimer.singleShot(0, lambda transition_id=transition_id: self._finish_focus_geometry_change(transition_id))
        QTimer.singleShot(0, lambda room=room, transition_id=transition_id: self._hide_non_focused_streams(room, transition_id))
        self.notification_window.raise_()

    def _reflow_stream_windows_batch(
        self,
        placements: list[tuple[StreamWindow, WindowPlacement]],
        transition_id: int,
        start_index: int,
    ) -> None:
        if transition_id != self._focus_transition_id or self._focused_stream_room:
            return
        end_index = min(start_index + _WINDOW_TRANSITION_BATCH_SIZE, len(placements))
        for window, placement in placements[start_index:end_index]:
            if window.stream.room not in self.stream_windows:
                continue
            window.set_focus_mode_active(False)
            rect = QRect(placement.x, placement.y, placement.width, placement.height)
            self._place_stream_window(window, rect, show=True)
        if end_index < len(placements):
            QTimer.singleShot(
                _WINDOW_TRANSITION_BATCH_INTERVAL_MS,
                lambda placements=placements, transition_id=transition_id, end_index=end_index: self._reflow_stream_windows_batch(
                    placements,
                    transition_id,
                    end_index,
                ),
            )
            return
        self._finish_focus_geometry_change(transition_id)
        self.main_window.append_log(f"Окна трансляций перестроены: осталось {len(self.stream_windows)}.")

    def _hide_non_focused_streams(self, room: str, transition_id: int) -> None:
        if transition_id != self._focus_transition_id or self._focused_stream_room != room:
            return
        hidden_count = 0
        for other_room, other_window in self.stream_windows.items():
            if other_room == room or not other_window.isVisible():
                continue
            other_window.set_focus_mode_active(False)
            other_window.hide()
            hidden_count += 1
            if hidden_count >= _WINDOW_TRANSITION_BATCH_SIZE:
                break
        has_visible_others = any(other_room != room and window.isVisible() for other_room, window in self.stream_windows.items())
        if has_visible_others:
            QTimer.singleShot(
                _WINDOW_TRANSITION_BATCH_INTERVAL_MS,
                lambda room=room, transition_id=transition_id: self._hide_non_focused_streams(room, transition_id),
            )

    def _place_stream_window(self, window: StreamWindow, rect: QRect, show: bool) -> None:
        updates_enabled = window.updatesEnabled()
        window.setUpdatesEnabled(False)
        try:
            if window.isMaximized() or window.isMinimized():
                window.showNormal()
            window.setGeometry(rect)
            if show:
                window.show()
        finally:
            window.setUpdatesEnabled(updates_enabled)

    def _finish_focus_geometry_change(self, transition_id: int) -> None:
        if transition_id == self._focus_transition_id:
            self._focus_geometry_change = False

    def _focus_rect_for_window(self, window: StreamWindow) -> QRect:
        screens, notification_placement = _screens_with_notification_strip()
        fallback = screens[0]
        center = window.geometry().center()
        chosen = fallback
        for screen in screens:
            rect = QRect(screen.x, screen.y, screen.width, screen.height)
            if rect.contains(center):
                chosen = screen
                break
        self.notification_window.set_compact_mode(True)
        self.notification_window.setGeometry(
            QRect(notification_placement.x, notification_placement.y, notification_placement.width, notification_placement.height)
        )
        self.notification_window.show()
        return QRect(chosen.x, chosen.y, chosen.width, chosen.height)

    @Slot(bool)
    def set_all_stream_audio_muted(self, muted: bool) -> None:
        self._all_stream_audio_muted = bool(muted)
        self.notification_window.set_all_audio_muted(self._all_stream_audio_muted)
        for window in self.stream_windows.values():
            window.set_audio_muted(self._all_stream_audio_muted, emit_signal=False)
        action = "отключен" if self._all_stream_audio_muted else "включен"
        self.main_window.append_log(f"Звук во всех окнах трансляций {action}.")
        self.notification_window.add_event("Информация", "", f"Звук во всех окнах {action}")

    @Slot(str, bool)
    def _on_stream_audio_muted_changed(self, room: str, muted: bool) -> None:
        action = "отключен" if muted else "включен"
        self.main_window.append_log(f"{room}: звук {action}.")
        if self.stream_windows and all(window.is_audio_muted() == muted for window in self.stream_windows.values()):
            self._all_stream_audio_muted = muted
            self.notification_window.set_all_audio_muted(muted)

    @Slot(str, str)
    def _on_stream_launch_state_changed(self, room: str, state: str) -> None:
        if state == "load_failed":
            self.notification_window.add_event("Ошибка", room, f"{room} - не загрузилась")
        elif state == "join_clicked":
            self.main_window.append_log(f"{room}: подключение к трансляции запущено.")
        elif state == "connected":
            self._stream_launch_retry_rooms.discard(room)
            self.main_window.append_log(f"{room}: трансляция открыта.")
        elif state == "call_error_reloaded":
            self._stream_launch_retry_rooms.discard(room)
            self.notification_window.add_event("Предупреждение", room, f"{room} - перезапуск звонка")
            self.main_window.append_log(f"{room}: VK показал ошибку звонка, страница перезапущена.")
        elif state == "join_timeout_reloaded":
            self._stream_launch_retry_rooms.discard(room)
            self.notification_window.add_event("Предупреждение", room, f"{room} - повторное подключение")
            self.main_window.append_log(f"{room}: подключение не подтвердилось, страница перезапущена.")
        elif state == "manual_reloaded":
            self._stream_launch_retry_rooms.discard(room)
            self.main_window.append_log(f"{room}: вкладка обновлена вручную, повторяю подключение.")

    @Slot()
    def record_all_streams(self) -> None:
        self._start_recording_on_all_streams("ручной запуск")

    @Slot(bool, int, int)
    def set_auto_recording(self, enabled: bool, hour: int, minute: int) -> None:
        was_enabled = self._auto_recording_enabled
        old_time = (self._auto_recording_hour, self._auto_recording_minute)
        if not enabled and not was_enabled:
            return
        self._auto_recording_enabled = bool(enabled)
        self._auto_recording_hour = max(0, min(23, int(hour)))
        self._auto_recording_minute = max(0, min(59, int(minute)))
        now = now_moscow()
        record_dt = _recording_datetime_for_today(self._auto_recording_hour, self._auto_recording_minute, now)
        if self._auto_recording_enabled and not _recording_time_is_valid(self._auto_recording_hour, self._auto_recording_minute, now):
            self._auto_recording_enabled = False
            self.notification_window.add_event(
                "Предупреждение",
                "",
                "Интервал автозаписи не действителен",
                f"Выбранное время уже прошло сегодня: {record_dt.strftime('%d.%m.%Y %H:%M')}.",
            )
            self.main_window.append_log(f"Автозапись не включена: время уже прошло ({record_dt.strftime('%H:%M')}).")
            return
        if self._auto_recording_enabled and (not was_enabled or old_time != (self._auto_recording_hour, self._auto_recording_minute)):
            self._last_auto_recording_date = ""
        if self._auto_recording_enabled:
            self.main_window.append_log(f"Автозапись включена на {self._auto_recording_hour:02d}:{self._auto_recording_minute:02d}.")
            self.notification_window.add_event(
                "Информация",
                "",
                f"Автозапись включена: {self._auto_recording_hour:02d}:{self._auto_recording_minute:02d}",
            )
        else:
            self.main_window.append_log("Автозапись выключена.")
            self.notification_window.add_event("Информация", "", "Автозапись выключена")

    def _start_recording_on_all_streams(self, reason: str) -> None:
        if not self.stream_windows:
            self.notification_window.add_event("Предупреждение", "", "Нет открытых вкладок для записи")
            self.main_window.append_log("Запись не поставлена: нет открытых вкладок трансляций.")
            return
        self._recording_generation += 1
        generation = self._recording_generation
        self._recording_attempts = {room: 0 for room in self.stream_windows}
        self._recording_confirmed_rooms.clear()
        self._recording_check_results.clear()
        self.notification_window.add_event("Информация", "", f"Постановка записи: {len(self.stream_windows)} вкладок", reason)
        self.main_window.append_log(f"Запускаю постановку записи на {len(self.stream_windows)} вкладках ({reason}).")
        for room in list(self.stream_windows.keys()):
            self._request_stream_recording(room, generation)
        QTimer.singleShot(_RECORDING_VERIFY_DELAY_MS, lambda generation=generation: self._verify_stream_recordings(generation))

    def _request_stream_recording(self, room: str, generation: int) -> None:
        if generation != self._recording_generation:
            return
        window = self.stream_windows.get(room)
        if window is None:
            return
        self._recording_attempts[room] = self._recording_attempts.get(room, 0) + 1
        title = _recording_title(window.stream.room)
        window.ensure_call_recording(
            title,
            lambda result, room=room, generation=generation: self._on_recording_request_result(generation, room, result),
        )

    def _on_recording_request_result(self, generation: int, room: str, result: dict[str, object]) -> None:
        if generation != self._recording_generation or room not in self.stream_windows:
            return
        state = str(result.get("state", "unknown"))
        title = str(result.get("title", _recording_title(room)))
        attempt = self._recording_attempts.get(room, 1)
        if result.get("recording"):
            self._recording_confirmed_rooms.add(room)
            self.notification_window.add_event("Проверка", room, f"{room} - запись уже идёт")
            self.main_window.append_log(f"{room}: запись уже идёт или поставлена. Название: {title}.")
            return
        if state in {"record_requested", "command_started"}:
            self.notification_window.add_event("Информация", room, f"{room} - команда записи отправлена")
            self.main_window.append_log(f"{room}: команда записи отправлена. Попытка {attempt}.")
            return
        self.notification_window.add_event(
            "Предупреждение",
            room,
            f"{room} - запись не поставилась сразу",
            _recording_state_message(state),
        )
        self.main_window.append_log(f"{room}: не удалось сразу поставить запись ({state}). Попытка {attempt}.")

    def _verify_stream_recordings(self, generation: int) -> None:
        if generation != self._recording_generation:
            return
        rooms = [room for room in self._recording_attempts if room in self.stream_windows]
        if not rooms:
            return
        self._recording_check_results = {}
        for room in rooms:
            window = self.stream_windows.get(room)
            if window is None:
                continue
            window.inspect_recording_state(
                lambda result, room=room, generation=generation: self._on_recording_state_checked(generation, room, result)
            )
        QTimer.singleShot(
            _RECORDING_VERIFY_CALLBACK_WAIT_MS,
            lambda generation=generation, rooms=rooms: self._finish_recording_verification(generation, rooms),
        )

    def _on_recording_state_checked(self, generation: int, room: str, result: dict[str, object]) -> None:
        if generation != self._recording_generation:
            return
        self._recording_check_results[room] = result

    def _finish_recording_verification(self, generation: int, rooms: list[str]) -> None:
        if generation != self._recording_generation:
            return
        retry_rooms: list[str] = []
        failed_rooms: list[str] = []
        for room in rooms:
            if room not in self.stream_windows:
                continue
            result = self._recording_check_results.get(room, {"recording": False, "state": "no_callback"})
            if result.get("recording"):
                if room not in self._recording_confirmed_rooms:
                    self.notification_window.add_event("Проверка", room, f"{room} - запись идёт")
                    self.main_window.append_log(f"{room}: проверка подтвердила, запись идёт.")
                self._recording_confirmed_rooms.add(room)
                continue
            if self._recording_attempts.get(room, 0) < _MAX_RECORDING_ATTEMPTS:
                retry_rooms.append(room)
            else:
                failed_rooms.append(room)

        for room in retry_rooms:
            self.notification_window.add_event("Предупреждение", room, f"{room} - запись не включилась, повторяю")
            self.main_window.append_log(f"{room}: запись не подтвердилась через 30 секунд, повторяю постановку.")
            self._request_stream_recording(room, generation)

        for room in failed_rooms:
            self.notification_window.add_event("Ошибка", room, f"{room} - запись не включилась", "Достигнут лимит повторных попыток.")
            self.main_window.append_log(f"{room}: запись не включилась после {_MAX_RECORDING_ATTEMPTS} попыток.")

        if retry_rooms:
            QTimer.singleShot(_RECORDING_VERIFY_DELAY_MS, lambda generation=generation: self._verify_stream_recordings(generation))
        elif not failed_rooms:
            self.notification_window.add_event("Информация", "", "Запись включена на всех вкладках")
            self.main_window.append_log("Запись подтверждена на всех открытых вкладках.")

    def _check_stream_launch(self, room: str) -> None:
        window = self.stream_windows.get(room)
        if window is None:
            return
        state = window.launch_state()
        if state in {"connected", "join_clicked"}:
            return
        if state == "loading":
            if room not in self._stream_launch_retry_rooms:
                self._stream_launch_retry_rooms.add(room)
                window.reload_and_retry_join()
                self.main_window.append_log(f"{room}: окно зависло на загрузке, перезагружаю.")
                QTimer.singleShot(18_000, lambda room=room: self._check_stream_launch(room))
                return
            self.notification_window.add_event("Ошибка", room, f"{room} - не открылась")
            self.main_window.append_log(f"{room}: окно трансляции не загрузилось.")
            return
        if state == "loaded" and room not in self._stream_launch_retry_rooms:
            self._stream_launch_retry_rooms.add(room)
            window.retry_join()
            self.main_window.append_log(f"{room}: повторно ищу кнопку подключения.")
            QTimer.singleShot(14_000, lambda room=room: self._check_stream_launch(room))
            return
        if state == "loaded":
            self.notification_window.add_event("Предупреждение", room, f"{room} - не подключилась")
            self.main_window.append_log(f"{room}: окно загрузилось, но присоединение не подтверждено.")

    @Slot()
    def show_notifications(self) -> None:
        if self.stream_windows and self.notification_window.compact_mode:
            self.notification_window.raise_()
            return
        self.notification_window.set_compact_mode(False)
        self.notification_window.showNormal()
        self.notification_window.raise_()
        self.notification_window.activateWindow()

    @Slot()
    def open_output_folder(self) -> None:
        output_dir = Path(self.settings.analysis.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_dir)))
        if opened:
            self.notification_window.add_event("Информация", "", "Открыта папка результатов", str(output_dir))
        else:
            self.notification_window.add_event("Ошибка", "", "Не удалось открыть папку результатов", str(output_dir))
            self.show_notifications()

    @Slot()
    def open_vk_login(self) -> None:
        self._ensure_vk_window()
        if self.vk_auth_window is None:
            return
        self.vk_auth_window.showNormal()
        self.vk_auth_window.raise_()
        self.vk_auth_window.activateWindow()

    def _ensure_vk_window(self) -> None:
        if self.vk_auth_window is None:
            self.vk_auth_window = VkAuthWindow(self.settings.source.vk_bot_url, self.main_window)
            self.vk_auth_window.auth_check_requested.connect(self.check_vk_auth_status)
            self.vk_auth_window.page_auth_detected.connect(self._on_vk_auth_checked)
            self.vk_auth_window.page_text_ready.connect(self._on_vk_page_text_ready)
            self.vk_auth_window.automation_log.connect(self.main_window.append_log)
            self.vk_auth_window.destroyed.connect(lambda: setattr(self, "vk_auth_window", None))

    def request_vk_today_schedule(self, show_window: bool = False, force: bool = False) -> None:
        if self._vk_schedule_request_active and not force:
            return
        self._ensure_vk_window()
        if self.vk_auth_window is None:
            return
        self._vk_schedule_request_id += 1
        request_id = self._vk_schedule_request_id
        self._vk_schedule_request_active = True
        if show_window:
            self.vk_auth_window.showNormal()
            self.vk_auth_window.raise_()
            self.vk_auth_window.activateWindow()
        self.main_window.show_status("VK: автоматически запрашиваю онлайн трансляции на сегодня")
        self.main_window.append_log("VK: автоматический запрос расписания на сегодня.")
        self.vk_auth_window.request_today_schedule()
        QTimer.singleShot(75_000, lambda: self._release_vk_schedule_request(request_id))

    def _release_vk_schedule_request(self, request_id: int) -> None:
        if request_id != self._vk_schedule_request_id:
            return
        if self._vk_schedule_request_active:
            self.main_window.append_log("VK: расписание не получено за время ожидания, можно повторить обновление.")
        if self.vk_auth_window is not None:
            self.vk_auth_window.stop_schedule_request()
        self._vk_schedule_request_active = False

    @Slot()
    def check_vk_auth_status(self) -> None:
        if self._vk_authorized:
            self.main_window.set_vk_auth_status(True, "Авторизовано")
            return
        self.main_window.set_vk_auth_status(None, "Проверяется")
        self.vk_auth_checker.check()

    @Slot(bool, str)
    def _on_vk_auth_checked(self, authorized: bool, message: str) -> None:
        if authorized:
            was_authorized = self._vk_authorized
            self._vk_authorized = True
            self._save_vk_auth_hint(True)
            if not was_authorized:
                self.request_vk_today_schedule(show_window=False)
        elif self._vk_authorized:
            self.main_window.set_vk_auth_status(True, "Авторизовано")
            return
        self.main_window.set_vk_auth_status(authorized, message)
        if authorized:
            if not was_authorized:
                self.main_window.append_log("VK: авторизовано.")
                self.notification_window.add_event("Информация", "", "VK авторизация активна", "Сессия сохранена в профиле клиента.")
        else:
            self.main_window.append_log(f"VK: {message.lower()}.")
            self.notification_window.add_event("Предупреждение", "", "VK не авторизован", "Откройте VK вход и войдите в аккаунт для получения расписания из V505_Control.")

    @Slot(str)
    def _on_vk_page_text_ready(self, text: str) -> None:
        if not self._vk_schedule_request_active:
            return
        streams = parse_vk_web_schedule(text, self.settings.source, now_moscow().date())
        if not streams:
            return
        self._vk_schedule_request_active = False
        if self.vk_auth_window is not None:
            self.vk_auth_window.stop_schedule_request()
        signature = "|".join(f"{stream.room}:{stream.time}:{stream.subject}" for stream in streams)
        if signature == self._last_vk_schedule_signature:
            self.main_window.set_streams(streams, self.main_window.selected_stream_keys() if self.main_window.streams else None)
            self.main_window.update_cards(self.settings)
            self.main_window.show_status(f"VK расписание обновлено: {len(streams)} аудиторий")
            return
        self._last_vk_schedule_signature = signature
        selected_keys = self.main_window.selected_stream_keys() if self.main_window.streams else None
        self.main_window.set_streams(streams, selected_keys)
        self.main_window.update_cards(self.settings)
        self.main_window.show_status(f"VK расписание получено: {len(streams)} аудиторий")
        self.main_window.append_log(f"VK расписание получено автоматически: {len(streams)} аудиторий.")
        self.notification_window.add_event("Информация", "", "VK расписание получено", f"Аудиторий: {len(streams)}")

    def _load_vk_auth_hint(self) -> bool:
        return (DATA_DIR / "vk_auth_ok.json").exists()

    def _save_vk_auth_hint(self, authorized: bool) -> None:
        marker = DATA_DIR / "vk_auth_ok.json"
        try:
            if authorized:
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text(json.dumps({"authorized": True}, ensure_ascii=False), encoding="utf-8")
            else:
                marker.unlink(missing_ok=True)
        except Exception:
            pass

    @Slot()
    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self.main_window)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.settings = dialog.settings
        save_settings(self.settings)
        self.analysis_manager.update_settings(self.settings.analysis)
        for window in self.stream_windows.values():
            window.settings = self.settings
        self.main_window.update_cards(self.settings)
        self.main_window.append_log("Настройки сохранены.")
        self.notification_window.add_event("Информация", "", "Настройки сохранены")
        self.refresh_schedule()

    @Slot(str, str, object, str)
    def _on_analysis_finished(self, room: str, path: str, summary_obj: object, error: str) -> None:
        if room not in self.stream_windows:
            self.main_window.append_log(f"{room}: вкладка закрыта, результат проверки не учитывается.")
            return
        summary = summary_obj if isinstance(summary_obj, AnalysisSummary) else None

        if summary is not None and self._handle_lesson_start_state(room, path, summary):
            return

        self.main_window.add_analysis_row(room, path, summary, error)
        self.notification_window.add_analysis_result(room, path, summary, error)

        if error:
            self.main_window.append_log(f"{room}: ошибка анализа: {error}")
            self.main_window.show_tray_message("Проблема трансляции", short_analysis_message(room, error=error), warning=True)
            self.show_notifications()
        elif summary:
            if summary.issues_count:
                short_message = short_analysis_message(room, summary)
                self.main_window.append_log(short_message)
                self.main_window.show_tray_message("Проблема трансляции", short_message, warning=True)
                self.show_notifications()
            else:
                self.main_window.append_log(f"{room}: проверка без проблем.")
            self._write_payload(room, path, summary)

        window = self.stream_windows.get(room)
        if window:
            window.apply_analysis_result(summary, error)

    def _handle_lesson_start_state(self, room: str, path: str, summary: AnalysisSummary) -> bool:
        if room in self._lesson_started_rooms:
            return False

        if _summary_waits_for_video(summary):
            if room not in self._lesson_not_started_rooms:
                self._lesson_not_started_rooms.add(room)
                message = f"{room} - занятие не началось"
                self.notification_window.add_event("Проверка", room, message)
                self.main_window.append_log(message)
            return True

        self._lesson_started_rooms.add(room)
        was_waiting = room in self._lesson_not_started_rooms
        self._lesson_not_started_rooms.discard(room)

        if summary.issues_count == 0:
            message = f"{room} - занятие началось, всё хорошо"
        elif was_waiting:
            message = f"{room} - занятие началось"
        else:
            message = ""
        if message:
            self.notification_window.add_event("Проверка", room, message)
            self.main_window.append_log(message)

        if summary.issues_count == 0:
            self.main_window.add_analysis_row(room, path, summary, "")
            self._write_payload(room, path, summary)
            window = self.stream_windows.get(room)
            if window:
                window.apply_analysis_result(summary, "")
            return True

        return False

    def _write_payload(self, room: str, video_path: str, summary: AnalysisSummary) -> None:
        if not video_path:
            return
        payload_path = Path(video_path).with_suffix(".json")
        try:
            payload_path.write_text(json.dumps(summary.payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            self.main_window.append_log(f"{room}: не удалось сохранить JSON анализа: {exc}")
            self.notification_window.add_event("Ошибка", room, "Не удалось сохранить JSON анализа", str(exc))
        if not self.settings.analysis.keep_video_fragments:
            try:
                Path(video_path).unlink(missing_ok=True)
            except Exception as exc:
                self.main_window.append_log(f"{room}: не удалось удалить фрагмент: {exc}")
                self.notification_window.add_event("Ошибка", room, "Не удалось удалить фрагмент", str(exc))

    def _check_launch_schedule(self) -> None:
        launch_time = parse_hhmm(self.settings.launch.launch_time_msk)
        if not launch_time:
            return

        now = now_moscow()
        today = now.strftime("%Y-%m-%d")
        launch_dt = now.replace(hour=launch_time[0], minute=launch_time[1], second=0, microsecond=0)
        remind_dt = launch_dt - timedelta(minutes=max(1, int(self.settings.launch.remind_minutes_before)))

        if self.last_reminder_date != today and remind_dt <= now < launch_dt:
            self.last_reminder_date = today
            self._show_prelaunch_prompt()

        if (
            self.settings.launch.auto_launch_at_time
            and self.last_auto_launch_date != today
            and launch_dt <= now < launch_dt + timedelta(minutes=2)
        ):
            self.last_auto_launch_date = today
            self.launch_selected()

    def _check_recording_schedule(self) -> None:
        if not self._auto_recording_enabled:
            return
        now = now_moscow()
        today = now.strftime("%Y-%m-%d")
        if self._last_auto_recording_date == today:
            return
        record_dt = now.replace(
            hour=self._auto_recording_hour,
            minute=self._auto_recording_minute,
            second=0,
            microsecond=0,
        )
        if record_dt <= now < record_dt + timedelta(minutes=5):
            if not self.stream_windows:
                self.main_window.append_log("Автозапись ждёт открытые вкладки трансляций.")
                return
            self._last_auto_recording_date = today
            self._start_recording_on_all_streams("автозапуск по времени")

    def _show_prelaunch_prompt(self) -> None:
        self.refresh_schedule()
        self.main_window.bring_to_front()
        text = "Проверьте список аудиторий перед запуском: по умолчанию выбраны все."
        self.main_window.show_tray_message("Скоро запуск трансляций", text)
        self.notification_window.add_event("Предупреждение", "", "Скоро запуск трансляций", text)
        self.show_notifications()
        self.main_window.show_info("Проверка перед запуском", text)

    def shutdown(self) -> None:
        self.close_stream_windows()
        self.analysis_manager.shutdown()
        self._cleanup_results_folder("при закрытии")

    def _cleanup_results_folder(self, reason: str) -> None:
        try:
            removed = cleanup_results_folder(self.settings.analysis.output_dir)
        except Exception as exc:
            if hasattr(self, "main_window"):
                self.main_window.append_log(f"Не удалось очистить папку результатов ({reason}): {exc}")
            return
        if removed and hasattr(self, "main_window"):
            self.main_window.append_log(f"Папка результатов очищена ({reason}): удалено {removed}.")

    def _run_startup_healthcheck(self) -> None:
        issues = run_startup_healthcheck(self.settings)
        if not issues:
            self.notification_window.add_event("Информация", "", "Проверка готовности пройдена")
            self.main_window.append_log("Проверка готовности пройдена.")
            return
        for issue in issues:
            self.notification_window.add_event(issue.level, "", issue.title, issue.details)
            self.main_window.append_log(f"{issue.level}: {issue.title}. {issue.details}")
        if any(issue.level == "Ошибка" for issue in issues):
            self.main_window.show_tray_message("Клиент требует внимания", "Есть ошибки готовности. Откройте окно уведомлений.", warning=True)
            self.show_notifications()


def _screens() -> list[ScreenRect]:
    return [
        ScreenRect(
            x=screen.availableGeometry().x(),
            y=screen.availableGeometry().y(),
            width=screen.availableGeometry().width(),
            height=screen.availableGeometry().height(),
        )
        for screen in QApplication.screens()
    ]


def _screens_with_notification_strip(strip_width: int = 240) -> tuple[list[ScreenRect], ScreenRect]:
    screens = _screens()
    if not screens:
        screens = [ScreenRect(0, 0, 1280, 720)]
    rightmost_index = max(range(len(screens)), key=lambda index: screens[index].x + screens[index].width)
    adjusted: list[ScreenRect] = []
    notification_rect = screens[rightmost_index]
    for index, screen in enumerate(screens):
        if index == rightmost_index:
            width = max(320, screen.width - strip_width)
            adjusted.append(ScreenRect(screen.x, screen.y, width, screen.height))
            notification_rect = ScreenRect(screen.x + width, screen.y, strip_width, screen.height)
        else:
            adjusted.append(screen)
    return adjusted, notification_rect


def _recording_title(room: str, date_text: str | None = None) -> str:
    normalized_room = _recording_room_name(room)
    current_date = date_text or now_moscow().strftime("%d_%m_%Y")
    return f"{normalized_room} {current_date}"


def _recording_datetime_for_today(hour: int, minute: int, now: datetime | None = None) -> datetime:
    now = now or now_moscow()
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _recording_time_is_valid(hour: int, minute: int, now: datetime | None = None) -> bool:
    now = now or now_moscow()
    record_dt = _recording_datetime_for_today(hour, minute, now)
    return record_dt > now


def _recording_room_name(room: str) -> str:
    return room.replace("-", "").replace("–", "").replace("—", "").replace(" ", "")


def _recording_state_message(state: str) -> str:
    messages = {
        "gear_not_found": "Не нашлась шестерёнка настроек звонка.",
        "title_field_not_found": "Окно записи открылось, но поле названия не найдено.",
        "submit_not_found": "Окно записи открылось, но кнопка подтверждения не найдена.",
        "record_action_not_found": "Меню настроек открылось, но пункт записи звонка не найден.",
        "record_dialog_not_opened": "Пункт записи найден, но окно создания записи не открылось.",
        "closed": "Вкладка закрыта.",
        "unknown": "Не удалось получить результат команды.",
    }
    return messages.get(state, f"Состояние: {state}")


def _summary_waits_for_video(summary: AnalysisSummary) -> bool:
    problem = short_problem(summary).lower()
    payload_text = _payload_text(summary.payload).lower()
    text = f"{problem} {payload_text}"
    wait_markers = (
        "нет видео",
        "пустая аудитория",
        "нет преподавателя",
        "камера выключена",
        "окно не найдено",
        "черный экран",
        "чёрный экран",
        "преподаватель отсутствует",
        "рабочее место без преподавателя",
    )
    return any(marker in text for marker in wait_markers)


def _payload_text(value: object) -> str:
    if isinstance(value, dict):
        return " ".join(f"{key} {_payload_text(item)}" for key, item in value.items())
    if isinstance(value, list):
        return " ".join(_payload_text(item) for item in value)
    return str(value)
