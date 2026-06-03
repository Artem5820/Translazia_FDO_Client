from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QNetworkCookie

from .vk_web_profile import vk_web_profile


VK_SESSION_COOKIE_NAMES = {"remixsid", "remixstlid", "remixua", "remixnsid", "remixusid", "remixrefresh_token"}


def is_vk_session_cookie(name: str, domain: str) -> bool:
    normalized_domain = domain.lower().lstrip(".")
    normalized_name = name.lower()
    return normalized_domain.endswith("vk.com") and (
        normalized_name in VK_SESSION_COOKIE_NAMES
        or (normalized_name.startswith("remix") and "sid" in normalized_name)
    )


class VkAuthChecker(QObject):
    finished = Signal(bool, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._authorized = False
        self._checking = False
        self._store = None

    def check(self) -> None:
        if self._checking:
            return
        self._authorized = False
        self._checking = True
        self._store = vk_web_profile().cookieStore()
        try:
            self._store.cookieAdded.connect(self._on_cookie_added)
            self._store.loadAllCookies()
        except RuntimeError:
            self._checking = False
            self._store = None
            self.finished.emit(False, "Не авторизовано")
            return
        QTimer.singleShot(1200, self._finish)

    def _on_cookie_added(self, cookie: QNetworkCookie) -> None:
        name = bytes(cookie.name()).decode("utf-8", errors="ignore")
        domain = cookie.domain()
        if is_vk_session_cookie(name, domain):
            self._authorized = True

    def _finish(self) -> None:
        if not self._checking:
            return
        self._checking = False
        store = self._store
        try:
            if store is not None:
                store.cookieAdded.disconnect(self._on_cookie_added)
        except (RuntimeError, TypeError):
            pass
        self._store = None
        message = "Авторизовано" if self._authorized else "Не авторизовано"
        self.finished.emit(self._authorized, message)
