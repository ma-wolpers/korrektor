from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()

# Tk-Testfenster geben den OS-Vordergrund sofort an das Fenster des Entwicklers
# zurück (keine "geklauten" Tastendrücke während eines Testlaufs); mit
# TK_FOCUS_TESTS=1 deaktiviert. Siehe bw-gui docs/KEYBINDING_CONTRACT.md.
from bw_gui.testing.background_windows import pytest_configure, pytest_unconfigure  # noqa: E402,F401


import pytest  # noqa: E402


@pytest.fixture(scope="session")
def korrektor_window(tmp_path_factory):
    """One real `MainWindow` for all real-Tk tests of a run (synthetic data only).

    ``APPDATA`` points to a temp folder while the dependencies are built, so
    the real settings and the real exam index are never read; the built
    repositories keep those temp paths afterwards. Session scope on purpose:
    creating/destroying several Tk interpreters in one process is flaky on
    Windows (see bw-gui ``tests/conftest.py``).
    """
    base = tmp_path_factory.mktemp("korrektor_window")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("APPDATA", str(base / "appdata"))
        from app.adapters.bootstrap.wiring import build_gui_dependencies
        from app.adapters.gui.main_window import MainWindow
        from app.adapters.gui.ui_intent_controller import UiIntentController

        deps = build_gui_dependencies(base_dir=base / "base")
        main_window = MainWindow(deps=deps)
    assert str(deps.exam_repository.index_root).startswith(str(base))
    main_window.set_controller(UiIntentController(app=main_window, deps=deps))
    main_window.update()
    yield main_window
    main_window.destroy()
