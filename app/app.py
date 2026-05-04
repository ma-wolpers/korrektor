from __future__ import annotations

from pathlib import Path

from app.adapters.bootstrap.wiring import AppDependencies, build_gui_dependencies
from app.adapters.gui.main_window import MainWindow
from app.adapters.gui.ui_intent_controller import UiIntentController
from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


def run() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    root = ui.Tk()

    deps: AppDependencies = build_gui_dependencies(base_dir=base_dir)
    window = MainWindow(root=root, deps=deps)
    controller = UiIntentController(app=window, deps=deps)
    window.set_controller(controller)
    window.start()
