from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()

# Tk-Testfenster geben den OS-Vordergrund sofort an das Fenster des Entwicklers
# zurück (keine "geklauten" Tastendrücke während eines Testlaufs); mit
# TK_FOCUS_TESTS=1 deaktiviert. Siehe bw-gui docs/KEYBINDING_CONTRACT.md.
from bw_gui.testing.background_windows import pytest_configure, pytest_unconfigure  # noqa: E402,F401


import pytest  # noqa: E402

_DIALOG_METHODS = {
    "messagebox": ("showerror", "showwarning", "showinfo", "askyesno", "askyesnocancel", "askretrycancel"),
    "simpledialog": ("askstring",),
    "choicedialog": ("askchoice",),
    "filedialog": ("askdirectory", "askopenfilename", "askopenfilenames", "asksaveasfilename"),
}


@pytest.fixture(autouse=True)
def _no_unpatched_dialogs(monkeypatch):
    """Safety net: a modal dialog a test did not replace fails the test instead of blocking the run.

    Every dialog of `app.adapters.gui.dialog_services` raises an
    `AssertionError` naming the dialog and its title. Tests that expect a
    dialog patch it themselves (module/test fixtures run after this
    conftest fixture, so their ``monkeypatch.setattr`` wins).
    """
    from app.adapters.gui import dialog_services

    def _refuse(kind):
        def refuse(*args, **kwargs):
            title = args[0] if args else kwargs.get("title", "")
            raise AssertionError(f"Unerwarteter Dialog im Test: {kind}({title!r}) - bitte im Test ersetzen")
        return refuse

    for service_name, methods in _DIALOG_METHODS.items():
        service = getattr(dialog_services, service_name)
        for method in methods:
            monkeypatch.setattr(service, method, _refuse(f"{service_name}.{method}"))


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
