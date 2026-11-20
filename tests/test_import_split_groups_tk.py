"""Real-Tk tests of the Klausur-Zuordnung in the PDF import wizard (keys, bar, folders per Klausur).

Same setup as `test_import_split_wizard_tk` (shared fixtures in
`import_split_tk_support`); the name prompt is stubbed. The keyboard test is
opt-in via ``TK_FOCUS_TESTS=1``.
"""

from __future__ import annotations

from import_split_tk_support import dialogs, open_single, sources, window  # noqa: F401 - fixtures
from tk_test_support import FOCUS_ONLY, pdf_texts, settle

from app.adapters.gui import dialog_services
from app.adapters.gui.import_split_session import SplitExamFolder


def _stub_name_prompt(monkeypatch, answers: list[str | None]) -> list[tuple[str, object]]:
    """Replace the shared text prompt; return the recorded ``(title, validate)`` calls."""
    seen: list[tuple[str, object]] = []

    def _ask(title, prompt, *, validate=None, **kwargs):
        seen.append((title, validate))
        return answers.pop(0)

    monkeypatch.setattr(dialog_services.simpledialog, "askstring", _ask)
    return seen


def test_klausur_switch_applies_from_here_and_split_writes_one_folder_per_klausur(
    window, dialogs, sources, tmp_path, monkeypatch
):
    seen = _stub_name_prompt(monkeypatch, ["Bio 10b"])
    session, view = open_single(window, dialogs, sources["scan2"])
    view.name_entry.insert(0, "Anna")
    for start, name in ((2, "Ben"), (3, "Anna")):
        session.mark_boundary(start)
        session.go_to_page(start)
        window._refresh_import_split_view(page_changed=True)
        view.name_entry.insert(0, name)
    session.go_to_page(2)
    window._refresh_import_split_view(page_changed=True)

    window._choose_import_split_group(1)  # Ctrl+2: next free number asks for the name
    window.update()

    assert [title for title, _validate in seen] == ["Neue Klausur im Import"]
    assert seen[0][1]("klausur 1") is not None and seen[0][1]("Chemie") is None
    assert session.group_names == ["Klausur 1", "Bio 10b"]
    assert [session.group_index_for_page(page) for page in (1, 2, 3)] == [0, 1, 1]
    assert view.group_bar.current_var.get() == "2 · Bio 10b"
    assert view.group_bar.overview_var.get() == "1 Klausur 1 (1) · 2 Bio 10b (2)"
    assert [view.section_tree.set(iid, "group") for iid in view.section_tree.get_children()] == ["1", "2", "2"]
    assert "2 Klausuren" in view.count_var.get()
    session.go_to_page(3)
    window._refresh_import_split_view(page_changed=True)
    assert view.hint_var.get().strip() == ""  # "Anna" in another Klausur is no duplicate

    window._step_import_split_group(-1)  # Ctrl+Up on page 3: from here on Klausur 1 again
    assert [session.group_index_for_page(page) for page in (1, 2, 3)] == [0, 1, 0]
    window._step_import_split_group(1)  # Ctrl+Down: existing Klausur 2, no prompt
    assert len(seen) == 1 and session.group_index_for_page(3) == 1
    window._choose_import_split_group(5)  # Ctrl+6 does not exist yet: hint only
    assert "gibt es noch nicht" in view.info_var.get() and len(seen) == 1

    dialogs.directory = str(tmp_path / "out")
    window._run_import_split()

    out = tmp_path / "out"
    assert sorted(path.name for path in out.iterdir()) == ["Bio 10b", "Klausur 1"]
    assert pdf_texts(out / "Klausur 1" / "Anna.pdf") == ["Y 1"]
    assert sorted(path.name for path in (out / "Bio 10b").glob("*.pdf")) == ["Anna.pdf", "Ben.pdf"]
    assert pdf_texts(out / "Bio 10b" / "Anna.pdf") == ["Y 3", "Y 4"]
    assert "Je Klausur ein Ordner" in dialogs.infos[-1][1]


def test_rename_and_cancelled_prompts_change_nothing_else(window, dialogs, sources, monkeypatch):
    seen = _stub_name_prompt(monkeypatch, [None, "Chemie 9", None])
    session, _view = open_single(window, dialogs, sources["scan2"])

    window._step_import_split_group(1)  # past the last Klausur -> prompt, cancelled
    assert session.group_names == ["Klausur 1"] and session.group_switches == {}
    window._rename_import_split_group()  # F2
    assert session.group_names == ["Chemie 9"]
    assert seen[1][1]("Chemie 9") is None  # its own name is no duplicate
    window._rename_import_split_group()  # cancelled
    assert session.group_names == ["Chemie 9"]
    window._step_import_split_group(-1)
    assert "bereits Klausur 1" in window._import_split_view.info_var.get()


def test_new_exam_flow_rejects_klausur_subfolder_with_pdfs(window, dialogs, sources, tmp_path, monkeypatch):
    _stub_name_prompt(monkeypatch, ["10b"])
    received: list[list[SplitExamFolder]] = []
    session, view = open_single(window, dialogs, sources["scan2"], callback=lambda folders: received.append(list(folders)))
    view.name_entry.insert(0, "Anna")
    session.mark_boundary(3)
    session.go_to_page(3)
    window._refresh_import_split_view(page_changed=True)
    view.name_entry.insert(0, "Ben")
    window._choose_import_split_group(1)
    target = tmp_path / "target"
    (target / "10b").mkdir(parents=True)
    (target / "10b" / "alt.pdf").write_bytes(b"x")
    (target / "unrelated.pdf").write_bytes(b"x")  # the parent may contain anything
    dialogs.directory = str(target)

    window._run_import_split()
    assert window._import_split_session is session
    assert "„10b“" in dialogs.errors[-1][1]

    (target / "10b" / "alt.pdf").unlink()
    window._run_import_split()
    assert received == [
        [SplitExamFolder(target / "Klausur 1", {"Anna.pdf": "Anna"}), SplitExamFolder(target / "10b", {"Ben.pdf": "Ben"})]
    ]


@FOCUS_ONLY
def test_klausur_keys_with_focus_in_name_field(window, dialogs, sources, monkeypatch):
    _stub_name_prompt(monkeypatch, ["10b", "10a"])
    session, view = open_single(window, dialogs, sources["scan2"])
    entry = view.name_entry
    session.mark_boundary(3)

    def key(sequence):
        entry.focus_force()
        window.update()
        entry.event_generate(sequence)
        settle(window, 40)

    entry.insert(0, "Anna")
    key("<Control-Key-2>")
    assert session.group_names == ["Klausur 1", "10b"] and session.group_index_for_page(4) == 1
    key("<Control-Up>")
    assert session.group_index_for_page(1) == 0 and entry.get() == "Anna"
    key("<Control-Down>")
    assert session.group_index_for_page(1) == 1
    key("<F2>")
    assert session.group_names == ["Klausur 1", "10a"]
