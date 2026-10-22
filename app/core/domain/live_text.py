"""Current text of a Punkte-/Prozent-/Noten-Superposition mark (pure, no GUI).

One computation for placing (`UiIntentControllerSuperpositionMixin`), the
correction preview and "Alle PDFs überschreiben", so a mark always shows the
value of the points recorded *now*, never the one from the moment it was
placed. Sums follow the Auswertung's one sum rule (`student_result._summarize`
via `compute_student_result`): bonus tasks add to the achieved points but not
to the maximum, and any unscored task makes the value unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.core.domain.grading_scale import GradingScaleSnapshot
from app.core.domain.model_students import LIVE_GRADE, LIVE_POINTS, LIVE_PERCENT, LiveValue
from app.core.domain.models import ExamProject, TaskDefinition
from app.core.domain.student_result import compute_student_result


@dataclass(frozen=True)
class LiveText:
    """The text to show, or ``None`` with a German ``problem`` ("es fehlt die Bewertung von 2B")."""

    text: str | None
    problem: str = ""


def live_text(
    value: LiveValue,
    *,
    tasks: Sequence[TaskDefinition],
    scores_by_task: dict[str, float],
    grading_scale_snapshot: GradingScaleSnapshot | None,
) -> LiveText:
    """Compute the current text of one person's mark from ``value`` and that person's points.

    - ``points``: achieved sum of the selected tasks, "7" or "7/10" (``show_max``).
    - ``percent``: achieved / maximum of the selection, rounded like the
      Auswertung ("75 %"); the whole exam gives exactly the Auswertung's value.
    - ``grade``: the exam-wide grade of the Notenschlüssel (always all tasks).

    The maximum leaves out bonus tasks; a selection of only bonus tasks uses
    their own maxima instead (else "7/0"). ``tasks`` are the exam's tasks; a
    selected code that no longer exists is a problem, not silently skipped.
    """
    by_code = {task.code: task for task in tasks}
    if value.kind == LIVE_GRADE or not value.task_codes:
        selected = list(tasks)
    else:
        gone = [code for code in value.task_codes if code not in by_code]
        if gone:
            return LiveText(None, f"Aufgabe {', '.join(gone)} gibt es nicht mehr")
        selected = [by_code[code] for code in value.task_codes]
    if value.kind == LIVE_GRADE and grading_scale_snapshot is None:
        return LiveText(None, "der Klausur ist kein Notenschlüssel zugeordnet")
    unscored = [task.code for task in selected if task.code not in scores_by_task]
    if unscored:
        return LiveText(None, f"es fehlt die Bewertung von Aufgabe {', '.join(unscored)}")

    result = compute_student_result(
        student_id="",
        display_name="",
        scores_by_task=scores_by_task,
        all_tasks=selected,
        categories=[],
        category_assignments={},
        grading_scale_snapshot=grading_scale_snapshot if value.kind == LIVE_GRADE else None,
    )
    achieved = result.total_achieved_points
    if achieved is None:
        return LiveText(None, "es fehlt eine Bewertung")
    max_points = result.total_max_points or sum(task.max_points for task in selected)

    if value.kind == LIVE_POINTS:
        return LiveText(f"{achieved:g}/{max_points:g}" if value.show_max else f"{achieved:g}")
    if max_points <= 0:
        return LiveText(None, "es gibt keine bewertbaren Punkte")
    if value.kind == LIVE_PERCENT:
        return LiveText(f"{achieved / max_points * 100:.0f} %")
    if result.grade_label is None:
        return LiveText(None, "die Punktzahl liegt unter der niedrigsten Schwelle des Notenschlüssels")
    return LiveText(result.grade_label)


def current_live_texts(exam: ExamProject, scores: dict[str, dict[str, float]]) -> dict[str, LiveText]:
    """`live_text` of every mark with a `LiveValue`, by ``annotation_id`` (marks of unknown PDFs are skipped).

    ``scores`` is ``{student_id: {task_code: points}}`` as loaded from the
    score repository; shared by the correction preview and the PDF export.
    """
    student_id_by_pdf = {student.pdf_filename: student.student_id for student in exam.students}
    texts: dict[str, LiveText] = {}
    for annotation in exam.pdf_annotations:
        student_id = student_id_by_pdf.get(annotation.student_pdf)
        if annotation.live_value is None or student_id is None:
            continue
        texts[annotation.annotation_id] = live_text(
            annotation.live_value,
            tasks=exam.tasks,
            scores_by_task=scores.get(student_id, {}),
            grading_scale_snapshot=exam.grading_scale_snapshot,
        )
    return texts
