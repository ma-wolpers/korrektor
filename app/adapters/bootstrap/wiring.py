from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.app_info import APP_INFO, AppInfo
from bw_libs.app_shell import AppShellConfig
from app.core.domain.progress import ProgressCalculator
from app.core.usecases.create_exam_usecase import CreateExamUseCase
from app.core.usecases.list_exams_usecase import ListExamsUseCase
from app.core.usecases.load_exam_usecase import LoadExamUseCase
from app.core.usecases.save_score_usecase import SaveScoreUseCase
from app.core.usecases.set_reading_complete_usecase import SetReadingCompleteUseCase
from app.core.usecases.upsert_region_usecase import UpsertRegionUseCase
from app.infrastructure.repositories.csv_score_repository import CsvScoreRepository
from app.infrastructure.repositories.in_memory_region_repository import InMemoryRegionRepository
from app.infrastructure.repositories.json_exam_repository import JsonExamRepository
from app.infrastructure.repositories.pymupdf_scan_repository import PyMuPdfScanRepository


@dataclass(frozen=True)
class GuiDependencies:
    list_exams_usecase: ListExamsUseCase
    create_exam_usecase: CreateExamUseCase
    load_exam_usecase: LoadExamUseCase
    upsert_region_usecase: UpsertRegionUseCase
    save_score_usecase: SaveScoreUseCase
    set_reading_complete_usecase: SetReadingCompleteUseCase
    exam_repository: JsonExamRepository
    app_info: AppInfo
    shell_config: AppShellConfig


AppDependencies = GuiDependencies


def build_gui_dependencies(base_dir: Path) -> GuiDependencies:
    index_root = base_dir / ".korrektor_index"

    exam_repo = JsonExamRepository(index_root=index_root)
    score_repo = CsvScoreRepository()
    scan_repo = PyMuPdfScanRepository()
    region_repo = InMemoryRegionRepository()

    progress = ProgressCalculator()

    return GuiDependencies(
        list_exams_usecase=ListExamsUseCase(exam_repo=exam_repo, progress_calculator=progress),
        create_exam_usecase=CreateExamUseCase(exam_repo=exam_repo, pdf_scan_repo=scan_repo),
        load_exam_usecase=LoadExamUseCase(exam_repo=exam_repo),
        upsert_region_usecase=UpsertRegionUseCase(exam_repo=exam_repo, region_repo=region_repo),
        save_score_usecase=SaveScoreUseCase(score_repo=score_repo),
        set_reading_complete_usecase=SetReadingCompleteUseCase(exam_repo=exam_repo),
        exam_repository=exam_repo,
        app_info=APP_INFO,
        shell_config=AppShellConfig(
            title=APP_INFO.window_title,
            geometry="1180x740",
            min_width=980,
            min_height=640,
        ),
    )
