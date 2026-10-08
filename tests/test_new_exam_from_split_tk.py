"""End-to-end "Neue Klausur" -> "Große PDF(s) aufteilen" through the real window (synthetic data only)."""

from __future__ import annotations

from tk_test_support import build_pdf, settle

from app.adapters.gui import dialog_services
from app.adapters.gui import ui_intent_controller_overview as overview_module


def test_new_exam_from_split_creates_exam_with_typed_names_and_opens_it(korrektor_window, tmp_path, monkeypatch):
    window = korrektor_window
    source = build_pdf(tmp_path / "sammel.pdf", 4, "S")
    answers = {"strings": ["Mathe 10a", "10a", "Mathe"]}
    monkeypatch.setattr(overview_module.choicedialog, "askchoice", lambda *args, **kwargs: "split")
    monkeypatch.setattr(dialog_services.filedialog, "askopenfilenames", lambda **kwargs: (str(source),))
    monkeypatch.setattr(dialog_services.filedialog, "askdirectory", lambda **kwargs: str(tmp_path / "abgaben"))
    monkeypatch.setattr(overview_module.simpledialog, "askstring", lambda *args, **kwargs: answers["strings"].pop(0))
    monkeypatch.setattr(dialog_services.messagebox, "showinfo", lambda *args, **kwargs: None)
    monkeypatch.setattr(dialog_services.messagebox, "showerror", lambda t, m, **kw: (_ for _ in ()).throw(AssertionError(m)))
    try:
        window._controller.create_exam()
        session = window._import_split_session
        view = window._import_split_view
        assert session is not None and session.creates_exam
        assert view.popup.title() == "Neue Klausur: PDF aufteilen"
        view.name_entry.insert(0, "Anna Müller")
        session.mark_boundary(3)
        session.go_to_page(3)
        window._refresh_import_split_view(page_changed=True)
        view.name_entry.insert(0, "Ben")
        settle(window)
        document = session.document

        window._run_import_split()
        settle(window)

        assert window._import_split_session is None and document.is_closed
        exam = window._current_exam
        assert exam is not None and exam.exam_name == "Mathe 10a"
        assert sorted(student.display_name for student in exam.students) == ["Anna Müller", "Ben"]
        assert sorted(student.pdf_filename for student in exam.students) == ["Anna_Müller.pdf", "Ben.pdf"]
        assert window._reading_active is True
    finally:
        window._end_import_split_session()
        window._return_to_overview()
        window.update()
