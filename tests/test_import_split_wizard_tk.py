"""Real-Tk tests of the PDF import wizard (Importmodus): lifecycle, error paths, layout, keyboard.

Uses the session-wide real `MainWindow` (``korrektor_window`` in
`conftest.py`, built with ``APPDATA`` redirected to a temp folder - the real
settings and exam index are never read). All PDFs are synthetic. Dialog
services are replaced by recorders. The keyboard test is opt-in via
``TK_FOCUS_TESTS=1`` (see `tk_test_support.FOCUS_ONLY`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tk_test_support import FOCUS_ONLY, build_pdf, pdf_texts, settle

from app.adapters.gui import dialog_services
from app.adapters.gui import main_window_import_split_export as export_module
from app.infrastructure.pdf.pdf_splitter import SplitWriteError


class _Dialogs:
    """Recording replacements for the shared dialog services."""

    def __init__(self) -> None:
        self.files: tuple[str, ...] = ()
        self.directory = ""
        self.yesno_answers: list[bool] = []
        self.infos: list[tuple[str, str]] = []
        self.errors: list[tuple[str, str]] = []
        self.questions: list[tuple[str, str]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(dialog_services.filedialog, "askopenfilenames", lambda **kw: self.files)
        monkeypatch.setattr(dialog_services.filedialog, "askdirectory", lambda **kw: self.directory)
        monkeypatch.setattr(dialog_services.messagebox, "showinfo", lambda t, m, **kw: self.infos.append((t, m)))
        monkeypatch.setattr(dialog_services.messagebox, "showerror", lambda t, m, **kw: self.errors.append((t, m)))

        def _askyesno(title, message, **kwargs):
            self.questions.append((title, message))
            return self.yesno_answers.pop(0)

        monkeypatch.setattr(dialog_services.messagebox, "askyesno", _askyesno)


@pytest.fixture
def window(korrektor_window):
    return korrektor_window


@pytest.fixture
def dialogs(window, monkeypatch):
    recorder = _Dialogs()
    recorder.install(monkeypatch)
    yield recorder
    window._end_import_split_pending()
    window._end_import_split_session()
    window.update()


@pytest.fixture
def sources(tmp_path):
    return {
        "scan10": build_pdf(tmp_path / "scan_10.pdf", 3, "X"),
        "scan2": build_pdf(tmp_path / "scan_2.pdf", 4, "Y"),
        "locked": build_pdf(tmp_path / "locked.pdf", 1, "L", locked=True),
    }


def _open_single(window, dialogs, path: Path, callback=None):
    dialogs.files = (str(path),)
    assert window.open_import_split_wizard(on_split_complete=callback) is True
    return window._import_split_session, window._import_split_view


def test_problem_source_rejects_whole_selection(window, dialogs, sources):
    dialogs.files = (str(sources["scan10"]), str(sources["locked"]), str(sources["scan2"]))

    assert window.open_import_split_wizard() is False

    assert window._import_split_pending is None and window._import_split_session is None
    assert "locked.pdf: passwortgeschützt" in dialogs.errors[-1][1]


def test_order_dialog_natural_order_and_confirm_merges(window, dialogs, sources):
    dialogs.files = (str(sources["scan10"]), str(sources["scan2"]))
    assert window.open_import_split_wizard() is True
    pending = window._import_split_pending
    assert [info.path.name for info in pending.infos] == ["scan_2.pdf", "scan_10.pdf"]

    pending.listbox.selection_clear(0, "end")
    pending.listbox.selection_set(1)
    window._move_import_split_source(-1)
    window._confirm_import_split_order()

    session = window._import_split_session
    assert window._import_split_pending is None
    assert [(s.path.name, s.first_page, s.last_page) for s in session.source_spans] == [
        ("scan_10.pdf", 1, 3),
        ("scan_2.pdf", 4, 7),
    ]
    session.go_to_page(4)
    window._refresh_import_split_view(page_changed=True)
    assert "aus scan_2.pdf, S. 1/4" in window._import_split_view.info_var.get()


@pytest.mark.parametrize("how", ["cancel", "window_close", "external_destroy"])
def test_every_end_of_the_order_dialog_clears_pending(window, dialogs, sources, how):
    dialogs.files = (str(sources["scan10"]), str(sources["scan2"]))
    window.open_import_split_wizard()
    pending = window._import_split_pending

    if how == "cancel":
        window._end_import_split_pending()
    elif how == "window_close":
        pending.popup.tk.eval(pending.popup.protocol("WM_DELETE_WINDOW"))
    else:
        pending.popup.destroy()
    settle(window)

    assert window._import_split_pending is None
    dialogs.files = (str(sources["scan2"]),)
    assert window.open_import_split_wizard() is True


def test_order_dialog_build_failure_clears_pending(window, dialogs, sources, monkeypatch):
    def _broken(_pending):
        raise RuntimeError("kaputt")

    monkeypatch.setattr(window, "_build_import_split_order_popup", _broken)
    dialogs.files = (str(sources["scan10"]), str(sources["scan2"]))

    assert window.open_import_split_wizard() is False
    assert window._import_split_pending is None
    assert "kaputt" in dialogs.errors[-1][1]


def test_second_call_is_rejected_and_keeps_running_session(window, dialogs, sources):
    session, _view = _open_single(window, dialogs, sources["scan2"])

    assert window.open_import_split_wizard(on_split_complete=lambda *args: None) is False

    assert window._import_split_session is session
    assert session.on_split_complete is None
    assert dialogs.infos


def test_external_destroy_ends_session_but_child_destroy_does_not(window, dialogs, sources):
    session, view = _open_single(window, dialogs, sources["scan2"])
    document = session.document

    view.bars[0].destroy()
    settle(window)
    assert window._import_split_session is session

    view.popup.destroy()
    settle(window)
    assert window._import_split_session is None
    assert document.is_closed


def test_programmatic_name_reload_never_writes_into_session(window, dialogs, sources):
    session, view = _open_single(window, dialogs, sources["scan2"])
    view.name_entry.insert(0, "Anna")
    window.update()
    assert session.names == {1: "Anna"}

    session.mark_boundary(3)
    session.go_to_page(3)
    window._refresh_import_split_view(page_changed=True)
    window._step_import_split_page(-1)
    window.update()

    assert session.names == {1: "Anna"}
    assert view.name_var.get() == "Anna"


def test_duplicate_hint_appears_without_changing_bar_height(window, dialogs, sources):
    session, view = _open_single(window, dialogs, sources["scan2"])
    view.name_entry.insert(0, "Anna")
    session.mark_boundary(3)
    session.go_to_page(3)
    window._refresh_import_split_view(page_changed=True)
    settle(window)
    height = view.bars[2].winfo_height()

    view.name_entry.insert(0, "anna")
    settle(window)

    assert "Diesen Namen gibt es schon (Seiten 1-2)" in view.hint_var.get()
    assert view.bars[2].winfo_height() == height


def test_write_error_keeps_wizard_and_state(window, dialogs, sources, monkeypatch, tmp_path):
    session, _view = _open_single(window, dialogs, sources["scan2"])
    _view.name_entry.insert(0, "Anna")
    session.mark_boundary(3)
    before = (set(session.boundaries), dict(session.names))

    def _fail(*args, **kwargs):
        raise SplitWriteError(OSError("disk full"), [])

    monkeypatch.setattr(export_module, "write_split_outputs", _fail)
    dialogs.yesno_answers = [True]
    dialogs.directory = str(tmp_path / "out")

    window._run_import_split()

    assert window._import_split_session is session
    assert (set(session.boundaries), dict(session.names)) == before
    assert "keine Dateien angelegt" in dialogs.errors[-1][1]


def test_fallback_warning_no_jumps_to_unnamed_section(window, dialogs, sources):
    session, view = _open_single(window, dialogs, sources["scan2"])
    view.name_entry.insert(0, "Anna")
    session.mark_boundary(3)
    dialogs.yesno_answers = [False]

    window._run_import_split()

    assert "Seiten 3-4 → Abgabe_02.pdf" in dialogs.questions[-1][1]
    assert session.current_page == 3
    assert window._import_split_session is session


def test_successful_split_merges_duplicates_and_closes_session(window, dialogs, sources, tmp_path):
    session, view = _open_single(window, dialogs, sources["scan2"])
    view.name_entry.insert(0, "Anna Müller")
    for start, name in ((2, "Ben"), (3, "anna  müller")):
        session.mark_boundary(start)
        session.go_to_page(start)
        window._refresh_import_split_view(page_changed=True)
        view.name_entry.insert(0, name)
    window.update()
    document = session.document
    dialogs.directory = str(tmp_path / "out")

    window._run_import_split()

    out = tmp_path / "out"
    assert sorted(path.name for path in out.glob("*.pdf")) == ["Anna_Müller.pdf", "Ben.pdf"]
    assert pdf_texts(out / "Anna_Müller.pdf") == ["Y 1", "Y 3", "Y 4"]
    assert window._import_split_session is None and document.is_closed
    assert "Zusammengeführt" in dialogs.infos[-1][1]


def test_new_exam_flow_rejects_folder_with_pdfs_and_calls_back_once(window, dialogs, sources, tmp_path):
    received: list[tuple[Path, dict[str, str]]] = []
    session, view = _open_single(window, dialogs, sources["scan2"], callback=lambda d, n: received.append((d, n)))
    view.name_entry.insert(0, "Anna Müller")
    window.update()
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "other.PDF").write_bytes(b"x")
    dialogs.directory = str(busy)

    window._run_import_split()
    assert window._import_split_session is session
    assert "bereits PDFs" in dialogs.errors[-1][0]

    dialogs.directory = str(tmp_path / "fresh")
    window._run_import_split()
    assert received == [(tmp_path / "fresh", {"Anna_Müller.pdf": "Anna Müller"})]
    assert window._import_split_session is None


def test_controls_stay_fully_visible_at_every_size(window, dialogs, sources):
    _session, view = _open_single(window, dialogs, sources["scan2"])
    view.name_entry.insert(0, "Ein sehr langer Name, der den Hinweis und die Liste ordentlich fordert")
    view.popup.update_idletasks()
    min_width, min_height = view.popup.minsize()
    renders: list[int] = []
    original_render = view.preview._render
    view.preview._render = lambda width: (renders.append(width), original_render(width))[1]
    controls = [widget for row in view.controls_by_row for widget in row]

    for width in (min_width, 800, 1300):
        for height in (min_height, 750):
            view.popup.geometry(f"{width}x{height}")
            settle(window, 200)
            popup_x, popup_y = view.popup.winfo_rootx(), view.popup.winfo_rooty()
            for widget in controls:
                x, y = widget.winfo_rootx() - popup_x, widget.winfo_rooty() - popup_y
                assert widget.winfo_ismapped()
                assert x >= 0 and y >= 0
                assert x + widget.winfo_width() <= view.popup.winfo_width()
                assert y + widget.winfo_height() <= view.popup.winfo_height()
                assert widget.winfo_width() >= widget.winfo_reqwidth() - 1

    renders.clear()
    view.popup.geometry(f"1300x{min_height}")
    settle(window, 200)
    renders.clear()
    view.popup.geometry("1300x760")
    settle(window, 250)
    assert renders == []


@FOCUS_ONLY
def test_keyboard_contract_with_focus_in_name_field(window, dialogs, sources):
    session, view = _open_single(window, dialogs, sources["scan2"])
    entry = view.name_entry
    view.popup.focus_force()

    def key(sequence, **kwargs):
        entry.focus_force()
        window.update()
        entry.event_generate(sequence, **kwargs)
        settle(window, 40)

    entry.insert(0, "Anna")
    entry.icursor(2)
    key("<Right>")
    assert session.current_page == 2 and entry.get() == "Anna"
    key("<Return>")
    assert session.boundaries == {2} and entry.get() == ""
    entry.insert(0, "Ben")
    key("<Shift-Return>")
    assert session.boundaries == set() and entry.get() == "Anna"
    key("<Return>", state=0x40000)  # keypad Enter on win32 (extended-key bit)
    assert session.boundaries == {2}
    key("<Shift-Return>", state=0x40009)  # Shift + keypad Enter + NumLock
    assert session.boundaries == set()
    key("<Left>")
    key("<Return>")
    assert session.boundaries == set()
    insert_index = entry.index("insert")
    key("<Down>")
    key("<Next>")
    assert entry.get() == "Anna" and entry.index("insert") == insert_index
    assert view.preview.canvas.yview()[0] > 0
    entry.focus_force()
    settle(window, 60)
    assert str(window.focus_get()) == str(entry), "the name field needs the OS keyboard focus - run undisturbed"
    key("<Control-Left>")
    assert session.current_page == 1 and entry.index("insert") < insert_index
    view.boundary_check.invoke()
    settle(window, 100)
    assert str(window.focus_get()) == str(entry)

