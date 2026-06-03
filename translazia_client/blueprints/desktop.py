from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QApplication

from ..controllers.main_controller import MainController


@dataclass(slots=True)
class DesktopBlueprint:
    name: str = "desktop"

    def register(self, app: QApplication) -> MainController:
        controller = MainController(app)
        controller.show()
        return controller
