from __future__ import annotations

from pathlib import Path

from app.adapters.gui.dialog_services import filedialog, messagebox
from app.adapters.gui.main_window_constants import COMPETENCY_CHART_SCOPE_LABELS, COMPETENCY_CHART_TYPE_LABELS
from app.infrastructure.repositories.file_utils import render_filename_template, sanitize_filename_stem

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.dialogs import ScrollablePopupWindow
from bw_gui.runtime import listbox_selection, on_listbox_select, ui, widgets
from bw_gui.widgets import Checkbox

_SECTION_LABELS: tuple[tuple[str, str], ...] = (
    ("summary", "Gesamt/Note"),
    ("tasks", "Pro Aufgabe"),
    ("categories", "Pro Kategorie"),
    ("chart", "Kompetenzgrad-Diagramm"),
)
_DEFAULT_FILENAME_TEMPLATE = "{Name}_{Klasse}_{Fach}_{Nr}"


class MainWindowBatchExportMixin:
    """Zentraler Exportmodus (Popup): alle ausgewaehlten Schueler:innen-PDFs in einem Rutsch exportieren.

    Reine GUI-Schicht um `UiIntentControllerBatchExportMixin.export_students_batch`
    (`ui_intent_controller_batch_export.py`) - trifft selbst keine
    fachliche Entscheidung (welche Sektions-/Ordner-/Namensschema-
    Kombination gueltig ist, welche Kollisionen erlaubt sind), das bleibt
    Sache des Controllers. Ohne angehakte Sektion exportiert der Knopf
    trotzdem: Die Dateien werden nur kopiert und umbenannt, ohne
    Statistikseite.
    """

    def _open_batch_export_popup(self, preselected_ids: list[str] | None = None) -> None:
        """Open the batch export; ``preselected_ids`` (e.g. from the evaluation overview) narrows the
        initial selection, default is everybody."""
        if self._controller is None or self._current_exam is None:
            return
        if not self._current_exam.students:
            messagebox.showinfo("Hinweis", "Diese Klausur hat keine Schüler:innen.")
            return
        self._build_batch_export_popup()
        self._batch_export_scores = self._controller.load_scores_for_exam(exam=self._current_exam)
        self._batch_export_list.delete(0, ui.END)
        for student in self._current_exam.students:
            self._batch_export_list.insert(ui.END, student.display_name)
        indices = [
            index for index, student in enumerate(self._current_exam.students)
            if preselected_ids is None or student.student_id in preselected_ids
        ]
        listbox_selection.set(self._batch_export_list, indices)
        self._update_batch_export_preview()

    def _build_batch_export_popup(self) -> None:
        popup = ScrollablePopupWindow(
            self.root,
            title="Sammelexport",
            geometry="640x760",
            minsize=(480, 480),
            theme_key=self._tooltip_theme_key,
        )

        body = widgets.Frame(popup.content, padding=10)
        body.pack(fill=ui.BOTH, expand=True)

        widgets.Label(body, text="Personen", style="Muted.TLabel").pack(anchor=ui.W)
        self._batch_export_list = ui.Listbox(body, selectmode=ui.EXTENDED, height=6, exportselection=False)
        self._batch_export_list.pack(fill=ui.X, pady=(4, 0))
        self._attach_hover_help(
            self._batch_export_list, label="Auswahl der zu exportierenden Personen (Mehrfachauswahl möglich)"
        )
        on_listbox_select(self._batch_export_list, lambda _change: self._update_batch_export_preview())

        sections_frame = widgets.Frame(body, style="Surface.TFrame")
        sections_frame.pack(fill=ui.X, pady=(12, 0))
        widgets.Label(sections_frame, text="Auswertungs-Bausteine", style="Muted.TLabel").pack(anchor=ui.W)
        self._batch_export_section_vars = {}
        for key, label in _SECTION_LABELS:
            var = ui.BooleanVar(value=True)
            self._batch_export_section_vars[key] = var
            Checkbox(sections_frame, text=label, variable=var).pack(anchor=ui.W)

        chart_controls = widgets.Frame(body, style="Surface.TFrame")
        chart_controls.pack(fill=ui.X, pady=(8, 0))
        widgets.Label(chart_controls, text="Diagramm", style="Muted.TLabel").pack(side=ui.LEFT)
        self._batch_export_chart_type_var = ui.StringVar(value=COMPETENCY_CHART_TYPE_LABELS[0])
        widgets.Combobox(
            chart_controls,
            textvariable=self._batch_export_chart_type_var,
            state="readonly",
            width=12,
            values=COMPETENCY_CHART_TYPE_LABELS,
        ).pack(side=ui.LEFT, padx=(8, 0))
        self._batch_export_chart_scope_var = ui.StringVar(value=COMPETENCY_CHART_SCOPE_LABELS[0])
        widgets.Combobox(
            chart_controls,
            textvariable=self._batch_export_chart_scope_var,
            state="readonly",
            width=14,
            values=COMPETENCY_CHART_SCOPE_LABELS,
        ).pack(side=ui.LEFT, padx=(8, 0))

        self._batch_export_per_student_folders_var = ui.BooleanVar(value=False)
        Checkbox(
            body,
            text="Pro Schüler:in eigener Ordner",
            variable=self._batch_export_per_student_folders_var,
            on_select=lambda _selected: self._update_batch_export_preview(),
        ).pack(anchor=ui.W, pady=(12, 0))

        naming_frame = widgets.Frame(body, style="Surface.TFrame")
        naming_frame.pack(fill=ui.X, pady=(8, 0))
        widgets.Label(naming_frame, text="Namensschema", style="Muted.TLabel").pack(anchor=ui.W)
        self._batch_export_filename_template_var = ui.StringVar(value=_DEFAULT_FILENAME_TEMPLATE)
        template_entry = widgets.Entry(naming_frame, textvariable=self._batch_export_filename_template_var)
        template_entry.pack(fill=ui.X, pady=(4, 0))
        self._attach_hover_help(template_entry, label="Platzhalter: {Name}, {Klasse}, {Fach}, {Nr}")
        self._batch_export_filename_template_var.trace_add("write", lambda *_args: self._update_batch_export_preview())
        self._batch_export_preview_var = ui.StringVar(value="")
        widgets.Label(naming_frame, textvariable=self._batch_export_preview_var, style="Muted.TLabel").pack(
            anchor=ui.W, pady=(4, 0)
        )

        self._batch_export_export_button = widgets.Button(
            body, text="Exportieren...", style="SecondaryAction.TButton", command=self._run_batch_export
        )
        self._batch_export_export_button.pack(anchor=ui.E, pady=(14, 0))

        widgets.Button(
            body, text="Schließen", style="SecondaryAction.TButton", command=self._close_batch_export_popup
        ).pack(anchor=ui.E, pady=(6, 0))

        self._batch_export_popup = popup

    def _update_batch_export_preview(self) -> None:
        """Show the resulting filename for the first selected person, using the live template/folder settings."""
        if self._current_exam is None or not hasattr(self, "_batch_export_preview_var"):
            return
        students = self._current_exam.students
        if not students:
            return
        selected_indices = self._batch_export_list.curselection() if self._batch_export_list is not None else ()
        preview_index = selected_indices[0] if selected_indices else 0
        if preview_index >= len(students):
            return
        student = students[preview_index]
        stem = render_filename_template(
            self._batch_export_filename_template_var.get(),
            display_name=student.display_name,
            school_class=self._current_exam.school_class,
            subject=self._current_exam.subject,
            index=preview_index + 1,
        )
        preview_name = f"{stem}.pdf" if stem is not None else "(ungültiges Namensschema)"
        if self._batch_export_per_student_folders_var.get():
            folder_hint = sanitize_filename_stem(student.display_name, replace_spaces_with=None) or "?"
            preview_name = f"{folder_hint}/{preview_name}"
        self._batch_export_preview_var.set(f"Beispiel: {preview_name}")

    def _run_batch_export(self) -> None:
        if self._current_exam is None or self._controller is None or self._batch_export_scores is None:
            return
        selected_indices = self._batch_export_list.curselection()
        if not selected_indices:
            messagebox.showinfo("Hinweis", "Bitte mindestens eine Person auswählen.")
            return
        students = self._current_exam.students
        student_ids = [students[index].student_id for index in selected_indices if index < len(students)]
        sections = frozenset(key for key, var in self._batch_export_section_vars.items() if var.get())

        target_dir = filedialog.askdirectory(title="Zielordner für den Sammelexport wählen")
        if not target_dir:
            return

        result = self._controller.export_students_batch(
            exam=self._current_exam,
            student_ids=student_ids,
            scores=self._batch_export_scores,
            sections=sections,
            chart_type=self._batch_export_chart_type_var.get(),
            chart_scope=self._batch_export_chart_scope_var.get(),
            output_dir=Path(target_dir),
            per_student_folders=self._batch_export_per_student_folders_var.get(),
            filename_template=self._batch_export_filename_template_var.get(),
        )
        if result is None:
            return
        exported, failed = result
        if failed:
            messagebox.showwarning(
                "Sammelexport teilweise fehlgeschlagen",
                f"{len(exported)} exportiert, fehlgeschlagen für:\n" + "\n".join(failed),
            )
        else:
            messagebox.showinfo("Sammelexport abgeschlossen", f"{len(exported)} PDF(s) exportiert nach:\n{target_dir}")

    def _close_batch_export_popup(self) -> None:
        if self._batch_export_popup is not None and self._batch_export_popup.winfo_exists():
            self._batch_export_popup._request_close()
