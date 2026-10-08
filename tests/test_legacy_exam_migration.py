"""Migration of the old central exam storage (`<index>/<exam_id>.json`) into the exam folders."""

import json
from pathlib import Path

import pytest

from app.infrastructure.repositories import legacy_exam_migration as migration_module
from app.infrastructure.repositories.exam_registry import ExamRegistry
from app.infrastructure.repositories.json_exam_repository import EXAM_DATA_FILENAME, JsonExamRepository


def _raw(exam_id: str, folder: Path, *, name: str = "Mathe", updated_at: str = "2025-01-01T00:00:00.000000Z") -> dict:
    return {
        "exam_id": exam_id,
        "exam_name": name,
        "folder_path": str(folder),
        "created_at": "2025-01-01T00:00:00.000000Z",
        "updated_at": updated_at,
        "standard_page_count": 1,
        "students": [],
        "regions": [],
        "extra_page_assignments": [],
        "person_area_completions": [],
        "task_comments": {},
        "pdf_annotations": [],
        "is_reading_complete": False,
    }


def _legacy(index: Path, raw: dict) -> Path:
    index.mkdir(parents=True, exist_ok=True)
    path = index / f"{raw['exam_id']}.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def test_moves_exam_into_its_folder_registers_it_and_keeps_a_backup(tmp_path: Path) -> None:
    folder = tmp_path / "exam"
    folder.mkdir()
    legacy = _legacy(tmp_path / "index", _raw("exam-1", folder))
    repo = JsonExamRepository(index_root=tmp_path / "index")

    report = repo.migrate_legacy_index()

    assert report.migrated == ["Mathe"]
    assert not legacy.exists() and legacy.with_name("exam-1.json.migriert").exists()
    assert repo.load_exam(folder / EXAM_DATA_FILENAME).exam_name == "Mathe"
    assert repo.exam_file_for_id("exam-1") == (folder / EXAM_DATA_FILENAME).resolve()
    assert "umgezogen" in report.status_text()


def test_second_run_is_a_no_op(tmp_path: Path) -> None:
    folder = tmp_path / "exam"
    folder.mkdir()
    _legacy(tmp_path / "index", _raw("exam-1", folder))
    repo = JsonExamRepository(index_root=tmp_path / "index")
    repo.migrate_legacy_index()
    before = (folder / EXAM_DATA_FILENAME).read_bytes()

    report = repo.migrate_legacy_index()

    assert report.status_text() is None
    assert (folder / EXAM_DATA_FILENAME).read_bytes() == before


def test_newer_legacy_wins_and_older_folder_file_is_backed_up(tmp_path: Path) -> None:
    folder = tmp_path / "exam"
    folder.mkdir()
    (folder / EXAM_DATA_FILENAME).write_text(json.dumps(_raw("exam-1", folder, name="alt")), encoding="utf-8")
    _legacy(tmp_path / "index", _raw("exam-1", folder, name="neu", updated_at="2026-01-01T00:00:00.000000Z"))
    repo = JsonExamRepository(index_root=tmp_path / "index")

    repo.migrate_legacy_index()

    assert repo.load_exam(folder / EXAM_DATA_FILENAME).exam_name == "neu"
    backup = json.loads((folder / f"{EXAM_DATA_FILENAME}.migriert").read_text(encoding="utf-8"))
    assert backup["exam_name"] == "alt"


def test_newer_folder_file_is_kept(tmp_path: Path) -> None:
    folder = tmp_path / "exam"
    folder.mkdir()
    (folder / EXAM_DATA_FILENAME).write_text(
        json.dumps(_raw("exam-1", folder, name="neu", updated_at="2026-01-01T00:00:00.000000Z")), encoding="utf-8"
    )
    _legacy(tmp_path / "index", _raw("exam-1", folder, name="alt"))
    repo = JsonExamRepository(index_root=tmp_path / "index")

    repo.migrate_legacy_index()

    assert repo.load_exam(folder / EXAM_DATA_FILENAME).exam_name == "neu"
    assert not (folder / f"{EXAM_DATA_FILENAME}.migriert").exists()


def test_foreign_exam_in_folder_is_a_conflict_and_nothing_is_touched(tmp_path: Path) -> None:
    folder = tmp_path / "exam"
    folder.mkdir()
    foreign = json.dumps(_raw("other", folder, name="Fremd"))
    (folder / EXAM_DATA_FILENAME).write_text(foreign, encoding="utf-8")
    legacy = _legacy(tmp_path / "index", _raw("exam-1", folder))
    repo = JsonExamRepository(index_root=tmp_path / "index")

    report = repo.migrate_legacy_index()

    assert report.conflicts and legacy.exists()
    assert (folder / EXAM_DATA_FILENAME).read_text(encoding="utf-8") == foreign
    assert repo.list_exam_files() == []


def test_missing_folder_keeps_legacy_file_and_is_reported(tmp_path: Path) -> None:
    legacy = _legacy(tmp_path / "index", _raw("exam-1", tmp_path / "gone"))
    repo = JsonExamRepository(index_root=tmp_path / "index")

    report = repo.migrate_legacy_index()

    assert legacy.exists()
    assert "Ordner nicht gefunden" in report.status_text()


@pytest.mark.parametrize("fail_at", ["register", "rename"])
def test_interrupted_run_completes_on_the_next_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_at) -> None:
    folder = tmp_path / "exam"
    folder.mkdir()
    legacy = _legacy(tmp_path / "index", _raw("exam-1", folder))
    repo = JsonExamRepository(index_root=tmp_path / "index")

    with monkeypatch.context() as patch:
        if fail_at == "register":
            patch.setattr(ExamRegistry, "register", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("crash")))
        else:
            real_replace = Path.replace

            def _crash(self, target):
                if self == legacy:
                    raise OSError("crash")
                return real_replace(self, target)

            patch.setattr(Path, "replace", _crash)
        with pytest.raises(OSError):
            repo.migrate_legacy_index()

    report = repo.migrate_legacy_index()

    assert report.migrated == ["Mathe"]
    assert repo.exam_file_for_id("exam-1") == (folder / EXAM_DATA_FILENAME).resolve()
    assert not legacy.exists() and legacy.with_name("exam-1.json.migriert").exists()
    assert not (folder / f"{EXAM_DATA_FILENAME}.migriert").exists()


def test_interrupted_while_writing_folder_file_leaves_legacy_untouched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "exam"
    folder.mkdir()
    legacy = _legacy(tmp_path / "index", _raw("exam-1", folder))
    repo = JsonExamRepository(index_root=tmp_path / "index")

    with monkeypatch.context() as patch:
        patch.setattr(migration_module, "atomic_write_json", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("crash")))
        with pytest.raises(OSError):
            repo.migrate_legacy_index()
    assert legacy.exists() and not (folder / EXAM_DATA_FILENAME).exists()

    repo.migrate_legacy_index()

    assert (folder / EXAM_DATA_FILENAME).exists() and not legacy.exists()


def test_corrupt_registry_is_set_aside_and_reported(tmp_path: Path) -> None:
    index = tmp_path / "index"
    index.mkdir()
    (index / "known_exams.json").write_text("{kaputt", encoding="utf-8")
    repo = JsonExamRepository(index_root=index)

    assert repo.list_exam_files() == []
    assert (index / "known_exams.json.defekt").exists()
    assert "beschädigt" in repo.registry.corruption_notice
