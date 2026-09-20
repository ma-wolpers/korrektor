from __future__ import annotations

from uuid import uuid4

from app.adapters.gui.dialog_services import messagebox
from app.core.domain.annotation_sync import build_annotation_clones, sync_group_members
from app.core.domain.models import ExamProject, PdfAnnotation


class UiIntentControllerAnnotationsMixin:
    """Immediate, sofort-persistierte Mutationen einzelner Korrektur-Annotationen.

    Vor diesem Mixin mutierten Platzieren/Verschieben/Groesse/Rotation/Farbe/
    Loeschen einer Annotation direkt `MainWindow._current_exam.pdf_annotations`
    im GUI-Mixin, ohne jede Persistenz oder History (Meilenstein 0.3 der
    Korrektor-Wunschliste) - nur die zwei Bulk-Mechanismen (Supersymbol,
    Durchdruecken) waren bereits korrekt sofort-persistiert. Jede Methode
    hier folgt dem etablierten `apply_super_symbol_immediate`-Muster:
    Snapshot vor der Mutation -> Mutation -> `save_exam`/`load_exam` -> ein
    `_record_exam_payload_action`-Aufruf, damit `Strg+Z`/`Strg+Y` exakt diese
    eine fachliche Aktion trifft - auch wenn sie (Sync-Gruppe) mehrere
    `PdfAnnotation`-Objekte gleichzeitig aendert.
    """

    @staticmethod
    def _find_annotation(exam: ExamProject, annotation_id: str) -> PdfAnnotation | None:
        return next((item for item in exam.pdf_annotations if item.annotation_id == annotation_id), None)

    @staticmethod
    def _group_or_self(exam: ExamProject, annotation: PdfAnnotation, *, include_detached: bool) -> list[PdfAnnotation]:
        """Resolve the annotations one style-mutation (Farbe/Groesse/Rotation) must touch together.

        A synced annotation touches every member of its `sync_group_id`
        (style attributes are never position_detached-exempt, see
        `sync_group_members`'s docstring); an unsynced one only touches
        itself. Falls back to `[annotation]` if the group ever resolves
        empty (defensive - should not happen for a `sync_group_id`-bearing
        annotation, since it is itself a member of its own group).
        """
        if not annotation.sync_group_id:
            return [annotation]
        members = sync_group_members(exam.pdf_annotations, annotation.sync_group_id, include_detached=include_detached)
        return members or [annotation]

    def _save_annotation_mutation_immediate(
        self,
        *,
        exam: ExamProject,
        description: str,
        before_payload: dict[str, object],
        rollback,
    ) -> ExamProject | None:
        """Persist an already-applied in-memory annotation mutation, or roll it back on failure.

        Shared tail for every method in this mixin: the caller performs its
        specific mutation on `exam` in memory first (append/remove an
        annotation, or set an attribute on one or more sync-group members),
        then calls this. On success, exactly one `_record_exam_payload_action`
        covers the whole mutation as a single undo/redo step, however many
        `PdfAnnotation`s it touched. On failure (`save_exam`/`load_exam`
        raises), `rollback()` undoes the in-memory mutation, no
        `HistoryAction` is pushed, and a clear error is shown - mirrors the
        rollback contract `rename_students_immediate`
        (`ui_intent_controller_naming.py`) already established for its
        (riskier, filesystem-touching) mutation, applied here so a failed
        save never leaves a half-applied, unpersisted change on screen.
        """
        try:
            exam_file = self._deps.exam_repository.save_exam(exam)
            updated = self._deps.exam_repository.load_exam(exam_file)
        except Exception as exc:
            rollback()
            messagebox.showerror("Speichern fehlgeschlagen", f"Markierung konnte nicht gespeichert werden: {exc}")
            return None

        self._record_exam_payload_action(
            description=description,
            exam_id=updated.exam_id,
            before_payload=before_payload,
            after_payload=updated.to_dict(),
        )
        self.refresh_exam_overview()
        return updated

    def place_annotation_immediate(self, *, exam: ExamProject, annotation: PdfAnnotation) -> ExamProject | None:
        """Add one freshly placed or pasted annotation and persist it immediately.

        `annotation` is already fully built by the caller (the GUI knows
        the concrete construction rules - current marker tool/colour/font
        for a fresh placement, or the clipboard contents for a paste); this
        method only owns the persistence/undo side, like every other
        `<verb>_immediate` controller method.
        """
        before_payload = exam.to_dict()
        exam.pdf_annotations.append(annotation)

        def _rollback() -> None:
            exam.pdf_annotations[:] = [
                item for item in exam.pdf_annotations if item.annotation_id != annotation.annotation_id
            ]

        return self._save_annotation_mutation_immediate(
            exam=exam,
            description="Markierung gesetzt",
            before_payload=before_payload,
            rollback=_rollback,
        )

    def delete_annotation_immediate(self, *, exam: ExamProject, annotation_id: str) -> ExamProject | None:
        """Delete one annotation - or its whole sync group at once if it has one - and persist immediately.

        Deleting a synced annotation removes every member of its
        `sync_group_id` together (same semantics as the pre-existing
        `MainWindow._delete_annotation_or_group`, this is now the single
        source of truth for that behaviour): a synced marker has no
        meaningful standalone remainder once one copy is gone.
        """
        annotation = self._find_annotation(exam, annotation_id)
        if annotation is None:
            return None

        before_payload = exam.to_dict()
        previous_annotations = list(exam.pdf_annotations)
        if annotation.sync_group_id:
            exam.pdf_annotations = [
                item for item in exam.pdf_annotations if item.sync_group_id != annotation.sync_group_id
            ]
            description = "Sync-Gruppe geloescht"
        else:
            exam.pdf_annotations = [item for item in exam.pdf_annotations if item.annotation_id != annotation_id]
            description = "Markierung geloescht"

        def _rollback() -> None:
            exam.pdf_annotations = previous_annotations

        return self._save_annotation_mutation_immediate(
            exam=exam,
            description=description,
            before_payload=before_payload,
            rollback=_rollback,
        )

    def resize_annotation_immediate(self, *, exam: ExamProject, annotation_id: str, delta: float) -> ExamProject | None:
        """Change the font size of an annotation - and every sync-group member - by `delta` points."""
        annotation = self._find_annotation(exam, annotation_id)
        if annotation is None:
            return None

        before_payload = exam.to_dict()
        members = self._group_or_self(exam, annotation, include_detached=True)
        next_size = max(8.0, min(96.0, float(annotation.font_size) + delta))
        previous_sizes = [(item, item.font_size) for item in members]
        for item in members:
            item.font_size = next_size

        def _rollback() -> None:
            for item, old_size in previous_sizes:
                item.font_size = old_size

        return self._save_annotation_mutation_immediate(
            exam=exam,
            description=f"Markierungsgroesse: {next_size:.0f}pt",
            before_payload=before_payload,
            rollback=_rollback,
        )

    def rotate_annotation_immediate(
        self, *, exam: ExamProject, annotation_id: str, next_rotation_deg: float
    ) -> ExamProject | None:
        """Set the rotation of an annotation - and every sync-group member - to `next_rotation_deg`.

        `next_rotation_deg` is the caller's already-normalized target angle
        (see `app.core.domain.annotation_sync.normalize_rotation_deg`) - this
        method does not recompute the delta/normalization itself, matching
        every other `_immediate` method's "GUI decides the concrete value,
        controller only persists it" split.
        """
        annotation = self._find_annotation(exam, annotation_id)
        if annotation is None:
            return None

        before_payload = exam.to_dict()
        members = self._group_or_self(exam, annotation, include_detached=True)
        previous_rotations = [(item, item.rotation_deg) for item in members]
        for item in members:
            item.rotation_deg = next_rotation_deg

        def _rollback() -> None:
            for item, old_rotation in previous_rotations:
                item.rotation_deg = old_rotation

        return self._save_annotation_mutation_immediate(
            exam=exam,
            description=f"Markierungswinkel: {next_rotation_deg:.0f}°",
            before_payload=before_payload,
            rollback=_rollback,
        )

    def recolor_annotation_immediate(self, *, exam: ExamProject, annotation_id: str, color_hex: str) -> ExamProject | None:
        """Change the colour of an annotation - and every sync-group member - to `color_hex`."""
        annotation = self._find_annotation(exam, annotation_id)
        if annotation is None:
            return None

        before_payload = exam.to_dict()
        members = self._group_or_self(exam, annotation, include_detached=True)
        previous_colors = [(item, item.color_hex) for item in members]
        for item in members:
            item.color_hex = color_hex

        def _rollback() -> None:
            for item, old_color in previous_colors:
                item.color_hex = old_color

        return self._save_annotation_mutation_immediate(
            exam=exam,
            description="Markierungsfarbe aktualisiert",
            before_payload=before_payload,
            rollback=_rollback,
        )

    def enable_annotation_sync_immediate(
        self, *, exam: ExamProject, annotation_id: str, other_student_pdfs: list[str]
    ) -> ExamProject | None:
        """"Durchdruecken": clone an annotation onto the given other students and persist immediately.

        `other_student_pdfs` is the GUI's already-resolved target set (every
        other correction student, per `MainWindow._correction_student_indices`)
        - this method only resolves those filenames against `exam.students`
        and performs the clone/persist, mirroring the "GUI decides the
        concrete selection, controller only persists it" split used by
        `apply_super_symbol_immediate`'s `matched_student_ids`. Uses the
        same `build_annotation_clones` mechanism as the Supersymbol bulk
        apply. One `HistoryAction` covers the base annotation's new
        `sync_group_id` plus every created clone together.
        """
        annotation = self._find_annotation(exam, annotation_id)
        if annotation is None:
            return None

        before_payload = exam.to_dict()
        previous_annotations = list(exam.pdf_annotations)
        previous_sync_group_id = annotation.sync_group_id

        sync_group_id = f"sg-{uuid4().hex[:12]}"
        annotation.sync_group_id = sync_group_id
        annotation.position_detached = False
        other_students = [student for student in exam.students if student.pdf_filename in other_student_pdfs]
        clones = build_annotation_clones(annotation, other_students, sync_group_id)
        if not clones:
            return None
        exam.pdf_annotations.extend(clones)

        def _rollback() -> None:
            exam.pdf_annotations = previous_annotations
            annotation.sync_group_id = previous_sync_group_id
            annotation.position_detached = False

        return self._save_annotation_mutation_immediate(
            exam=exam,
            description=f"Durchgedrueckt: {len(clones)} Kopien erzeugt",
            before_payload=before_payload,
            rollback=_rollback,
        )

    def disable_annotation_sync_immediate(self, *, exam: ExamProject, annotation_id: str) -> ExamProject | None:
        """"Durchdruecken" deaktivieren: delete every other member of the sync group, un-sync the selected one.

        Unlike `detach_annotation_from_sync_immediate` (Meilenstein 1.3,
        which removes only the selected annotation from an otherwise
        still-active group), this turns the sync group off entirely -
        matches the pre-existing "Durchdruecken"-Toggle semantics.
        """
        annotation = self._find_annotation(exam, annotation_id)
        if annotation is None or not annotation.sync_group_id:
            return None

        before_payload = exam.to_dict()
        previous_annotations = list(exam.pdf_annotations)
        previous_sync_group_id = annotation.sync_group_id
        previous_position_detached = annotation.position_detached

        sync_group_id = annotation.sync_group_id
        exam.pdf_annotations = [
            item
            for item in exam.pdf_annotations
            if item.sync_group_id != sync_group_id or item.annotation_id == annotation.annotation_id
        ]
        annotation.sync_group_id = ""
        annotation.position_detached = False
        removed = len(previous_annotations) - len(exam.pdf_annotations)

        def _rollback() -> None:
            exam.pdf_annotations = previous_annotations
            annotation.sync_group_id = previous_sync_group_id
            annotation.position_detached = previous_position_detached

        return self._save_annotation_mutation_immediate(
            exam=exam,
            description=f"Durchdruecken deaktiviert ({removed} Kopien entfernt)",
            before_payload=before_payload,
            rollback=_rollback,
        )

    def commit_annotation_move_immediate(
        self, *, exam: ExamProject, before_payload: dict[str, object]
    ) -> ExamProject | None:
        """Persist a just-finished drag gesture, using a snapshot taken before the drag started.

        The GUI already moved `annotation.x`/`.y` (and, for a synced,
        non-detached annotation, every group member's position together)
        live during the drag for immediate visual feedback - see
        `MainWindow._on_correction_canvas_drag`, unchanged and still
        unpersisted. `before_payload` must be the exam snapshot taken at
        drag *start* (`MainWindow._on_correction_canvas_press`), not
        recomputed here, since by the time this is called the in-memory
        exam already holds the post-drag (`after`) state - recomputing
        `before_payload = exam.to_dict()` at this point would make undo a
        no-op (this was exactly the bug fixed in Meilenstein 0.2 for
        `save_exam_immediate`). Called at most once per drag gesture
        (`MainWindow._on_correction_canvas_release`), and only if the
        position actually changed - one `HistoryAction` per drag, never one
        per mouse-move.
        """
        before_exam = ExamProject.from_dict(before_payload)
        rollback_positions = [
            (item, item.x, item.y)
            for item in exam.pdf_annotations
            for before_item in before_exam.pdf_annotations
            if item.annotation_id == before_item.annotation_id and (item.x, item.y) != (before_item.x, before_item.y)
        ]

        def _rollback() -> None:
            for item, old_x, old_y in rollback_positions:
                item.x = old_x
                item.y = old_y

        return self._save_annotation_mutation_immediate(
            exam=exam,
            description="Markierung verschoben",
            before_payload=before_payload,
            rollback=_rollback,
        )
