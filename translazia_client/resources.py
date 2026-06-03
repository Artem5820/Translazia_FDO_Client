from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon


PACKAGE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = PACKAGE_DIR / "assets"
LOGO_PATH = ASSETS_DIR / "logo_fdo.png"
LOGO_SMALL_PATH = ASSETS_DIR / "logo_fdo_96.png"
APP_ICON_PATH = ASSETS_DIR / "logo_fdo.ico"


def app_icon() -> QIcon:
    if APP_ICON_PATH.exists():
        return QIcon(str(APP_ICON_PATH))
    if LOGO_PATH.exists():
        return QIcon(str(LOGO_PATH))
    return QIcon()
