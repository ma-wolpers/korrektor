import json
from pathlib import Path

import pytest

from app.adapters.bootstrap.wiring import build_gui_dependencies
from app.adapters.gui import ui_intent_controller as uic_module
from app.adapters.gui.ui_intent_controller import UiIntentController
from app.core.domain.grading_scale import SCALE_TYPE_SCHOOL_1_6, GradeThreshold, GradingScale


@pytest.fixture(autouse=True)
def _no_real_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent showerror/showinfo/showinfo from opening a real (blocking) Tk dialog."""
    monkeypatch.setattr(uic_module.messagebox, "showerror", lambda *args, **kwargs: None)
    monkeypatch.setattr(uic_module.messagebox, "showinfo", lambda *args, **kwargs: None)


class _FakeApp:
    def __init__(self) -> None:
        self.status_messages: list[str] = []

    def set_status(self, text: str) -> None:
        self.status_messages.append(text)


def _controller(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> UiIntentController:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    deps = build_gui_dependencies(tmp_path / "repo")
    return UiIntentController(app=_FakeApp(), deps=deps)


def _scale(name: str = "Mathe 8") -> GradingScale:
    return GradingScale(
        scale_id="",
        name=name,
        subject="Mathe",
        year="8",
        school="Musterschule",
        scale_type=SCALE_TYPE_SCHOOL_1_6,
        thresholds=[GradeThreshold(min_percent=80.0, grade_label="1")],
    )


def test_export_then_import_on_a_second_installation_recreates_the_scale(tmp_path: Path, monkeypatch) -> None:
    """Simulates the actual use case: export on "computer A", import into a separate, empty store."""
    controller_a = _controller(tmp_path / "pc-a", monkeypatch)
    saved = controller_a.save_grading_scale_immediate(scale=_scale())

    export_file = tmp_path / "export.json"
    monkeypatch.setattr(uic_module.filedialog, "asksaveasfilename", lambda **kwargs: str(export_file))
    assert controller_a.export_grading_scales_to_file() is True
    assert export_file.exists()

    controller_b = _controller(tmp_path / "pc-b", monkeypatch)
    assert controller_b.list_grading_scales() == []
    monkeypatch.setattr(uic_module.filedialog, "askopenfilename", lambda **kwargs: str(export_file))
    summary = controller_b.import_grading_scales_from_file()

    assert summary is not None
    assert summary.added == [saved.name]
    imported = controller_b.list_grading_scales()
    assert len(imported) == 1
    assert imported[0].scale_id == saved.scale_id
    assert imported[0].thresholds[0].grade_label == "1"


def test_import_skips_a_scale_that_is_already_present_and_identical(tmp_path: Path, monkeypatch) -> None:
    controller = _controller(tmp_path / "pc", monkeypatch)
    saved = controller.save_grading_scale_immediate(scale=_scale())

    export_file = tmp_path / "export.json"
    monkeypatch.setattr(uic_module.filedialog, "asksaveasfilename", lambda **kwargs: str(export_file))
    controller.export_grading_scales_to_file()

    monkeypatch.setattr(uic_module.filedialog, "askopenfilename", lambda **kwargs: str(export_file))
    summary = controller.import_grading_scales_from_file()

    assert summary is not None
    assert summary.added == []
    assert summary.skipped_identical == [saved.name]
    assert summary.skipped_conflict == []
    assert len(controller.list_grading_scales()) == 1


def test_import_reports_a_conflict_instead_of_overwriting_a_local_edit(tmp_path: Path, monkeypatch) -> None:
    controller_a = _controller(tmp_path / "pc-a", monkeypatch)
    saved = controller_a.save_grading_scale_immediate(scale=_scale())
    export_file = tmp_path / "export.json"
    monkeypatch.setattr(uic_module.filedialog, "asksaveasfilename", lambda **kwargs: str(export_file))
    controller_a.export_grading_scales_to_file()

    controller_b = _controller(tmp_path / "pc-b", monkeypatch)
    local_edit = GradingScale(
        scale_id=saved.scale_id,
        name="Mathe 8 (lokal angepasst)",
        subject="Mathe",
        year="8",
        school="Musterschule",
        scale_type=SCALE_TYPE_SCHOOL_1_6,
        thresholds=[GradeThreshold(min_percent=90.0, grade_label="1")],
    )
    controller_b._deps.grading_scale_repository.save_scale(local_edit)

    monkeypatch.setattr(uic_module.filedialog, "askopenfilename", lambda **kwargs: str(export_file))
    summary = controller_b.import_grading_scales_from_file()

    assert summary is not None
    assert summary.added == []
    assert summary.skipped_conflict == [saved.name]
    # the local edit must survive untouched
    still_local = controller_b._deps.grading_scale_repository.get_scale(saved.scale_id)
    assert still_local is not None
    assert still_local.name == "Mathe 8 (lokal angepasst)"


def test_import_rejects_a_file_that_is_not_a_grading_scale_export(tmp_path: Path, monkeypatch) -> None:
    controller = _controller(tmp_path / "pc", monkeypatch)
    not_an_export = tmp_path / "not_an_export.json"
    not_an_export.write_text(json.dumps({"something_else": True}), encoding="utf-8")

    monkeypatch.setattr(uic_module.filedialog, "askopenfilename", lambda **kwargs: str(not_an_export))
    summary = controller.import_grading_scales_from_file()

    assert summary is None
    assert controller.list_grading_scales() == []
