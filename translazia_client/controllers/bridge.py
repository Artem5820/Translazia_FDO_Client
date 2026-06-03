from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class AppBridge(QObject):
    schedule_loaded = Signal(object, str)
    schedule_failed = Signal(str)
    analysis_finished = Signal(str, str, object, str)
