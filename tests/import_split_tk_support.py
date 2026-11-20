"""Shared fixtures of the real-Tk PDF import wizard tests (synthetic PDFs, recorded dialogs).

Imported by name into the test modules (pytest picks fixtures up from the
module namespace): ``window``, ``dialogs``, ``sources`` plus `open_single`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tk_test_support import build_pdf

from app.adapters.gui import dialog_services


class DialogRecorder:
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
    recorder = DialogRecorder()
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


def open_single(window, dialogs, path: Path, callback=None):
    dialogs.files = (str(path),)
    assert window.open_import_split_wizard(on_split_complete=callback) is True
    return window._import_split_session, window._import_split_view
