from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

from app.core.domain.models import ExamProject
from app.infrastructure.repositories.file_utils import slugify

AdoptionSituation = Literal["new", "same", "moved", "copy"]


@dataclass(frozen=True)
class AdoptionAnalysis:
    """What "Neue Klausur" found in a folder that already holds ``korrektor_klausur.json``.

    ``situation`` (binding policy - the registry never makes the GUI open a
    different exam than the chosen folder's):

    - ``"new"``: ``exam_id`` unknown to the Klausurliste -> adopt after a question.
    - ``"same"``: ``exam_id`` registered for exactly this folder -> just open.
    - ``"moved"``: registered for another folder that no longer exists or no
      longer contains this ``exam_id`` -> offer to switch the entry to this folder.
    - ``"copy"``: registered for another folder that still contains this
      ``exam_id`` (a copy of the exam) -> choose: own exam with a new id,
      switch the registration, or cancel.
    """

    exam_file: Path
    exam_id: str
    exam_name: str
    updated_at: str
    situation: AdoptionSituation
    registered_folder: Path | None


class AdoptExamUseCase:
    """Take over an exam whose data already lives in a folder (portability between PCs)."""

    def __init__(self, exam_repo) -> None:
        """``exam_repo`` is the `JsonExamRepository` (needs registry access besides the port)."""
        self._exam_repo = exam_repo

    def analyze(self, folder: Path) -> AdoptionAnalysis | None:
        """Classify ``folder``; ``None`` if it holds no (readable) exam data file."""
        exam_file = self._exam_repo.exam_file_for_folder(folder)
        if not exam_file.exists():
            return None
        header = self._exam_repo.read_exam_header(exam_file)
        if not header or not header.get("exam_id"):
            return None
        exam_id = header["exam_id"]
        registered = self._exam_repo.registry.folder_for(exam_id)
        if registered is None:
            situation: AdoptionSituation = "new"
        elif registered == exam_file.parent:
            situation = "same"
        else:
            other_file = self._exam_repo.exam_file_for_folder(registered)
            other_header = self._exam_repo.read_exam_header(other_file) if other_file.exists() else None
            situation = "copy" if (other_header or {}).get("exam_id") == exam_id else "moved"
        return AdoptionAnalysis(
            exam_file=exam_file,
            exam_id=exam_id,
            exam_name=header.get("exam_name") or exam_id,
            updated_at=header.get("updated_at", ""),
            situation=situation,
            registered_folder=registered,
        )

    def adopt(self, analysis: AdoptionAnalysis, *, as_new_exam: bool = False) -> ExamProject:
        """Register the folder (replacing a stale/other registration) and return the loaded exam.

        ``as_new_exam`` (only meaningful for ``"copy"``) gives the folder's exam
        a fresh ``exam_id`` first, so both copies can coexist in the overview.
        """
        exam = self._exam_repo.load_exam(analysis.exam_file)
        if as_new_exam:
            exam.exam_id = f"{slugify(exam.exam_name)}-{uuid4().hex[:8]}"
            self._exam_repo.save_exam(exam)
        else:
            self._exam_repo.registry.register(exam.exam_id, analysis.exam_file.parent)
        return exam
