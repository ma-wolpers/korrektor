from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.core.domain.models import ExamProject, StudentExam, utc_now_iso
from app.core.ports.repositories import ExamRepository, PdfScanRepository
from app.infrastructure.repositories.file_utils import slugify


@dataclass(slots=True)
class CreateExamResult:
    exam: ExamProject
    exam_file: Path


class CreateExamUseCase:
    def __init__(self, exam_repo: ExamRepository, pdf_scan_repo: PdfScanRepository) -> None:
        self._exam_repo = exam_repo
        self._pdf_scan_repo = pdf_scan_repo

    def execute(self, *, folder_path: Path, exam_name: str | None = None) -> CreateExamResult:
        scan_entries = self._pdf_scan_repo.scan_exam_folder(folder_path)
        if not scan_entries:
            raise ValueError("Im gewaehlten Ordner wurden keine PDFs gefunden.")

        standard_page_count = min(page_count for _, page_count in scan_entries)
        created = utc_now_iso()

        students: list[StudentExam] = []
        for pdf_filename, page_count in scan_entries:
            display_name = Path(pdf_filename).stem
            student_id = slugify(display_name)
            extras = [page for page in range(standard_page_count + 1, page_count + 1)]
            students.append(
                StudentExam(
                    student_id=student_id,
                    display_name=display_name,
                    pdf_filename=pdf_filename,
                    page_count=page_count,
                    extra_pages=extras,
                )
            )

        effective_name = exam_name.strip() if exam_name else folder_path.name
        exam = ExamProject(
            exam_id=f"{slugify(effective_name)}-{uuid4().hex[:8]}",
            exam_name=effective_name,
            folder_path=str(folder_path),
            created_at=created,
            updated_at=created,
            standard_page_count=standard_page_count,
            students=students,
            regions=[],
            is_reading_complete=False,
        )
        exam_file = self._exam_repo.save_exam(exam)
        return CreateExamResult(exam=exam, exam_file=exam_file)
