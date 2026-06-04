from __future__ import annotations

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QAction
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow

from ..resources import app_icon
from ..services.vk_web_profile import vk_web_profile


_MAX_TODAY_REQUESTS = 2


class VkAuthWindow(QMainWindow):
    closed = Signal()
    auth_check_requested = Signal()
    page_auth_detected = Signal(bool, str)
    page_text_ready = Signal(str)
    automation_log = Signal(str)

    def __init__(self, bot_url: str, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.bot_url = bot_url
        self._automation_requested = False
        self._today_clicks = 0
        self._today_click_in_flight = False
        self._today_requested = False
        self._schedule_command_sent = False
        self._schedule_command_in_flight = False
        self._today_retries_scheduled = False
        self.setWindowTitle("VK авторизация | V505_Control")
        self.setWindowIcon(app_icon())
        self.resize(1120, 780)
        self._build_ui()
        self._install_actions()
        self.open_bot()

    def _build_ui(self) -> None:
        self.web = QWebEngineView()
        self.web.setPage(QWebEnginePage(vk_web_profile(), self.web))
        self.web.page().featurePermissionRequested.connect(self._grant_permission)
        self.web.loadFinished.connect(self._on_load_finished)
        self.setCentralWidget(self.web)

    def _install_actions(self) -> None:
        reload_action = QAction("Обновить VK", self)
        reload_action.setShortcut("F5")
        reload_action.triggered.connect(self.web.reload)
        self.addAction(reload_action)

        open_bot_action = QAction("Открыть V505_Control", self)
        open_bot_action.setShortcut("Ctrl+L")
        open_bot_action.triggered.connect(self.open_bot)
        self.addAction(open_bot_action)

        check_action = QAction("Проверить вход", self)
        check_action.setShortcut("Ctrl+Return")
        check_action.triggered.connect(self.auth_check_requested.emit)
        self.addAction(check_action)

    def open_bot(self) -> None:
        self.web.setUrl(QUrl(self.bot_url))

    def request_today_schedule(self) -> None:
        self._automation_requested = True
        self._today_clicks = 0
        self._today_click_in_flight = False
        self._today_requested = False
        self._schedule_command_sent = False
        self._schedule_command_in_flight = False
        self._today_retries_scheduled = False
        self.open_bot()
        self.automation_log.emit("VK: запрашиваю онлайн трансляции на сегодня.")
        self._schedule_command_attempts()
        self._schedule_page_reads()

    def stop_schedule_request(self) -> None:
        self._automation_requested = False
        self._schedule_command_sent = True
        self._schedule_command_in_flight = False
        self._today_click_in_flight = False
        self._today_requested = True
        self._today_retries_scheduled = True

    def has_requested_today_period(self) -> bool:
        return self._today_requested

    def _grant_permission(self, origin: QUrl, feature: QWebEnginePage.Feature) -> None:
        self.web.page().setFeaturePermission(origin, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser)

    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            self.page_auth_detected.emit(False, "VK не загрузился")
            return
        QTimer.singleShot(1200, self._inspect_page)
        QTimer.singleShot(3000, self._inspect_page)

    def _inspect_page(self) -> None:
        auth_script = """
(() => {
  const text = document.body ? document.body.innerText : "";
  const loginVisible = /Войти|Телефон или почта|Введите пароль/.test(text) && !/Мессенджер|V505_Control/.test(text);
  const inVk = location.hostname.endsWith("vk.com");
  const hasMessenger = /Мессенджер|V505_Control|Сообщение|Сегодня|Завтра/.test(text);
  return Boolean(inVk && !loginVisible && hasMessenger);
})()
"""
        self.web.page().runJavaScript(auth_script, self._emit_page_auth)
        self.web.page().runJavaScript("document.body ? document.body.innerText : ''", self._emit_page_text)
        if self._automation_requested and not self._schedule_command_sent and not self._today_requested:
            self._run_schedule_automation()

    def _schedule_command_attempts(self) -> None:
        for delay in (2500, 5500, 9000, 14000, 22000):
            QTimer.singleShot(delay, self._run_schedule_automation)

    def _emit_page_auth(self, authorized: object) -> None:
        is_authorized = bool(authorized)
        self.page_auth_detected.emit(is_authorized, "Авторизовано" if is_authorized else "Не авторизовано")

    def _emit_page_text(self, text: object) -> None:
        if isinstance(text, str) and text.strip():
            self.page_text_ready.emit(text)

    def _run_schedule_automation(self) -> None:
        if not self._automation_requested:
            return
        if self._today_requested:
            return
        if self._schedule_command_in_flight:
            return
        if self._schedule_command_sent:
            self._click_today_button()
            return
        self._schedule_command_in_flight = True
        script = """
(() => {
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
  };
  const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const text = document.body ? document.body.innerText : '';
  const clickableSelector = 'button, [role="button"], a, .vkuiButton, .Button, [tabindex]';
  const fireClick = (node) => {
    node.scrollIntoView({block: 'center', inline: 'center'});
    const rect = node.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    const pointTarget = document.elementFromPoint(x, y) || node;
    for (const type of ['pointerdown', 'mousedown', 'mouseup']) {
      pointTarget.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window, clientX: x, clientY: y}));
    }
    const target = typeof pointTarget.click === 'function' ? pointTarget : node;
    target.click();
  };
  const textNodeCandidates = (patterns, maxLen = 90) => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const items = [];
    while (walker.nextNode()) {
      const textNode = walker.currentNode;
      const label = norm(textNode.nodeValue);
      if (!label || label.length > maxLen || !patterns.some((pattern) => pattern.test(label))) continue;
      const parent = textNode.parentElement;
      if (!parent || !visible(parent)) continue;
      const range = document.createRange();
      range.selectNodeContents(textNode);
      const rect = range.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) continue;
      const clickable = parent.closest(clickableSelector) || parent;
      items.push({clickable, label, rect});
    }
    return items;
  };
  const candidateNodes = () => Array.from(document.querySelectorAll(`${clickableSelector}, div, span`))
    .filter((node) => visible(node))
    .map((node) => {
      const label = norm(node.innerText || node.textContent);
      const clickable = node.closest(clickableSelector) || node;
      const rect = clickable.getBoundingClientRect();
      return {node, clickable, label, rect};
    });
  const clickByText = (patterns, maxLen = 90) => {
    const candidates = candidateNodes()
      .filter((item) => item.label && item.label.length <= maxLen && patterns.some((pattern) => pattern.test(item.label)))
      .concat(textNodeCandidates(patterns, maxLen))
      .sort((left, right) => right.rect.top - left.rect.top);
    if (candidates.length) {
      fireClick(candidates[0].clickable);
      return candidates[0].label;
    }
    return '';
  };

  const periodVisible = /Выберите период/i.test(text) || /^Сегодня$/m.test(text);
  let clicked = '';
  if (periodVisible) {
    clicked = clickByText([/^Сегодня$/i], 40);
    if (clicked) return {status: 'clicked-today', action: clicked};
    return {status: 'period-waiting', action: ''};
  }

  const mainMenuVisible = /🏠?\\s*Меню:/i.test(text) || /1[-–—]Аудитория/i.test(text) || /5[-–—]Онлайн трансляции/i.test(text);
  if (mainMenuVisible) {
    clicked = clickByText([/^5\\s*[-–—]?\\s*Онлайн трансляции$/i], 50);
    if (clicked) return {status: 'clicked-online', action: clicked};
  }

  clicked = clickByText([/^5\\s*[-–—]?\\s*Онлайн трансляции$/i], 50);
  if (clicked) return {status: 'clicked-online', action: clicked};
  clicked = clickByText([/^Сегодня$/i], 40);
  if (clicked) return {status: 'clicked-today', action: clicked};

  const clickSendButton = (editable) => {
    const editorRect = editable.getBoundingClientRect();
    const sendCandidates = Array.from(document.querySelectorAll('button, [role="button"], [aria-label], [title], .vkuiButton, .Button, [tabindex]'))
      .filter((node) => visible(node))
      .map((node) => {
        const rect = node.getBoundingClientRect();
        const label = norm(node.getAttribute('aria-label') || node.getAttribute('title') || node.innerText || node.textContent);
        return {node, rect, label};
      })
      .filter((item) => {
        if (/Отправить|Send/i.test(item.label)) return true;
        const nearEditor = item.rect.left >= editorRect.right - 30
          && item.rect.top >= editorRect.top - 25
          && item.rect.top <= editorRect.bottom + 35
          && item.rect.width <= 80
          && item.rect.height <= 80;
        return nearEditor && item.node.querySelector('svg');
      })
      .sort((left, right) => {
        const score = (label) => /Отправить|Send/i.test(label) ? 1 : 0;
        return score(right.label) - score(left.label) || right.rect.left - left.rect.left;
      });
    if (!sendCandidates.length) return false;
    fireClick(sendCandidates[0].node);
    return true;
  };
  const editable = document.querySelector('[contenteditable="true"], [contenteditable]:not([contenteditable="false"]), [role="textbox"], textarea, input[type="text"]');
  if (editable && visible(editable)) {
    const command = '5-Онлайн трансляции';
    editable.focus();
    if ('value' in editable) {
      editable.value = command;
      editable.dispatchEvent(new Event('input', {bubbles: true}));
    } else {
      document.execCommand('selectAll', false, null);
      document.execCommand('insertText', false, command);
      editable.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: command}));
    }
    editable.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true}));
    editable.dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true}));
    clickSendButton(editable);
    return {status: 'typed-command', action: command};
  }
  return {status: 'not-found', action: ''};
})()
"""
        self.web.page().runJavaScript(script, self._handle_schedule_automation)

    def _handle_schedule_automation(self, result: object) -> None:
        self._schedule_command_in_flight = False
        if not isinstance(result, dict):
            return
        status = str(result.get("status", ""))
        action = str(result.get("action", ""))
        if status == "ready":
            self._automation_requested = False
            self.automation_log.emit("VK: расписание на сегодня найдено.")
            self._schedule_page_reads()
        elif status == "clicked-online":
            self._schedule_command_sent = True
            self.automation_log.emit(f"VK: нажата кнопка {action}.")
            self._schedule_today_retries()
        elif status == "clicked-today":
            self._schedule_command_sent = True
            self._today_requested = True
            self._today_clicks += 1
            self.automation_log.emit("VK: нажата кнопка Сегодня.")
            self._schedule_page_reads()
        elif status == "typed-command":
            self._schedule_command_sent = True
            self.automation_log.emit("VK: команда отправлена текстом.")
            self._schedule_today_retries()
        elif status == "period-waiting":
            self._schedule_today_retries()

    def _schedule_today_retries(self) -> None:
        if self._today_retries_scheduled or self._today_requested:
            return
        self._today_retries_scheduled = True
        for delay in (4500, 9000):
            QTimer.singleShot(delay, self._click_today_button)

    def _click_today_button(self) -> None:
        if not self._automation_requested or self._today_requested:
            return
        if self._today_click_in_flight or self._today_clicks >= _MAX_TODAY_REQUESTS:
            return
        self._today_click_in_flight = True
        script = """
(() => {
  const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const clickableSelector = 'button, [role="button"], a, .vkuiButton, .Button, [tabindex]';
  const visible = (node) => {
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
  };
  const fireClick = (node) => {
    node.scrollIntoView({block: 'center', inline: 'center'});
    const rect = node.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    const pointTarget = document.elementFromPoint(x, y) || node;
    for (const type of ['pointerdown', 'mousedown', 'mouseup']) {
      pointTarget.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window, clientX: x, clientY: y}));
    }
    const target = typeof pointTarget.click === 'function' ? pointTarget : node;
    target.click();
  };
  const textNodeCandidates = () => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const items = [];
    while (walker.nextNode()) {
      const textNode = walker.currentNode;
      const label = norm(textNode.nodeValue);
      if (!/^Сегодня$/i.test(label)) continue;
      const parent = textNode.parentElement;
      if (!parent || !visible(parent)) continue;
      const range = document.createRange();
      range.selectNodeContents(textNode);
      const rect = range.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) continue;
      const clickable = parent.closest(clickableSelector) || parent;
      items.push({label, clickable, rect});
    }
    return items;
  };
  const candidates = Array.from(document.querySelectorAll(`${clickableSelector}, div, span`))
    .filter((node) => visible(node))
    .map((node) => {
      const label = norm(node.innerText || node.textContent);
      const clickable = node.closest(clickableSelector) || node;
      const rect = clickable.getBoundingClientRect();
      return {label, clickable, rect};
    })
    .filter((item) => /^Сегодня$/i.test(item.label) && item.rect.width > 0 && item.rect.height > 0)
    .concat(textNodeCandidates())
    .sort((left, right) => right.rect.top - left.rect.top);
  if (candidates.length) {
    fireClick(candidates[0].clickable);
    return 'clicked';
  }
  return '';
})()
"""
        self.web.page().runJavaScript(script, self._handle_today_click)

    def _handle_today_click(self, clicked: object) -> None:
        self._today_click_in_flight = False
        if clicked == "ready":
            self._today_requested = True
            self.automation_log.emit("VK: расписание на сегодня уже открыто.")
            self._schedule_page_reads()
        elif bool(clicked):
            self._today_clicks += 1
            self._today_requested = True
            self.automation_log.emit("VK: выбран период Сегодня.")
            self._schedule_page_reads()

    def _schedule_page_reads(self) -> None:
        for delay in (700, 1500, 2500, 4000, 6500, 9000, 13_000, 18_000, 25_000, 35_000, 50_000, 65_000):
            QTimer.singleShot(delay, self._inspect_page)

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.closed.emit()
        super().closeEvent(event)
