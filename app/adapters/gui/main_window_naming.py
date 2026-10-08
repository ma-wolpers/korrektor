from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz

from app.adapters.gui.dialog_services import messagebox
from app.adapters.gui.main_window_import_split_input import prefer_toplevel_bindings
from app.adapters.gui.ui_intents import UiIntent
from app.core.domain.models import ExamProject
from bw_gui.contracts.keybinding import UI_MODE_DIALOG, UI_MODE_EDITOR
from bw_gui.theming import theme_canvas

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import WindowShortcutBinder, ui, widgets

_STAGE_REGION = "region"
_STAGE_CAPTURE = "capture"


@dataclass
class NamingWindowView:
    """Widgets and state of the "Namen erfassen & umbenennen" window (one per open window)."""

    popup: Any
    canvas: Any
    info_var: Any
    hint_var: Any
    name_var: Any
    name_entry: Any
    progress_var: Any
    stage_button: Any
    rename_button: Any
    region_bar: Any
    capture_bar: Any
    bars: list[Any]
    stage: str = _STAGE_REGION
    page: int = 1
    cursor: int = 0
    scale: float = 1.0
    photo: Any = None
    drag_start: tuple[float, float] | None = None
    drag_rect: int | None = None
    pending_render: str | None = None
    binder: Any = None


class MainWindowNamingMixin:
    """Menü "Klausur" → "Namen erfassen & umbenennen…": a window instead of a Zuschnitt sub-mode.

    Stage 1 sets the shared name field on the Superseite (drag a box; ↑/↓
    page). Stage 2 walks the students on a crop of that field (←/→ person,
    also inside the name field; Enter takes the name and moves on) and
    "Alle umbenennen" runs the existing rollback-safe rename. Typed names
    stay in ``_pending_student_names`` while the exam is open, also across
    closing/reopening this window. Lifecycle like the import wizard: one
    window, one idempotent end method, ``<Destroy>`` only for the toplevel
    itself; the bars are packed before the canvas so they always stay visible.
    """

    def open_naming_window(self) -> None:
        """Open (or bring to front) the naming window for the current exam."""
        if self._current_exam is None or not self._current_exam.students:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur öffnen.")
            return
        view = self._naming_window_view
        if view is not None and self._import_split_window_alive(view.popup):
            view.popup.deiconify()
            view.popup.lift()
            view.popup.focus_force()
            return
        self._end_naming_window()
        self._naming_window_view = self._build_naming_window()
        exam = self._current_exam
        self._naming_window_view.page = exam.name_region_page if exam.name_region else 1
        self._show_naming_stage(_STAGE_REGION)

    def _build_naming_window(self) -> NamingWindowView:
        popup = ui.Toplevel(self.root)
        popup.title(f"Namen erfassen & umbenennen – {self._current_exam.exam_name}")
        popup.transient(self.root)
        popup.geometry("900x760")
        self._register_popup_window(popup)

        info_var = ui.StringVar(value="")
        header = widgets.Frame(popup, padding=(10, 10, 10, 6))
        header.pack(side=ui.TOP, fill=ui.X)
        widgets.Label(header, textvariable=info_var, style="Muted.TLabel", anchor=ui.W).pack(side=ui.LEFT, fill=ui.X)

        actions = widgets.Frame(popup, padding=(10, 4, 10, 10))
        actions.pack(side=ui.BOTTOM, fill=ui.X)
        stage_button = widgets.Button(actions, text="", style="SecondaryAction.TButton", command=self._toggle_naming_stage, takefocus=False)
        stage_button.pack(side=ui.LEFT)
        widgets.Button(actions, text="Schließen", style="SecondaryAction.TButton", command=self._end_naming_window, takefocus=False).pack(side=ui.RIGHT)
        rename_button = widgets.Button(actions, text="Alle umbenennen", style="PrimaryAction.TButton", command=self._rename_all_students, takefocus=False)
        rename_button.pack(side=ui.RIGHT, padx=(0, 8))

        hint_var = ui.StringVar(value="")
        region_bar = widgets.Frame(popup, padding=(10, 2, 10, 2))
        widgets.Button(region_bar, text="▲ Seite", style="SecondaryAction.TButton", takefocus=False, command=lambda: self._change_naming_page(-1)).pack(side=ui.LEFT)
        widgets.Button(region_bar, text="Seite ▼", style="SecondaryAction.TButton", takefocus=False, command=lambda: self._change_naming_page(1)).pack(side=ui.LEFT, padx=(8, 0))
        widgets.Label(region_bar, textvariable=hint_var, style="Muted.TLabel", anchor=ui.W).pack(side=ui.LEFT, fill=ui.X, expand=True, padx=(12, 0))

        capture_bar = widgets.Frame(popup, padding=(10, 2, 10, 2))
        nav = widgets.Frame(capture_bar)
        nav.pack(fill=ui.X)
        widgets.Button(nav, text="◀ Person", style="SecondaryAction.TButton", takefocus=False, command=lambda: self._change_naming_student(-1)).pack(side=ui.LEFT)
        widgets.Button(nav, text="Person ▶", style="SecondaryAction.TButton", takefocus=False, command=lambda: self._change_naming_student(1)).pack(side=ui.LEFT, padx=(8, 0))
        widgets.Label(nav, text="Name:", style="Muted.TLabel").pack(side=ui.LEFT, padx=(16, 4))
        name_var = ui.StringVar(value="")
        name_entry = widgets.Entry(nav, textvariable=name_var, width=36)
        name_entry.pack(side=ui.LEFT, fill=ui.X, expand=True)
        name_entry.bind("<FocusOut>", lambda _event: self._commit_naming_field_if_possible())
        progress_var = ui.StringVar(value="")
        widgets.Label(capture_bar, textvariable=progress_var, style="Muted.TLabel", anchor=ui.W).pack(fill=ui.X, pady=(4, 0))

        canvas_bg, canvas_border = self._canvas_theme_tokens()
        canvas = ui.Canvas(popup, bg=canvas_bg, highlightthickness=1, highlightbackground=canvas_border, takefocus=0)
        canvas.pack(side=ui.TOP, fill=ui.BOTH, expand=True, padx=10, pady=(0, 6))
        theme_canvas(canvas, self._tooltip_theme_key)
        canvas.bind("<ButtonPress-1>", self._on_naming_canvas_press)
        canvas.bind("<B1-Motion>", self._on_naming_canvas_drag)
        canvas.bind("<ButtonRelease-1>", self._on_naming_canvas_release)
        canvas.bind("<Configure>", lambda _event: self._schedule_naming_render(), add="+")

        view = NamingWindowView(
            popup=popup, canvas=canvas, info_var=info_var, hint_var=hint_var, name_var=name_var, name_entry=name_entry,
            progress_var=progress_var, stage_button=stage_button, rename_button=rename_button,
            region_bar=region_bar, capture_bar=capture_bar, bars=[header, actions],
        )
        popup.protocol("WM_DELETE_WINDOW", self._end_naming_window)
        popup.bind("<Destroy>", lambda event: self._on_naming_window_destroyed(event, view), add="+")
        self._install_naming_keys(view)
        popup.minsize(560, 420)
        return view

    def _install_naming_keys(self, view: NamingWindowView) -> None:
        """←/→ person and Enter (stage 2), ↑/↓ page (stage 1) - also with focus in the name field."""
        binder = WindowShortcutBinder(
            view.popup, hsm_contract=self._hsm_contract, mode_provider=lambda: UI_MODE_DIALOG,
            on_dispatch=self._record_laufkern_intent_dispatch,
        )
        for sequence, suffix, intent, action in (
            ("<Left>", "prev_person", UiIntent.NAMING_PREV_PERSON, lambda: self._change_naming_student(-1)),
            ("<Right>", "next_person", UiIntent.NAMING_NEXT_PERSON, lambda: self._change_naming_student(1)),
            ("<Return>", "commit", UiIntent.NAMING_COMMIT, self._commit_and_next_naming_student),
            ("<KP_Enter>", "commit_keypad", UiIntent.NAMING_COMMIT, self._commit_and_next_naming_student),
            ("<Up>", "prev_page", UiIntent.NAMING_PREV_PAGE, lambda: self._change_naming_page(-1)),
            ("<Down>", "next_page", UiIntent.NAMING_NEXT_PAGE, lambda: self._change_naming_page(1)),
        ):
            binder.bind(
                sequence, self._naming_key_handler(action), binding_id=f"naming.{suffix}", intent=intent,
                modes=(UI_MODE_DIALOG, UI_MODE_EDITOR), allow_when_text_input=True,
            )
        view.binder = binder
        prefer_toplevel_bindings(view.name_entry, view.popup)

    def _naming_key_handler(self, action):
        def _handle(_event) -> str:
            if self._naming_window_view is not None and self._current_exam is not None:
                action()
            return "break"

        return _handle

    def _show_naming_stage(self, stage: str) -> None:
        """Switch between "Namensfeld festlegen" and "Namen erfassen" (bars packed before the canvas)."""
        view = self._naming_window_view
        if view is None:
            return
        if stage == _STAGE_CAPTURE and self._current_exam.name_region is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst das Namensfeld aufziehen.", parent=view.popup)
            stage = _STAGE_REGION
        view.stage = stage
        view.region_bar.pack_forget()
        view.capture_bar.pack_forget()
        if stage == _STAGE_REGION:
            view.region_bar.pack(side=ui.BOTTOM, fill=ui.X, before=view.canvas)
            view.stage_button.configure(text="Namen erfassen ▶")
            view.rename_button.pack_forget()
        else:
            view.capture_bar.pack(side=ui.BOTTOM, fill=ui.X, before=view.canvas)
            view.stage_button.configure(text="◀ Namensfeld anpassen")
            view.rename_button.pack(side=ui.RIGHT, padx=(0, 8))
            view.cursor = min(view.cursor, len(self._current_exam.students) - 1)
            self._load_naming_field()
            view.popup.after_idle(self._focus_naming_entry)
        self._render_naming_window()

    def _toggle_naming_stage(self) -> None:
        view = self._naming_window_view
        if view is None:
            return
        if view.stage == _STAGE_CAPTURE:
            self._commit_naming_field_if_possible()
            self._show_naming_stage(_STAGE_REGION)
        else:
            self._show_naming_stage(_STAGE_CAPTURE)

    def _schedule_naming_render(self) -> None:
        """Debounced re-render after the canvas was resized."""
        view = self._naming_window_view
        if view is None:
            return
        if view.pending_render is not None:
            view.popup.after_cancel(view.pending_render)
        view.pending_render = view.popup.after(120, self._render_naming_window)

    def _render_naming_window(self) -> None:
        view = self._naming_window_view
        if view is None or self._current_exam is None:
            return
        view.pending_render = None
        if view.stage == _STAGE_REGION:
            self._render_naming_region_stage()
        else:
            self._render_naming_capture_page()

    def _end_naming_window(self) -> None:
        """Close the naming window (idempotent). Typed names stay pending for this exam."""
        view = self._naming_window_view
        self._naming_window_view = None
        if view is None:
            return
        self._commit_naming_field_if_possible(view)
        self._destroy_import_split_window(view.popup)

    def _on_naming_window_destroyed(self, event, view: NamingWindowView) -> None:
        if event.widget is view.popup and self._naming_window_view is view:
            self._naming_window_view = None
            self._destroy_import_split_window(view.popup)

    def _check_name_region_geometry(self, exam: ExamProject, page_number: int) -> list[str]:
        """Report students whose page geometry at `page_number` differs from the first.

        `name_region` assumes every student's PDF has the same page size and
        rotation at `page_number`; this only detects and reports a mismatch
        (purely informational) - it does not normalize or exclude anything.
        """
        folder = Path(exam.folder_path)
        reference: tuple[fitz.Rect, int] | None = None
        mismatched: list[str] = []
        for student in exam.students:
            if page_number > student.page_count or not (folder / student.pdf_filename).exists():
                continue
            try:
                page = self._naming_document(student.pdf_filename).load_page(page_number - 1)
            except Exception:
                continue
            if reference is None:
                reference = (page.rect, int(page.rotation))
                continue
            rect, rotation = reference
            if abs(page.rect.width - rect.width) > 1.0 or abs(page.rect.height - rect.height) > 1.0 or int(page.rotation) != rotation:
                mismatched.append(student.display_name or student.student_id)
        return mismatched

    def _naming_document(self, pdf_filename: str) -> fitz.Document:
        """Open (and cache) a student PDF of the current exam."""
        document = self._doc_cache.get(pdf_filename)
        if document is None:
            document = fitz.open(Path(self._current_exam.folder_path) / pdf_filename)
            self._doc_cache[pdf_filename] = document
        return document
