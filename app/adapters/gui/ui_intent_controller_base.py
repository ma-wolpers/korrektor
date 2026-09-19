from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.bootstrap.wiring import GuiDependencies

if TYPE_CHECKING:
    from app.adapters.gui.main_window import MainWindow


class UiIntentControllerBase:
    def __init__(self, app: "MainWindow", deps: GuiDependencies) -> None:
        self._app = app
        self._deps = deps
