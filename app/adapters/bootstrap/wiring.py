from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.app_info import APP_INFO, AppInfo
from bw_libs.app_shell import AppShellConfig
from app.adapters.undo import UndoHistory
from app.core.domain.progress import ProgressCalculator
from app.core.usecases.create_exam_usecase import CreateExamUseCase
from app.core.usecases.delete_exam_usecase import DeleteExamUseCase
from app.core.usecases.export_scores_usecase import ExportScoresUseCase
from app.core.usecases.list_exams_usecase import ListExamsUseCase
from app.core.usecases.load_exam_usecase import LoadExamUseCase
from app.core.usecases.save_score_usecase import SaveScoreUseCase
from app.core.usecases.set_reading_complete_usecase import SetReadingCompleteUseCase
from app.core.usecases.upsert_region_usecase import UpsertRegionUseCase
from app.infrastructure.repositories.csv_score_export_repository import CsvScoreExportRepository
from app.infrastructure.repositories.csv_score_repository import CsvScoreRepository
from app.infrastructure.repositories.in_memory_region_repository import InMemoryRegionRepository
from app.infrastructure.repositories.json_app_settings_repository import AppRuntimeSettings, JsonAppSettingsRepository
from app.infrastructure.repositories.json_exam_repository import JsonExamRepository
from app.infrastructure.repositories.pymupdf_scan_repository import PyMuPdfScanRepository


@dataclass(frozen=True)
class GuiDependencies:
    list_exams_usecase: ListExamsUseCase
    create_exam_usecase: CreateExamUseCase
    delete_exam_usecase: DeleteExamUseCase
    load_exam_usecase: LoadExamUseCase
    upsert_region_usecase: UpsertRegionUseCase
    save_score_usecase: SaveScoreUseCase
    export_scores_usecase: ExportScoresUseCase
    set_reading_complete_usecase: SetReadingCompleteUseCase
    exam_repository: JsonExamRepository
    settings_repository: JsonAppSettingsRepository
    runtime_settings: AppRuntimeSettings
    undo_history: UndoHistory
    app_info: AppInfo
    shell_config: AppShellConfig


AppDependencies = GuiDependencies


def build_gui_dependencies(base_dir: Path) -> GuiDependencies:
    default_index_root = (base_dir / ".korrektor_index").resolve()
    settings_repository = JsonAppSettingsRepository(
        app_name=APP_INFO.appdata_folder,
        base_dir=base_dir,
        default_exam_index_dir=default_index_root,
    )
    runtime_settings = settings_repository.load()
    undo_history = UndoHistory()

    exam_repo = JsonExamRepository(index_root=runtime_settings.exam_index_dir)
    score_repo = CsvScoreRepository()
    export_repo = CsvScoreExportRepository()
    scan_repo = PyMuPdfScanRepository()
    region_repo = InMemoryRegionRepository()

    progress = ProgressCalculator()

    return GuiDependencies(
        list_exams_usecase=ListExamsUseCase(exam_repo=exam_repo, progress_calculator=progress),
        create_exam_usecase=CreateExamUseCase(exam_repo=exam_repo, pdf_scan_repo=scan_repo),
        delete_exam_usecase=DeleteExamUseCase(exam_repo=exam_repo),
        load_exam_usecase=LoadExamUseCase(exam_repo=exam_repo),
        upsert_region_usecase=UpsertRegionUseCase(exam_repo=exam_repo, region_repo=region_repo),
        save_score_usecase=SaveScoreUseCase(score_repo=score_repo),
        export_scores_usecase=ExportScoresUseCase(export_repo=export_repo),
        set_reading_complete_usecase=SetReadingCompleteUseCase(exam_repo=exam_repo),
        exam_repository=exam_repo,
        settings_repository=settings_repository,
        runtime_settings=runtime_settings,
        undo_history=undo_history,
        app_info=APP_INFO,
        shell_config=AppShellConfig(
            title=APP_INFO.window_title,
            geometry="1180x740",
            min_width=980,
            min_height=640,
        ),
    )
