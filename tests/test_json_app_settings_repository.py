from pathlib import Path

from app.infrastructure.repositories.json_app_settings_repository import JsonAppSettingsRepository


def test_load_uses_default_exam_index_dir_when_no_settings_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    base_dir = tmp_path / "repo"
    base_dir.mkdir(parents=True)
    default_index = base_dir / ".korrektor_index"

    repository = JsonAppSettingsRepository(
        app_name="korrektor-test",
        base_dir=base_dir,
        default_exam_index_dir=default_index,
    )

    settings = repository.load()

    assert settings.exam_index_dir == default_index.resolve()
    assert settings.exam_index_dir.exists()


def test_save_and_reload_custom_exam_index_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    base_dir = tmp_path / "repo"
    base_dir.mkdir(parents=True)
    default_index = base_dir / ".korrektor_index"
    custom_index = tmp_path / "custom-index"

    repository = JsonAppSettingsRepository(
        app_name="korrektor-test",
        base_dir=base_dir,
        default_exam_index_dir=default_index,
    )

    repository.save_exam_index_dir(custom_index)
    settings = repository.load()

    assert settings.exam_index_dir == custom_index.resolve()
    assert settings.exam_index_dir.exists()
