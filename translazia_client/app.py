from __future__ import annotations

import ctypes
import sys

from PySide6.QtWidgets import QApplication

from .blueprints import DesktopBlueprint
from .resources import app_icon
from .services.vk_web_profile import configure_vk_web_profile
from .ui.styles import APP_STYLESHEET


def run() -> int:
    _set_windows_app_user_model_id()
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("ФДО Онлайн")
    app.setApplicationDisplayName("ФДО Онлайн")
    app.setWindowIcon(app_icon())
    configure_vk_web_profile()
    app.setStyleSheet(APP_STYLESHEET)
    controller = DesktopBlueprint().register(app)
    app.aboutToQuit.connect(controller.shutdown)
    app._translazia_controller = controller  # type: ignore[attr-defined]
    return app.exec()


def _set_windows_app_user_model_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TranslaziaFDO.Client")
    except Exception:
        pass
