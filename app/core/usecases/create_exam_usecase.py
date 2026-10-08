from __future__ import annotations

from collections.abc import Mapping
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

    def execute(
        self,
        *,
        folder_path: Path,
        exam_name: str | None = None,
        school_class: str = "",
        subject: str = "",
        display_name_by_filename: Mapping[str, str] | None = None,
    ) -> CreateExamResult:
        """Create and save a new exam from a folder with one PDF per student.

        Args:
            folder_path: Exam folder; every ``*.pdf`` in it becomes one student.
            exam_name: Name of the exam (default: the folder name).
            school_class: Optional class, only used by export filename templates.
            subject: Optional subject, only used by export filename templates.
            display_name_by_filename: Optional ``{pdf_filename: display_name}``
                from the PDF import wizard, so a student shows exactly the
                name typed there ("Anna Müller") although the file follows
                the Namenmodus convention (``Anna_Müller.pdf``). Files without
                an entry keep the previous rule: display name = file stem.
                ``student_id`` is always derived from the file stem, so the
                folder flow behaves exactly as before.

        Raises:
            ValueError: The folder is already indexed by another exam, or it
                contains no PDF.
        """
        resolved_folder = folder_path.resolve()
        existing_name = self._find_exam_name_for_folder(resolved_folder)
        if existing_name is not None:
            raise ValueError(
                f"Fuer diesen Ordner existiert im aktuellen Exam-Indexordner bereits die Klausur "
                f"'{existing_name}'. Bitte diese ueber die Klausur-Uebersicht oeffnen, statt eine "
                "neue, leere Klausur anzulegen - sonst gehen bereits erfasste Bereiche/Punkte/Namen "
                "fuer diesen Ordner scheinbar verloren (sie bleiben in der alten Klausur erhalten, "
                "tauchen aber in der neuen nicht auf)."
            )
        scan_entries = self._pdf_scan_repo.scan_exam_folder(folder_path)
        if not scan_entries:
            raise ValueError("Im gewaehlten Ordner wurden keine PDFs gefunden.")

        standard_page_count = min(page_count for _, page_count in scan_entries)
        created = utc_now_iso()

        students: list[StudentExam] = []
        display_names = display_name_by_filename or {}
        for pdf_filename, page_count in scan_entries:
            stem = Path(pdf_filename).stem
            display_name = display_names.get(pdf_filename, "").strip() or stem
            student_id = slugify(stem)
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
            extra_page_assignments=[],
            person_area_completions=[],
            is_reading_complete=False,
            school_class=school_class.strip(),
            subject=subject.strip(),
        )
        exam_file = self._exam_repo.save_exam(exam)
        return CreateExamResult(exam=exam, exam_file=exam_file)

    def _find_exam_name_for_folder(self, resolved_folder: Path) -> str | None:
        """Return the name of an already-indexed exam pointing at `resolved_folder`, if any.

        A file that fails to load (broken/legacy JSON) is skipped rather
        than aborting exam creation over an unrelated exam's problem - the
        same "skip broken, don't block" choice `ListExamsUseCase` makes.
        """
        for exam_file in self._exam_repo.list_exam_files():
            try:
                candidate = self._exam_repo.load_exam(exam_file)
            except Exception:
                continue
            if Path(candidate.folder_path).resolve() == resolved_folder:
                return candidate.exam_name
        return None
