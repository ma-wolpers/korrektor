from __future__ import annotations

from app.adapters.gui.dialog_services import messagebox, simpledialog
from app.core.domain.models import ExamProject

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.dialogs import ScrollablePopupWindow
from bw_gui.runtime import ui, widgets
from bw_gui.widgets import DragDropController

_UNCATEGORIZED_DROP_ID = "__uncategorized__"


class MainWindowTaskCategoriesMixin:
    """Kategorien-Zuordnungsseite (Meilenstein 4.3): Aufgaben per Drag-and-Drop auf Kategorien ziehen.

    Popup wie die Notenschluessel-Verwaltung (Meilenstein 2.4) - nutzt
    `bw_gui.dialogs.ScrollablePopupWindow` (bw-gui-Standard fuer Popups,
    siehe `bw-gui/docs/SCROLLABILITY_CONTRACT.md`), Inhalt bei jedem
    Oeffnen/nach jeder Aenderung komplett neu aufgebaut
    (`_refresh_task_category_popup`): Aufgaben- und Kategorienzahl pro
    Klausur ist klein genug, dass ein voller Rebuild einfacher und weniger
    fehleranfaellig ist als inkrementelles Widget-Update. Nutzt
    `bw_gui.widgets.DragDropController` (Meilenstein 4.2, neu in bw-gui) -
    eine Aufgaben-Zeile ist eine Drag-Quelle (Payload: `task_code`), jede
    Kategorie-Box und die "Unkategorisiert"-Box sind Drop-Ziele.
    """

    def _open_task_category_popup(self) -> None:
        if self._controller is None or self._current_exam is None:
            return
        # ScrollablePopupWindow is one-shot - build fresh on every open.
        self._build_task_category_popup()
        self._refresh_task_category_popup()

    def _build_task_category_popup(self) -> None:
        popup = ScrollablePopupWindow(
            self.root,
            title="Kategorien zuordnen",
            geometry="760x520",
            minsize=(560, 380),
            theme_key=self._tooltip_theme_key,
            request_close_confirmation=self._on_task_category_popup_close_requested,
        )
        self._register_popup_window(popup)

        body = widgets.Frame(popup.content, padding=10)
        body.pack(fill=ui.BOTH, expand=True)

        tasks_panel = widgets.Frame(body, style="Surface.TFrame", padding=(0, 0, 10, 0))
        tasks_panel.pack(side=ui.LEFT, fill=ui.BOTH, expand=True)
        widgets.Label(tasks_panel, text="Aufgaben (ziehen auf eine Kategorie)", style="Muted.TLabel").pack(anchor=ui.W)
        self._task_category_tasks_frame = widgets.Frame(tasks_panel, style="Surface.TFrame")
        self._task_category_tasks_frame.pack(fill=ui.BOTH, expand=True, pady=(4, 0))

        categories_panel = widgets.Frame(body, style="Surface.TFrame", padding=(10, 0, 0, 0))
        categories_panel.pack(side=ui.LEFT, fill=ui.BOTH, expand=True)
        widgets.Label(categories_panel, text="Kategorien", style="Muted.TLabel").pack(anchor=ui.W)
        self._task_category_categories_frame = widgets.Frame(categories_panel, style="Surface.TFrame")
        self._task_category_categories_frame.pack(fill=ui.BOTH, expand=True, pady=(4, 0))

        add_category_button = widgets.Button(
            categories_panel,
            text="+ Kategorie",
            style="SecondaryAction.TButton",
            command=self._add_task_category,
        )
        add_category_button.pack(anchor=ui.W, pady=(6, 0))

        widgets.Button(body, text="Schliessen", style="SecondaryAction.TButton", command=self._close_task_category_popup).pack(
            anchor=ui.E, pady=(10, 0)
        )

        self._task_category_drag_drop = DragDropController(popup)
        self._task_category_popup = popup

    def _gather_exam_tasks(self, exam: ExamProject) -> list[tuple[str, str]]:
        """Every `(task_code, area_code)` pair across all Standardbereiche, sorted by area then code."""
        pairs = [
            (task.code, region.assigned_area_codes[0] if region.assigned_area_codes else "?")
            for region in exam.regions
            for task in region.tasks
        ]
        return sorted(pairs, key=lambda item: (item[1], item[0]))

    def _refresh_task_category_popup(self) -> None:
        if self._current_exam is None or self._task_category_drag_drop is None:
            return
        exam = self._current_exam

        for child in self._task_category_tasks_frame.winfo_children():
            child.destroy()
        for child in self._task_category_categories_frame.winfo_children():
            child.destroy()

        category_name_by_id = {category.category_id: category.name for category in exam.task_categories}
        for task_code, area_code in self._gather_exam_tasks(exam):
            assigned_id = exam.task_category_assignments.get(task_code)
            assigned_name = category_name_by_id.get(assigned_id, "unkategorisiert") if assigned_id else "unkategorisiert"
            row = widgets.Label(
                self._task_category_tasks_frame,
                text=f"{task_code} (Bereich {area_code}) -> {assigned_name}",
                style="Surface.TLabel",
                relief="groove",
                padding=(6, 4),
            )
            row.pack(fill=ui.X, pady=(0, 4))
            self._task_category_drag_drop.register_source(
                row, get_payload=lambda code=task_code: code, preview_text=lambda code: code
            )

        for category in exam.task_categories:
            self._build_task_category_box(category.category_id, category.name)

        uncategorized_box = widgets.Frame(self._task_category_categories_frame, style="Surface.TFrame", relief="groove", padding=8)
        uncategorized_box.pack(fill=ui.X, pady=(0, 6))
        widgets.Label(uncategorized_box, text="Unkategorisiert (zum Entfernen hierher ziehen)", style="Muted.TLabel").pack(
            anchor=ui.W
        )
        self._task_category_drag_drop.register_target(
            uncategorized_box, on_drop=lambda task_code: self._on_task_dropped(task_code, None)
        )

    def _build_task_category_box(self, category_id: str, name: str) -> None:
        box = widgets.Frame(self._task_category_categories_frame, style="Surface.TFrame", relief="groove", padding=8)
        box.pack(fill=ui.X, pady=(0, 6))
        widgets.Label(box, text=name, style="Status.TLabel").pack(side=ui.LEFT)

        actions = widgets.Frame(box, style="Surface.TFrame")
        actions.pack(side=ui.RIGHT)
        widgets.Button(actions, text="▲", width=2, style="SecondaryAction.TButton", command=lambda: self._move_task_category(category_id, -1)).pack(side=ui.LEFT)
        widgets.Button(actions, text="▼", width=2, style="SecondaryAction.TButton", command=lambda: self._move_task_category(category_id, 1)).pack(side=ui.LEFT, padx=(2, 0))
        widgets.Button(actions, text="Umbenennen", style="SecondaryAction.TButton", command=lambda: self._rename_task_category(category_id)).pack(side=ui.LEFT, padx=(6, 0))
        widgets.Button(actions, text="Loeschen", style="SecondaryAction.TButton", command=lambda: self._delete_task_category(category_id)).pack(side=ui.LEFT, padx=(6, 0))

        self._task_category_drag_drop.register_target(
            box, on_drop=lambda task_code: self._on_task_dropped(task_code, category_id)
        )

    def _on_task_dropped(self, task_code: str, category_id: str | None) -> None:
        if self._current_exam is None or self._controller is None:
            return
        updated = self._controller.assign_task_to_category_immediate(
            exam=self._current_exam, task_code=task_code, category_id=category_id
        )
        if updated is None:
            return
        self._current_exam = updated
        self._refresh_task_category_popup()

    def _add_task_category(self) -> None:
        if self._current_exam is None or self._controller is None:
            return
        name = simpledialog.askstring("Neue Kategorie", "Name der Kategorie:")
        if not name:
            return
        updated = self._controller.save_task_category_immediate(exam=self._current_exam, category_id=None, name=name)
        if updated is None:
            return
        self._current_exam = updated
        self._refresh_task_category_popup()

    def _rename_task_category(self, category_id: str) -> None:
        if self._current_exam is None or self._controller is None:
            return
        current = next((item for item in self._current_exam.task_categories if item.category_id == category_id), None)
        if current is None:
            return
        name = simpledialog.askstring("Kategorie umbenennen", "Neuer Name:", initialvalue=current.name)
        if not name:
            return
        updated = self._controller.save_task_category_immediate(exam=self._current_exam, category_id=category_id, name=name)
        if updated is None:
            return
        self._current_exam = updated
        self._refresh_task_category_popup()

    def _delete_task_category(self, category_id: str) -> None:
        if self._current_exam is None or self._controller is None:
            return
        confirm = messagebox.askyesno(
            "Kategorie loeschen",
            "Kategorie wirklich loeschen? Zugeordnete Aufgaben werden unkategorisiert, nicht geloescht.",
        )
        if not confirm:
            return
        updated = self._controller.delete_task_category_immediate(exam=self._current_exam, category_id=category_id)
        if updated is None:
            return
        self._current_exam = updated
        self._refresh_task_category_popup()

    def _move_task_category(self, category_id: str, delta: int) -> None:
        if self._current_exam is None or self._controller is None:
            return
        ids = [item.category_id for item in self._current_exam.task_categories]
        index = ids.index(category_id)
        target_index = index + delta
        if target_index < 0 or target_index >= len(ids):
            return
        ids[index], ids[target_index] = ids[target_index], ids[index]
        updated = self._controller.reorder_task_categories_immediate(exam=self._current_exam, ordered_category_ids=ids)
        if updated is None:
            return
        self._current_exam = updated
        self._refresh_task_category_popup()

    def _on_task_category_popup_close_requested(self) -> bool:
        """Popup-registry cleanup shared by every close path - see the identical pattern/rationale
        in `main_window_student_result.py:_on_student_result_popup_close_requested`."""
        if self._task_category_popup is not None:
            popup_id = str(self._task_category_popup)
            self._popup_registry.close_popup(popup_id)
            self._tracked_popup_ids.discard(popup_id)
        return True

    def _close_task_category_popup(self) -> None:
        if self._task_category_popup is not None and self._task_category_popup.winfo_exists():
            self._task_category_popup._request_close()
