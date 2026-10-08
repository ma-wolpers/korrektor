from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.adapters.gui.dialog_services import choicedialog, messagebox
from app.adapters.gui.scan_workshop_session import ScanWorkshopSession
from bw_gui.dialogs import ChoiceOption
from bw_gui.theming import theme_canvas

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets

SCAN_KEY_HELP = "←/→ Person · ↑/↓ Seite · Strg+↑/↓ verschieben · Entf löschen · Strg+←/→ drehen · Strg+Shift+←/→ 90° · Klick: Fadenkreuz"
_MAX_LISTED = 15


@dataclass
class ScanWorkshopView:
    """Widgets of the Scan-Werkstatt view (built once with the main window)."""

    info_var: Any
    pending_var: Any
    degree_var: Any
    degree_hint_var: Any
    degree_entry: Any
    canvas: Any
    page_tree: Any
    delete_button: Any
    photo: Any = None
    image_box: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    pending_render: str | None = None
    degree_flush: str | None = None
    suppress_degree: bool = False


class MainWindowScanWorkshopMixin:
    """Scan-Werkstatt: edit the student PDFs (order, delete, rotate) before the Zuschnitt.

    Pending edits live in a Tk-free `ScanWorkshopSession`; nothing touches a
    file until "Änderungen übernehmen" (controller transaction over PDFs and
    exam data, undoable with a warning). Leaving the view with pending edits
    asks: übernehmen / verwerfen / abbrechen. Layout contract as everywhere:
    bars packed before the preview, so they never leave the window.
    """

    def _build_scan_workshop_view(self) -> None:
        """Build the view once: header, bars packed at the bottom *before* the preview (never pushed out), page list right, canvas left."""
        root = self._scan_workshop_view
        info_var, pending_var = ui.StringVar(value=""), ui.StringVar(value="")
        header = widgets.Frame(root, style="Surface.TFrame")
        header.pack(side=ui.TOP, fill=ui.X)
        widgets.Label(header, text="Scan-Werkstatt", style="Title.TLabel").pack(side=ui.LEFT)
        widgets.Label(header, textvariable=info_var, style="Muted.TLabel", anchor=ui.W).pack(side=ui.LEFT, fill=ui.X, expand=True, padx=(12, 0))

        actions = widgets.Frame(root, style="Surface.TFrame")
        actions.pack(side=ui.BOTTOM, fill=ui.X, pady=(6, 0))
        widgets.Button(actions, text="Zurück zur Klausur", style="SecondaryAction.TButton", command=self._leave_scan_workshop).pack(side=ui.LEFT)
        widgets.Button(actions, text="Änderungen übernehmen", style="PrimaryAction.TButton", command=self._apply_scan_workshop).pack(side=ui.RIGHT)
        widgets.Button(actions, text="Verwerfen", style="SecondaryAction.TButton", command=self._discard_scan_workshop).pack(side=ui.RIGHT, padx=(0, 8))
        widgets.Label(actions, textvariable=pending_var, style="Status.TLabel", anchor=ui.W).pack(side=ui.LEFT, fill=ui.X, expand=True, padx=12)

        tools = widgets.Frame(root, style="Surface.TFrame")
        tools.pack(side=ui.BOTTOM, fill=ui.X, pady=(6, 0))
        for text, command in (
            ("◀ Person", lambda: self._scan_go_student(-1)), ("Person ▶", lambda: self._scan_go_student(1)),
            ("▲ Seite", lambda: self._scan_go_page(-1)), ("Seite ▼", lambda: self._scan_go_page(1)),
            ("Seite nach oben", lambda: self._scan_move_page(-1)), ("Seite nach unten", lambda: self._scan_move_page(1)),
        ):
            widgets.Button(tools, text=text, style="SecondaryAction.TButton", command=command, takefocus=False).pack(side=ui.LEFT, padx=(0, 6))
        delete_button = widgets.Button(tools, text="Seite löschen", style="SecondaryAction.TButton", command=self._scan_toggle_delete, takefocus=False)
        delete_button.pack(side=ui.LEFT, padx=(6, 6))
        for text, command in (("↺", lambda: self._scan_rotate_key(-1)), ("↻", lambda: self._scan_rotate_key(1)), ("↺ 90°", lambda: self._scan_rotate_quarter_key(-1)), ("↻ 90°", lambda: self._scan_rotate_quarter_key(1))):
            widgets.Button(tools, text=text, style="SecondaryAction.TButton", command=command, takefocus=False).pack(side=ui.LEFT, padx=(0, 4))
        degree_var, degree_hint_var = ui.StringVar(value="0"), ui.StringVar(value="")
        degree_entry = widgets.Entry(tools, textvariable=degree_var, width=7)
        degree_entry.pack(side=ui.LEFT, padx=(8, 2))
        widgets.Label(tools, text="°", style="Muted.TLabel").pack(side=ui.LEFT)
        widgets.Label(tools, textvariable=degree_hint_var, style="Status.TLabel", anchor=ui.W).pack(side=ui.LEFT, fill=ui.X, expand=True, padx=(8, 0))
        degree_entry.bind("<KeyRelease>", self._on_scan_degree_typed)
        degree_entry.bind("<Return>", lambda _event: self._flush_scan_degree())
        degree_entry.bind("<FocusOut>", lambda _event: self._flush_scan_degree())
        widgets.Label(root, text=SCAN_KEY_HELP, style="Muted.TLabel", anchor=ui.W).pack(side=ui.BOTTOM, fill=ui.X, pady=(4, 0))

        middle = widgets.Frame(root, style="Surface.TFrame")
        middle.pack(side=ui.TOP, fill=ui.BOTH, expand=True, pady=(8, 0))
        list_panel = widgets.Frame(middle, width=250)
        list_panel.pack(side=ui.RIGHT, fill=ui.Y, padx=(8, 0))
        list_panel.pack_propagate(False)
        page_tree = widgets.Treeview(list_panel, columns=("pos", "orig", "rot", "status"), show="headings", takefocus=False)
        for column, title, width in (("pos", "Pos.", 40), ("orig", "Original", 60), ("rot", "Drehung", 60), ("status", "Status", 80)):
            page_tree.heading(column, text=title)
            page_tree.column(column, width=width, anchor=ui.CENTER, stretch=column == "status")
        page_tree.pack(fill=ui.BOTH, expand=True)
        page_tree.bind("<<TreeviewSelect>>", self._on_scan_page_selected)
        canvas_bg, canvas_border = self._canvas_theme_tokens()
        canvas = ui.Canvas(middle, bg=canvas_bg, highlightthickness=1, highlightbackground=canvas_border, takefocus=0)
        canvas.pack(side=ui.LEFT, fill=ui.BOTH, expand=True)
        theme_canvas(canvas, self._tooltip_theme_key)
        canvas.bind("<ButtonPress-1>", self._on_scan_canvas_click)
        canvas.bind("<Configure>", lambda _event: self._schedule_scan_render(), add="+")

        self._scan_view = ScanWorkshopView(
            info_var=info_var, pending_var=pending_var, degree_var=degree_var, degree_hint_var=degree_hint_var,
            degree_entry=degree_entry, canvas=canvas, page_tree=page_tree, delete_button=delete_button,
        )

    def _start_scan_workshop(self) -> None:
        """Enter the Scan-Werkstatt for the open exam (fresh session, no pending edits)."""
        if self._current_exam is None or not self._current_exam.students:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur öffnen.")
            return
        self._stop_correction_mode(silent=True)
        self._scan_session = ScanWorkshopSession(self._current_exam.students)
        self._show_view("scan_workshop")
        self._render_scan_workshop()
        self._status_var.set("Scan-Werkstatt aktiv")

    def _new_scan_session_keeping_view(self) -> None:
        """Fresh session after apply/undo/redo, keeping crosshair, person and page position."""
        old = self._scan_session
        session = ScanWorkshopSession(self._current_exam.students)
        if old is not None:
            session.crosshair = old.crosshair
            session.student_index = min(old.student_index, len(session.pdfs) - 1)
            session.position = min(old.position, len(session.current_state.order))
        self._scan_session = session

    def _refresh_scan_workshop_after_reload(self) -> None:
        """Undo/redo changed files and exam data: drop pending edits (they referred to the old pages)."""
        if self._active_view == "scan_workshop" and self._current_exam is not None:
            self._new_scan_session_keeping_view()
            self._render_scan_workshop()

    def _leave_scan_workshop(self) -> None:
        """Back to the exam; with pending edits ask: übernehmen / verwerfen / abbrechen."""
        session = self._scan_session
        if session is not None and session.changed_pdfs():
            choice = choicedialog.askchoice(
                "Scan-Werkstatt verlassen",
                f"Es gibt ungespeicherte Änderungen bei {len(session.changed_pdfs())} Person(en).",
                (
                    ChoiceOption("apply", "Änderungen übernehmen", "PDFs werden geändert, Originale gesichert."),
                    ChoiceOption("discard", "Verwerfen", "Alle offenen Änderungen gehen verloren."),
                ),
            )
            if choice is None or (choice == "apply" and not self._apply_scan_workshop()):
                return
        self._scan_session = None
        self._show_detail_mode()
        self._status_var.set("Scan-Werkstatt verlassen")

    def _discard_scan_workshop(self) -> None:
        """"Verwerfen": drop all pending edits after a confirmation; files are never touched."""
        session = self._scan_session
        if session is None or not session.changed_pdfs():
            return
        if messagebox.askyesno("Verwerfen", f"Alle offenen Änderungen ({len(session.changed_pdfs())} Person(en)) verwerfen?"):
            session.discard()
            self._render_scan_workshop()

    def _apply_scan_workshop(self) -> bool:
        """"Änderungen übernehmen": confirm (with what gets dropped), then run the controller transaction."""
        session = self._scan_session
        if session is None or self._controller is None or not session.changed_pdfs():
            return True
        changed = session.changed_pdfs()
        states = {pdf: session.states[pdf] for pdf in changed}
        try:
            remap = self._controller.plan_scan_workshop_apply(exam=self._current_exam, states=states)
        except Exception as exc:
            messagebox.showerror("Scan-Werkstatt", f"Planung fehlgeschlagen:\n{exc}")
            return False
        names = ", ".join(session.display_names[pdf] for pdf in changed)
        dropped = list(remap.dropped[:_MAX_LISTED]) + ([f"… und {len(remap.dropped) - _MAX_LISTED} weitere"] if len(remap.dropped) > _MAX_LISTED else [])
        text = f"Geändert werden die PDFs von: {names}.\n\nDie Originale werden im Klausurordner unter .korrektor_originale gesichert."
        if dropped:
            text += "\n\nAuf gelöschten Seiten entfällt:\n" + "\n".join(f"• {item}" for item in dropped)
        text += (
            "\n\nSymbole wandern mit ihrer Seite (auch beim Drehen). Wurden Markierungen schon mit "
            "„Alle PDFs überschreiben“ in die PDFs geschrieben, dies danach erneut ausführen.\n\n"
            "Rückgängig ist mit Strg+Z möglich. Übernehmen?"
        )
        if not messagebox.askyesno("Änderungen übernehmen", text):
            return False
        updated = self._controller.apply_scan_workshop_immediate(exam=self._current_exam, states=states, remap=remap)
        if updated is None:
            return False
        self._current_exam = updated
        self._apply_detail_labels(updated)
        self._new_scan_session_keeping_view()
        self._render_scan_workshop()
        return True
