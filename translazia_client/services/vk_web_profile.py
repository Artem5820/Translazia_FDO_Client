from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWebEngineCore import QWebEngineProfile

from ..config import DATA_DIR


_VK_PROFILE: QWebEngineProfile | None = None


def vk_web_profile() -> QWebEngineProfile:
    global _VK_PROFILE
    if _VK_PROFILE is None:
        parent = QCoreApplication.instance()
        _VK_PROFILE = QWebEngineProfile("translazia_fdo_vk", parent)
        _configure_profile(_VK_PROFILE)
    return _VK_PROFILE


def configure_vk_web_profile() -> QWebEngineProfile:
    return vk_web_profile()


def _configure_profile(profile: QWebEngineProfile) -> None:
    profile_root = DATA_DIR / "vk_web_profile"
    cache_root = DATA_DIR / "vk_web_cache"
    profile_root.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    profile.setPersistentStoragePath(str(profile_root))
    profile.setCachePath(str(cache_root))
    profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
