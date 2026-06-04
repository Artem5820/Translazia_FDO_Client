from __future__ import annotations

from typing import Callable
import json
import time

from PySide6.QtCore import QEvent, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QCloseEvent, QKeyEvent, QResizeEvent
from PySide6.QtWidgets import QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from ..analysis import AnalysisManager, AnalysisSummary
from ..config import AppSettings
from ..controllers.bridge import AppBridge
from ..models import StreamRoom
from ..services.capture import StreamCaptureSession
from ..services.vk_web_profile import vk_web_profile


class StreamWindow(QMainWindow):
    closed = Signal(str)
    audio_muted_changed = Signal(str, bool)
    launch_state_changed = Signal(str, str)
    focus_mode_requested = Signal(str)
    focus_mode_exited = Signal()
    next_stream_requested = Signal(str)
    previous_stream_requested = Signal(str)
    multiwindow_requested = Signal()

    def __init__(
        self,
        stream: StreamRoom,
        settings: AppSettings,
        analysis_manager: AnalysisManager,
        bridge: AppBridge,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.stream = stream
        self.settings = settings
        self.analysis_manager = analysis_manager
        self.bridge = bridge
        self.capture: StreamCaptureSession | None = None
        self._join_clicked = False
        self._join_clicked_at = 0.0
        self._in_call = False
        self._page_loaded = False
        self._last_recovery_at = 0.0
        self._focus_mode_active = False
        self._closing = False
        self._closed_emitted = False
        self._audio_muted = False
        self._recording_assistant_id = 0
        self._pending_timers: list[QTimer] = []
        self.recovery_timer = QTimer(self)
        self.recovery_timer.timeout.connect(self._inspect_call_state)
        self.analysis_timer = QTimer(self)
        self.analysis_timer.timeout.connect(self.start_capture)
        self.setWindowTitle(f"Трансляция {stream.room}")
        self.resize(900, 560)
        self._build_ui()
        self._configure_web_engine()
        self.view.setUrl(QUrl(stream.url))
        self.recovery_timer.start(6500)
        self._start_analysis_timer()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.view = QWebEngineView()
        self.view.setPage(QWebEnginePage(vk_web_profile(), self.view))
        layout.addWidget(self.view, 1)
        self.room_badge = QPushButton(self.stream.room, self)
        self.room_badge.setObjectName("streamRoomBadge")
        self.room_badge.setFixedSize(92, 32)
        self.room_badge.setEnabled(False)
        self.room_badge.setToolTip("Текущая аудитория")
        self.mute_button = QPushButton(self)
        self.mute_button.setObjectName("streamMuteButton")
        self.mute_button.setFixedSize(92, 32)
        self.mute_button.clicked.connect(self.toggle_audio_muted)
        self.mute_button.setStyleSheet(
            """
            QPushButton#streamMuteButton {
                background: rgba(255, 255, 255, 232);
                color: #00328a;
                border: 1px solid rgba(0, 76, 190, 180);
                border-radius: 8px;
                font-weight: 700;
            }
            QPushButton#streamMuteButton:hover {
                background: #ffffff;
                border-color: #006dff;
            }
            """
        )
        self._update_mute_button()
        self.refresh_button = QPushButton("⟳", self)
        self.refresh_button.setObjectName("streamRefreshButton")
        self.refresh_button.setFixedSize(34, 34)
        self.refresh_button.setToolTip("Обновить вкладку и повторить подключение")
        self.refresh_button.clicked.connect(self.manual_reload_and_retry_join)
        self.room_badge.raise_()
        self.mute_button.raise_()
        self.refresh_button.raise_()
        if hasattr(self, "recording_hint"):
            hint_width = min(max(360, width - 48), 620)
            self.recording_hint.setFixedWidth(hint_width)
            self.recording_hint.adjustSize()
            self.recording_hint.move(max(margin, (width - self.recording_hint.width()) // 2), 54)
            if self.recording_hint.isVisible():
                self.recording_hint.raise_()
        self.prev_button = QPushButton("‹", self)
        self.prev_button.setObjectName("streamNavButton")
        self.prev_button.setFixedSize(42, 72)
        self.prev_button.setToolTip("Предыдущая аудитория")
        self.prev_button.clicked.connect(lambda: self.previous_stream_requested.emit(self.stream.room))
        self.prev_button.hide()

        self.next_button = QPushButton("›", self)
        self.next_button.setObjectName("streamNavButton")
        self.next_button.setFixedSize(42, 72)
        self.next_button.setToolTip("Следующая аудитория")
        self.next_button.clicked.connect(lambda: self.next_stream_requested.emit(self.stream.room))
        self.next_button.hide()

        self.close_stream_button = QPushButton("Закрыть", self)
        self.close_stream_button.setObjectName("streamCloseButton")
        self.close_stream_button.setFixedSize(104, 34)
        self.close_stream_button.setToolTip("Закрыть эту трансляцию")
        self.close_stream_button.clicked.connect(self.close)
        self.close_stream_button.hide()

        self.multiwindow_button = QPushButton("Многооконность", self)
        self.multiwindow_button.setObjectName("streamMultiwindowButton")
        self.multiwindow_button.setFixedSize(136, 34)
        self.multiwindow_button.setToolTip("Вернуться к виду всех трансляций")
        self.multiwindow_button.clicked.connect(self.multiwindow_requested.emit)
        self.multiwindow_button.hide()

        self.recording_hint = QLabel(
            "Откройте в VK: шестерёнка → Записать звонок. Название заполнится автоматически.",
            self,
        )
        self.recording_hint.setObjectName("streamRecordingHint")
        self.recording_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.recording_hint.setWordWrap(True)
        self.recording_hint.hide()

        self.setStyleSheet(
            self.styleSheet()
            + """
            QPushButton#streamRoomBadge {
                background: rgba(255, 255, 255, 232);
                color: #00328a;
                border: 1px solid rgba(0, 76, 190, 180);
                border-radius: 8px;
                font-weight: 800;
            }
            QPushButton#streamRoomBadge:disabled {
                color: #00328a;
            }
            QPushButton#streamNavButton {
                background: rgba(255, 255, 255, 220);
                color: #00328a;
                border: 1px solid rgba(0, 76, 190, 170);
                border-radius: 10px;
                font-size: 34px;
                font-weight: 800;
            }
            QPushButton#streamNavButton:hover {
                background: #ffffff;
                border-color: #006dff;
            }
            QPushButton#streamRefreshButton {
                background: rgba(255, 255, 255, 232);
                color: #00328a;
                border: 1px solid rgba(0, 76, 190, 170);
                border-radius: 8px;
                font-size: 18px;
                font-weight: 900;
                padding: 0;
            }
            QPushButton#streamRefreshButton:hover {
                background: #ffffff;
                border-color: #006dff;
            }
            QPushButton#streamCloseButton {
                background: rgba(255, 255, 255, 232);
                color: #9a1b1b;
                border: 1px solid rgba(190, 0, 0, 150);
                border-radius: 8px;
                font-weight: 800;
            }
            QPushButton#streamCloseButton:hover {
                background: #fff3f3;
                border-color: #d52828;
            }
            QPushButton#streamMultiwindowButton {
                background: rgba(255, 255, 255, 232);
                color: #00328a;
                border: 1px solid rgba(0, 76, 190, 170);
                border-radius: 8px;
                font-weight: 800;
            }
            QPushButton#streamMultiwindowButton:hover {
                background: #ffffff;
                border-color: #006dff;
            }
            QLabel#streamRecordingHint {
                background: rgba(255, 255, 255, 238);
                color: #0635b8;
                border: 1px solid rgba(0, 76, 190, 180);
                border-radius: 8px;
                padding: 8px 12px;
                font-weight: 800;
            }
            """
        )
        self.setCentralWidget(root)

    def set_focus_controls_visible(self, visible: bool) -> None:
        for button in (self.prev_button, self.next_button, self.close_stream_button, self.multiwindow_button):
            button.setVisible(visible)
            if visible:
                button.raise_()
        self.refresh_button.raise_()
        QTimer.singleShot(0, self._position_overlay_buttons)

    def set_focus_mode_active(self, active: bool) -> None:
        self._focus_mode_active = active
        self.set_focus_controls_visible(active)

    def _configure_web_engine(self) -> None:
        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        self.view.loadFinished.connect(self._on_load_finished)
        self.view.page().featurePermissionRequested.connect(self._grant_feature_permission)

    @Slot(bool)
    def _on_load_finished(self, ok: bool) -> None:
        self._page_loaded = bool(ok)
        self.setWindowTitle(f"Трансляция {self.stream.room}" if ok else f"Трансляция {self.stream.room} - ошибка загрузки")
        self.set_audio_muted(self._audio_muted, emit_signal=False)
        if ok:
            self.launch_state_changed.emit(self.stream.room, "loaded")
            self._schedule_join_attempts()
        else:
            self.launch_state_changed.emit(self.stream.room, "load_failed")

    @Slot()
    def toggle_audio_muted(self) -> None:
        self.set_audio_muted(not self._audio_muted)

    def set_audio_muted(self, muted: bool, emit_signal: bool = True) -> None:
        self._audio_muted = bool(muted)
        try:
            self.view.page().setAudioMuted(self._audio_muted)
        except RuntimeError:
            return
        self._update_mute_button()
        if emit_signal:
            self.audio_muted_changed.emit(self.stream.room, self._audio_muted)

    def is_audio_muted(self) -> bool:
        return self._audio_muted

    def _update_mute_button(self) -> None:
        if not hasattr(self, "mute_button"):
            return
        self.mute_button.setText("Вкл. звук" if self._audio_muted else "Откл. звук")
        self.mute_button.setToolTip(
            "Включить звук этой трансляции" if self._audio_muted else "Отключить звук этой трансляции"
        )

    def _schedule_join_attempts(self) -> None:
        for delay in (900, 1800, 3200, 5200, 8000, 12000, 18000, 26000):
            self._schedule_once(delay, self._try_join_call)

    def retry_join(self) -> None:
        if self._closing or self._in_call:
            return
        self._join_clicked = False
        self._schedule_join_attempts()

    @Slot()
    def manual_reload_and_retry_join(self) -> None:
        if self._closing:
            return
        self.launch_state_changed.emit(self.stream.room, "manual_reloaded")
        self.reload_and_retry_join(force=True)

    def reload_and_retry_join(self, force: bool = False) -> None:
        if self._closing or (self._in_call and not force):
            return
        self._in_call = False
        self._join_clicked = False
        self._join_clicked_at = 0.0
        self._page_loaded = False
        try:
            target_url = QUrl(self.stream.url)
            if self.view.url() == target_url:
                self.view.reload()
            else:
                self.view.setUrl(target_url)
        except RuntimeError:
            self._closing = True

    def _recover_call_page(self, reason: str) -> None:
        if self._closing:
            return
        now = time.monotonic()
        if now - self._last_recovery_at < 12:
            return
        self._last_recovery_at = now
        self._in_call = False
        self._join_clicked = False
        self._join_clicked_at = 0.0
        self.launch_state_changed.emit(self.stream.room, reason)
        self.reload_and_retry_join()

    def _schedule_once(self, delay_ms: int, callback: Callable[[], None]) -> None:
        timer = QTimer(self)
        timer.setSingleShot(True)

        def fire() -> None:
            if timer in self._pending_timers:
                self._pending_timers.remove(timer)
            if not self._closing:
                callback()
            timer.deleteLater()

        timer.timeout.connect(fire)
        self._pending_timers.append(timer)
        timer.start(delay_ms)

    def _try_join_call(self) -> None:
        if self._closing or self._in_call:
            return
        script = """
(() => {
  const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
  };
  const text = document.body ? document.body.innerText : '';
  const selector = 'button, [role="button"], a, .vkuiButton, .Button, [tabindex], div, span';
  const buttons = Array.from(document.querySelectorAll(selector));
  for (const button of buttons) {
    const label = norm(button.innerText || button.textContent || button.getAttribute('aria-label'));
    if (!visible(button) || label.length > 80) continue;
    if (/^(Присоединиться|Войти|Join|Continue|Продолжить)$/i.test(label)) {
      button.scrollIntoView({block: 'center', inline: 'center'});
      button.click();
      return {clicked: true, inCall: false, label};
    }
  }
  const inCall =
    /Во время звонка/i.test(text) ||
    /Включите камеру/i.test(text) ||
    /Выключить микрофон|Включить микрофон/i.test(text) ||
    /Покинуть звонок/i.test(text) ||
    ((/В звонке\\s+\\d+\\s+участник/i.test(text) || /В звонке пока никого нет/i.test(text)) &&
      !/Присоединиться|Войти|Join|Continue|Продолжить/i.test(text));
  return {clicked: false, inCall, label: ''};
})()
"""
        try:
            self.view.page().runJavaScript(script, self._on_join_attempt)
        except RuntimeError:
            self._closing = True

    def _on_join_attempt(self, result: object) -> None:
        if self._closing:
            return
        if not isinstance(result, dict):
            return
        if result.get("inCall"):
            self._in_call = True
            self._join_clicked = False
            self._join_clicked_at = 0.0
            self.setWindowTitle(f"Трансляция {self.stream.room} - открыто")
            self.launch_state_changed.emit(self.stream.room, "connected")
            return
        if result.get("clicked"):
            self._join_clicked = True
            self._join_clicked_at = time.monotonic()
            self.setWindowTitle(f"Трансляция {self.stream.room} - подключение")
            self.launch_state_changed.emit(self.stream.room, "join_clicked")
            self._schedule_once(3500, self._try_join_call)

    def _inspect_call_state(self) -> None:
        if self._closing or not self._page_loaded:
            return
        script = """
(() => {
  const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const text = document.body ? document.body.innerText : '';
  const buttons = Array.from(document.querySelectorAll('button, [role="button"], a, .vkuiButton, .Button, [tabindex], div, span'));
  const hasJoinButton = buttons.some((button) => {
    const label = norm(button.innerText || button.textContent || button.getAttribute('aria-label'));
    if (!label || label.length > 80) return false;
    return /^(Присоединиться|Войти|Join|Continue|Продолжить)$/i.test(label);
  });
  const hasCallError =
    /Не удалось позвонить/i.test(text) ||
    /произошла ошибка[^\\n]{0,120}попробуйте/i.test(text) ||
    /попробуйте еще раз/i.test(text);
  const inCall =
    /Во время звонка/i.test(text) ||
    /Включите камеру/i.test(text) ||
    /Выключить микрофон|Включить микрофон/i.test(text) ||
    /Покинуть звонок/i.test(text) ||
    ((/В звонке\\s+\\d+\\s+участник/i.test(text) || /В звонке пока никого нет/i.test(text)) && !hasJoinButton);
  return {hasCallError, inCall, hasJoinButton};
})()
"""
        try:
            self.view.page().runJavaScript(script, self._on_call_state_inspected)
        except RuntimeError:
            self._closing = True

    def _on_call_state_inspected(self, result: object) -> None:
        if self._closing or not isinstance(result, dict):
            return
        if result.get("inCall"):
            if not self._in_call:
                self._in_call = True
                self._join_clicked = False
                self._join_clicked_at = 0.0
                self.setWindowTitle(f"Трансляция {self.stream.room} - открыто")
                self.launch_state_changed.emit(self.stream.room, "connected")
            return
        if result.get("hasCallError"):
            self._recover_call_page("call_error_reloaded")
            return
        if result.get("hasJoinButton"):
            self._try_join_call()
            return
        if self._join_clicked and self._join_clicked_at and time.monotonic() - self._join_clicked_at > 18:
            self._recover_call_page("join_timeout_reloaded")

    def launch_state(self) -> str:
        if self._in_call:
            return "connected"
        if self._join_clicked:
            return "join_clicked"
        if self._page_loaded:
            return "loaded"
        return "loading"

    def ensure_call_recording(self, title: str, callback: Callable[[dict[str, object]], None]) -> None:
        if self._closing:
            callback({"state": "closed", "recording": False})
            return
        if self.isMinimized() or not self.isVisible():
            callback({"state": "window_not_visible", "recording": False})
            return
        self._recording_assistant_id += 1
        assistant_id = self._recording_assistant_id
        self._show_recording_hint()
        script = _START_RECORDING_SCRIPT.replace("__RECORDING_TITLE__", json.dumps(title, ensure_ascii=False))
        self._run_recording_assistant(script, callback, assistant_id, time.monotonic())

    def _run_recording_assistant(
        self,
        script: str,
        callback: Callable[[dict[str, object]], None],
        assistant_id: int,
        started_at: float,
    ) -> None:
        if assistant_id != self._recording_assistant_id:
            return
        if self._closing:
            callback({"state": "closed", "recording": False})
            return
        try:
            self.view.page().runJavaScript(
                script,
                lambda result: self._on_recording_assistant_result(script, callback, assistant_id, started_at, result),
            )
        except RuntimeError:
            self._closing = True
            self._hide_recording_hint()
            callback({"state": "closed", "recording": False})

    def _on_recording_assistant_result(
        self,
        script: str,
        callback: Callable[[dict[str, object]], None],
        assistant_id: int,
        started_at: float,
        result: object,
    ) -> None:
        if self._closing or assistant_id != self._recording_assistant_id:
            return
        payload = _recording_result(result)
        state = str(payload.get("state", "unknown"))
        if state == "waiting_record_dialog" and time.monotonic() - started_at < 45:
            QTimer.singleShot(1000, lambda: self._run_recording_assistant(script, callback, assistant_id, started_at))
            return
        if state == "waiting_record_dialog":
            payload = {**payload, "state": "record_dialog_timeout"}
        self._hide_recording_hint()
        callback(payload)

    def _show_recording_hint(self) -> None:
        self.recording_hint.show()
        self._position_overlay_buttons()

    def _hide_recording_hint(self) -> None:
        if hasattr(self, "recording_hint"):
            self.recording_hint.hide()

    def inspect_recording_state(self, callback: Callable[[dict[str, object]], None]) -> None:
        if self._closing:
            callback({"state": "closed", "recording": False})
            return
        try:
            self.view.page().runJavaScript(_INSPECT_RECORDING_SCRIPT, lambda result: callback(_recording_result(result)))
        except RuntimeError:
            self._closing = True
            callback({"state": "closed", "recording": False})

    @Slot(QUrl, QWebEnginePage.Feature)
    def _grant_feature_permission(self, origin: QUrl, feature: QWebEnginePage.Feature) -> None:
        self.view.page().setFeaturePermission(
            origin,
            feature,
            QWebEnginePage.PermissionPolicy.PermissionGrantedByUser,
        )

    def _start_analysis_timer(self) -> None:
        if not self.settings.analysis.enabled:
            return
        delay_ms = 10_000
        interval_ms = max(60_000, int(self.settings.analysis.interval_minutes) * 60_000)
        self._schedule_once(delay_ms, self.start_capture)
        self.analysis_timer.start(interval_ms)

    @Slot()
    def start_capture(self) -> None:
        if self._closing:
            return
        if self.capture and self.capture.active:
            return
        if not self.settings.analysis.enabled:
            return
        self.capture = StreamCaptureSession(self.stream.room, self.view, self.settings, self)
        self.capture.finished.connect(self._on_capture_finished)
        self.capture.failed.connect(self._on_capture_failed)
        self.capture.start()

    @Slot(str, str)
    def _on_capture_finished(self, room: str, path: str) -> None:
        if self._closing:
            return
        self.analysis_manager.submit_video(room, path, self._analysis_callback)

    @Slot(str, str)
    def _on_capture_failed(self, room: str, message: str) -> None:
        if self._closing:
            return
        self.bridge.analysis_finished.emit(room, "", None, message)

    def _analysis_callback(self, room: str, path: str, summary: AnalysisSummary | None, error: str | None) -> None:
        if self._closing:
            return
        self.bridge.analysis_finished.emit(room, path, summary, error or "")

    def apply_analysis_result(self, summary: AnalysisSummary | None, error: str) -> None:
        if self._closing:
            return
        if error:
            self.setWindowTitle(f"Трансляция {self.stream.room} - ошибка анализа")
            return
        if not summary:
            return
        if summary.issues_count:
            self.setWindowTitle(f"Трансляция {self.stream.room} - проблем: {summary.issues_count}")
        else:
            self.setWindowTitle(f"Трансляция {self.stream.room}")

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._position_overlay_buttons()

    def _position_overlay_buttons(self) -> None:
        if not hasattr(self, "mute_button"):
            return
        margin = 12
        width = max(1, self.width())
        height = max(1, self.height())
        close_visible = getattr(self, "close_stream_button", None) is not None and self.close_stream_button.isVisible()
        if close_visible:
            self.close_stream_button.move(max(margin, width - self.close_stream_button.width() - margin), margin)
            self.refresh_button.move(
                max(margin, self.close_stream_button.x() - self.refresh_button.width() - margin),
                margin,
            )
            self.multiwindow_button.move(
                max(margin, self.refresh_button.x() - self.multiwindow_button.width() - margin),
                margin,
            )
            mute_x = self.multiwindow_button.x() - self.mute_button.width() - margin
            self.mute_button.move(max(margin, mute_x), margin)
            room_x = self.mute_button.x() - self.room_badge.width() - margin
            self.room_badge.move(max(margin, room_x), margin)
            self.prev_button.move(margin, max(margin, (height - self.prev_button.height()) // 2))
            self.next_button.move(max(margin, width - self.next_button.width() - margin), max(margin, (height - self.next_button.height()) // 2))
            self.prev_button.raise_()
            self.next_button.raise_()
            self.multiwindow_button.raise_()
            self.refresh_button.raise_()
            self.close_stream_button.raise_()
        else:
            self.refresh_button.move(max(margin, width - self.refresh_button.width() - margin), margin)
            mute_x = self.refresh_button.x() - self.mute_button.width() - margin
            self.mute_button.move(max(margin, mute_x), margin)
            room_x = self.mute_button.x() - self.room_badge.width() - margin
            self.room_badge.move(max(margin, room_x), margin)
        self.room_badge.raise_()
        self.mute_button.raise_()
        self.refresh_button.raise_()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() != QEvent.Type.WindowStateChange:
            return
        if self.isMaximized():
            self._focus_mode_active = True
            self.focus_mode_requested.emit(self.stream.room)
        elif self._focus_mode_active and not self.isMaximized():
            self._focus_mode_active = False
            self.focus_mode_exited.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self.next_stream_requested.emit(self.stream.room)
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self.previous_stream_requested.emit(self.stream.room)
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.prepare_for_close(emit_closed=True)
        self.hide()
        event.ignore()

    def prepare_for_close(self, emit_closed: bool = True) -> None:
        if self._closing:
            if emit_closed and not self._closed_emitted:
                self._closed_emitted = True
                self.closed.emit(self.stream.room)
            return
        self._closing = True
        for timer in list(self._pending_timers):
            timer.stop()
            timer.deleteLater()
        self._pending_timers.clear()
        self.analysis_timer.stop()
        if self.capture:
            try:
                self.capture.finished.disconnect(self._on_capture_finished)
                self.capture.failed.disconnect(self._on_capture_failed)
            except (RuntimeError, TypeError):
                pass
            self.capture.stop()
            self.capture.deleteLater()
            self.capture = None
        if emit_closed and not self._closed_emitted:
            self._closed_emitted = True
            self.closed.emit(self.stream.room)


def _recording_result(result: object) -> dict[str, object]:
    if isinstance(result, dict):
        return result
    return {"state": "no_result", "recording": False}


_INSPECT_RECORDING_SCRIPT = """
(() => {
  const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const text = norm(document.body ? document.body.innerText : '');
  const recording =
    /Ид[её]т запись звонка/i.test(text) ||
    /\\b\\d{2}:\\d{2}\\s+Завершить\\b/i.test(text) ||
    /запись звонка[^\\n]{0,100}Завершить/i.test(text);
  return {state: recording ? 'recording' : 'not_recording', recording, marker: text.slice(0, 300)};
})()
"""


_START_RECORDING_SCRIPT = """
(async () => {
  const title = __RECORDING_TITLE__;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const visible = (node) => {
    if (!node || !node.getBoundingClientRect) return false;
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
  };
  const text = () => norm(document.body ? document.body.innerText : '');
  const label = (node) => norm(
    node.innerText ||
    node.textContent ||
    node.getAttribute('aria-label') ||
    node.getAttribute('title') ||
    node.getAttribute('placeholder') ||
    ''
  );
  const isRecording = () => {
    const pageText = text();
    return (
      /Ид[её]т запись звонка/i.test(pageText) ||
      /\\b\\d{2}:\\d{2}\\s+Завершить\\b/i.test(pageText) ||
      /запись звонка[^\\n]{0,100}Завершить/i.test(pageText)
    );
  };
  const dialogOpen = () => /Создать запись звонка|Название/i.test(text());
  const findTitleField = () => {
    const fields = Array.from(document.querySelectorAll('input, textarea, [contenteditable="true"]')).filter(visible);
    if (!fields.length) return null;
    return fields.find((field) => /групповой звонок|название|звонок|call|record/i.test(norm(
      field.value ||
      field.innerText ||
      field.textContent ||
      field.getAttribute('placeholder') ||
      field.getAttribute('aria-label') ||
      ''
    ))) || fields[fields.length - 1];
  };
  const setFieldValue = (field, value) => {
    field.focus();
    if ('value' in field) {
      const setter =
        Object.getOwnPropertyDescriptor(field.constructor.prototype, 'value')?.set ||
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set ||
        Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
      if (setter) setter.call(field, value);
      else field.value = value;
      field.dispatchEvent(new Event('input', {bubbles: true}));
      field.dispatchEvent(new Event('change', {bubbles: true}));
      return;
    }
    field.textContent = value;
    field.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: value}));
  };
  const findSubmit = () => {
    const nodes = Array.from(document.querySelectorAll('button, [role="button"], .vkuiButton, .Button, [tabindex]')).filter(visible);
    return nodes.find((node) => /^Записать звонок$/i.test(label(node)) || /^Создать запись/i.test(label(node))) || null;
  };
  const clickNode = (node) => {
    node.scrollIntoView({block: 'center', inline: 'center'});
    const rect = node.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    if (window.PointerEvent) {
      node.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, pointerType: 'mouse'}));
      node.dispatchEvent(new PointerEvent('pointerup', {bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, pointerType: 'mouse'}));
    }
    node.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window, clientX: x, clientY: y}));
    node.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window, clientX: x, clientY: y}));
    node.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window, clientX: x, clientY: y}));
  };

  if (isRecording()) return {state: 'already_recording', recording: true, title};
  if (!dialogOpen()) return {state: 'waiting_record_dialog', recording: false, title};

  const field = findTitleField();
  if (!field) return {state: 'title_field_not_found', recording: false, title};
  setFieldValue(field, title);
  await sleep(250);

  const submit = findSubmit();
  if (!submit) return {state: 'submit_not_found', recording: false, title};
  clickNode(submit);
  await sleep(900);
  return {state: 'record_requested', recording: isRecording(), title};
})()
"""
