from pathlib import Path

from app.infrastructure.repositories.json_app_settings_repository import AppRuntimeSettings, JsonAppSettingsRepository


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
    assert settings.default_annotation_color == "#d62828"
    assert settings.default_annotation_pdf_font_size == 14.0


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
    assert settings.default_annotation_color == "#d62828"
    assert settings.default_annotation_pdf_font_size == 14.0


def test_save_exam_index_dir_keeps_annotation_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    base_dir = tmp_path / "repo"
    base_dir.mkdir(parents=True)
    default_index = base_dir / ".korrektor_index"
    first_index = tmp_path / "index-a"
    second_index = tmp_path / "index-b"

    repository = JsonAppSettingsRepository(
        app_name="korrektor-test",
        base_dir=base_dir,
        default_exam_index_dir=default_index,
    )

    repository.save(
        AppRuntimeSettings(
            exam_index_dir=first_index,
            default_annotation_color="#ff4fa3",
            default_annotation_pdf_font_size=22.0,
        )
    )

    repository.save_exam_index_dir(second_index)
    settings = repository.load()

    assert settings.exam_index_dir == second_index.resolve()
    assert settings.default_annotation_color == "#ff4fa3"
    assert settings.default_annotation_pdf_font_size == 22.0
