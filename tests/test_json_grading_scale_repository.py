from pathlib import Path

from app.core.domain.grading_scale import (
    SCALE_TYPE_SCHOOL_1_6,
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    GradeThreshold,
    GradingScale,
    GradingScaleUsageEntry,
)
from app.infrastructure.repositories.json_grading_scale_repository import JsonGradingScaleRepository


def _repo(tmp_path: Path, monkeypatch) -> JsonGradingScaleRepository:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    base_dir = tmp_path / "repo"
    base_dir.mkdir(parents=True)
    return JsonGradingScaleRepository(app_name="korrektor-test", base_dir=base_dir)


def _scale(scale_id: str = "scale-1") -> GradingScale:
    return GradingScale(
        scale_id=scale_id,
        name="Mathe 8",
        subject="Mathe",
        year="8",
        school="Musterschule",
        scale_type=SCALE_TYPE_SCHOOL_1_6,
        thresholds=[GradeThreshold(min_percent=80.0, grade_label="1")],
    )


def test_list_scales_empty_when_no_file_exists(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path, monkeypatch)
    assert repo.list_scales() == []


def test_save_scale_then_list_and_get(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path, monkeypatch)
    repo.save_scale(_scale())

    scales = repo.list_scales()
    assert len(scales) == 1
    assert scales[0].scale_id == "scale-1"
    assert repo.get_scale("scale-1") is not None
    assert repo.get_scale("missing") is None


def test_save_scale_updates_existing_entry_by_scale_id_instead_of_duplicating(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path, monkeypatch)
    repo.save_scale(_scale())
    updated = _scale()
    updated.name = "Mathe 8 (ueberarbeitet)"
    repo.save_scale(updated)

    scales = repo.list_scales()
    assert len(scales) == 1
    assert scales[0].name == "Mathe 8 (ueberarbeitet)"


def test_delete_scale_removes_it(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path, monkeypatch)
    repo.save_scale(_scale())
    repo.delete_scale("scale-1")
    assert repo.list_scales() == []


def test_record_and_list_usage(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path, monkeypatch)
    entry = GradingScaleUsageEntry(
        source_scale_id="scale-1",
        exam_id="exam-1",
        exam_name="Mathe Klausur 1",
        exam_folder_path="/exams/mathe-1",
        assigned_at="2026-09-19T10:00:00.000000Z",
    )
    repo.record_usage(entry)

    assert repo.has_usage("scale-1") is True
    assert repo.has_usage("scale-2") is False
    usage = repo.list_usage("scale-1")
    assert len(usage) == 1
    assert usage[0].exam_name == "Mathe Klausur 1"


def test_usage_survives_scale_deletion_as_historical_record(tmp_path: Path, monkeypatch) -> None:
    """The usage log is a separate, append-only record - deleting the template doesn't touch it."""
    repo = _repo(tmp_path, monkeypatch)
    repo.save_scale(_scale())
    repo.record_usage(
        GradingScaleUsageEntry(
            source_scale_id="scale-1",
            exam_id="exam-1",
            exam_name="Mathe Klausur 1",
            exam_folder_path="/exams/mathe-1",
            assigned_at="2026-09-19T10:00:00.000000Z",
        )
    )

    repo.delete_scale("scale-1")

    assert repo.list_scales() == []
    assert repo.has_usage("scale-1") is True


def test_scale_status_active_by_default_and_persists_archived(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path, monkeypatch)
    scale = _scale()
    assert scale.status == STATUS_ACTIVE
    repo.save_scale(scale)

    scale.status = STATUS_ARCHIVED
    repo.save_scale(scale)

    assert repo.get_scale("scale-1").status == STATUS_ARCHIVED
