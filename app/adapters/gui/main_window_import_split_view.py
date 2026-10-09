from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import fitz

from app.adapters.gui.import_split_session import ImportSplitSession
from app.adapters.gui.import_split_texts import (
    KEY_HELP_TEXT,
    counter_text,
    duplicate_hint,
    format_range,
    invalid_name_hint,
    name_caption,
    origin_text,
    section_status,
)
from app.core.domain.pdf_split_naming import SplitSection, find_other_sections_with_name, plan_split_files
from app.infrastructure.repositories.file_utils import build_pdf_filename_from_name
from bw_gui.runtime.screen_placement import work_area_for
from bw_gui.theming import theme_canvas
from bw_gui.widgets import Checkbox, ScrollableImagePreview

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets

_SECTION_LIST_WIDTH = 270
_PREVIEW_MIN_WIDTH = 240
_PREVIEW_MIN_HEIGHT = 160
_EMPTY_HINT = " "


@dataclass
class ImportSplitView:
    """Widget references of the open wizard window (one per session, dropped on session end).

    ``suppress_name_trace`` guards programmatic writes to ``name_var`` (V7):
    only typing may write a name into the session.
    """

    popup: Any
    preview: ScrollableImagePreview
    info_var: Any
    count_var: Any
    caption_var: Any
    name_var: Any
    hint_var: Any
    boundary_var: Any
    boundary_check: Any
    name_entry: Any
    section_tree: Any
    bars: list[Any]
    controls_by_row: list[list[Any]]
    binder: Any = None
    suppress_name_trace: bool = False
    tree_start_by_iid: dict[str, int] = field(default_factory=dict)
    bars_reqheight: int = 0


class MainWindowImportSplitViewMixin:
    """Layout, rendering and refresh of the PDF import wizard.

    Layout contract (user requirement "Leisten immer sichtbar"):

    1. Pack order gives the bars height priority: header ``TOP``; actions,
       name area and navigation ``BOTTOM`` - all packed *before* the middle
       part; the middle part (preview + section list) last with ``expand``.
       Shrinking the window therefore only shrinks the preview.
    2. Every label in the bars is single-line (no ``wraplength``), so bar
       heights do not depend on the window width; the hint line is always
       packed (a blank when empty) so a hint never changes the height.
    3. Within each row the controls are packed first and pure info texts
       last with ``fill=X``: a narrow window clips info text, never a control.
    4. ``minsize`` = controls' requested widths / bars' requested heights
       plus a minimum preview; recomputed whenever the bars' requested
       height changes (e.g. after a theme or font change).

    The popup itself is a plain ``ui.Toplevel`` without an outer scroll
    layer: only the preview scrolls, via bw-gui's `ScrollableImagePreview`
    (see bw-gui ``docs/SCROLLABILITY_CONTRACT.md``).
    """

    def _build_import_split_view(self, session: ImportSplitSession) -> None:
        """Create the wizard window for ``session`` and store it as ``self._import_split_view``."""
        popup = ui.Toplevel(self.root)
        popup.title("Neue Klausur: PDF aufteilen" if session.creates_exam else "PDF importieren & aufteilen")
        popup.transient(self.root)
        self._register_popup_window(popup)

        header = widgets.Frame(popup, padding=(10, 10, 10, 6))
        header.pack(side=ui.TOP, fill=ui.X)
        info_var = ui.StringVar(value="")
        widgets.Label(header, textvariable=info_var, style="Muted.TLabel", anchor=ui.W).pack(side=ui.LEFT, fill=ui.X)

        actions = widgets.Frame(popup, padding=(10, 4, 10, 10))
        actions.pack(side=ui.BOTTOM, fill=ui.X)
        split_button = widgets.Button(
            actions,
            text="Aufteilen && Klausur anlegen…" if session.creates_exam else "Aufteilen…",
            style="PrimaryAction.TButton",
            command=self._run_import_split,
            takefocus=False,
        )
        split_button.pack(side=ui.LEFT)
        close_button = widgets.Button(
            actions, text="Schließen", style="SecondaryAction.TButton", command=self._request_close_import_split, takefocus=False
        )
        close_button.pack(side=ui.RIGHT)
        widgets.Label(actions, text=KEY_HELP_TEXT, style="Muted.TLabel", anchor=ui.CENTER).pack(
            side=ui.LEFT, fill=ui.X, expand=True, padx=8
        )

        name_area = widgets.Frame(popup, padding=(10, 2, 10, 0))
        name_area.pack(side=ui.BOTTOM, fill=ui.X)
        name_row = widgets.Frame(name_area)
        name_row.pack(fill=ui.X)
        caption_var = ui.StringVar(value="")
        caption = widgets.Label(name_row, textvariable=caption_var, width=26, anchor=ui.W)
        caption.pack(side=ui.LEFT)
        name_var = ui.StringVar(value="")
        name_entry = widgets.Entry(name_row, textvariable=name_var, width=32)
        name_entry.pack(side=ui.LEFT, fill=ui.X, expand=True)
        hint_var = ui.StringVar(value=_EMPTY_HINT)
        widgets.Label(name_area, textvariable=hint_var, style="Status.TLabel", anchor=ui.W).pack(fill=ui.X)

        nav = widgets.Frame(popup, padding=(10, 6, 10, 2))
        nav.pack(side=ui.BOTTOM, fill=ui.X)
        prev_button = widgets.Button(
            nav, text="◀", style="SecondaryAction.TButton", takefocus=False,
            command=lambda: self._step_import_split_page(-1),
        )
        prev_button.pack(side=ui.LEFT)
        self._attach_hover_help(prev_button, label="Vorherige Seite", shortcut="Links")
        next_button = widgets.Button(
            nav, text="▶", style="SecondaryAction.TButton", takefocus=False,
            command=lambda: self._step_import_split_page(1),
        )
        next_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(next_button, label="Nächste Seite", shortcut="Rechts")
        boundary_var = ui.BooleanVar(value=True)
        # Checkbox: staged selection only - boundaries take effect on "Aufteilen".
        boundary_check = Checkbox(
            nav, text="Hier beginnt neue Abgabe", variable=boundary_var,
            on_select=self._on_import_split_boundary_selected,
        )
        boundary_check.configure(takefocus=False)
        boundary_check.pack(side=ui.LEFT, padx=(16, 0))
        self._attach_hover_help(boundary_check, label="Hier aufteilen / Aufteilung zurücknehmen", shortcut="Enter / Shift+Enter")
        count_var = ui.StringVar(value="")
        widgets.Label(nav, textvariable=count_var, style="Status.TLabel", anchor=ui.W).pack(
            side=ui.LEFT, fill=ui.X, expand=True, padx=(16, 0)
        )

        middle = widgets.Frame(popup, padding=(10, 0, 10, 4))
        middle.pack(side=ui.TOP, fill=ui.BOTH, expand=True)
        section_tree = self._build_import_split_section_list(middle)
        preview = ScrollableImagePreview(middle, render=self._render_import_split_page_image)
        preview.canvas.configure(takefocus=0)
        preview.pack(side=ui.LEFT, fill=ui.BOTH, expand=True)
        theme_canvas(preview.canvas, self._tooltip_theme_key)

        view = ImportSplitView(
            popup=popup, preview=preview, info_var=info_var, count_var=count_var, caption_var=caption_var,
            name_var=name_var, hint_var=hint_var, boundary_var=boundary_var, boundary_check=boundary_check,
            name_entry=name_entry, section_tree=section_tree, bars=[header, nav, name_area, actions],
            controls_by_row=[[prev_button, next_button, boundary_check], [caption, name_entry], [split_button, close_button]],
        )
        self._import_split_view = view
        popup.protocol("WM_DELETE_WINDOW", self._request_close_import_split)
        popup.bind("<Destroy>", self._on_import_split_popup_destroyed, add="+")
        for bar in view.bars:
            bar.bind("<Configure>", lambda _event: self._update_import_split_minsize(), add="+")
        self._install_import_split_input(view)
        self._update_import_split_minsize(initial=True)
        self._focus_import_split_name_field()

    def _build_import_split_section_list(self, parent):
        """Right-hand list of sections (fixed width, own scrollbar); a click jumps to the section."""
        panel = widgets.Frame(parent, width=_SECTION_LIST_WIDTH)
        panel.pack(side=ui.RIGHT, fill=ui.Y, padx=(8, 0))
        panel.pack_propagate(False)
        tree = widgets.Treeview(panel, columns=("pages", "name", "status"), show="headings", takefocus=False)
        tree.heading("pages", text="Seiten")
        tree.heading("name", text="Name")
        tree.heading("status", text="Status")
        tree.column("pages", width=60, anchor=ui.CENTER, stretch=False)
        tree.column("name", width=110, anchor=ui.W)
        tree.column("status", width=90, anchor=ui.W, stretch=False)
        scrollbar = widgets.Scrollbar(panel, orient=ui.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=ui.RIGHT, fill=ui.Y)
        tree.pack(side=ui.LEFT, fill=ui.BOTH, expand=True)
        tree.bind("<<TreeviewSelect>>", self._on_import_split_section_selected)
        return tree

    def _render_import_split_page_image(self, width: int):
        """`ScrollableImagePreview` render callback: the current page scaled to ``width`` pixels.

        The only 0-based page index of the wizard lives here (``load_page``).
        Errors are shown in the header instead of escaping into Tk.
        """
        session = self._import_split_session
        view = self._import_split_view
        if session is None or session.closed:
            return None
        try:
            page = session.document.load_page(session.current_page - 1)
            scale = width / max(page.rect.width, 1.0)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            return ui.PhotoImage(data=pix.tobytes("ppm"), format="ppm")
        except Exception as exc:
            if view is not None:
                view.info_var.set(f"Seite {session.current_page} konnte nicht dargestellt werden: {exc}")
            return None

    def _refresh_import_split_view(self, *, page_changed: bool = False, reload_name: bool = False) -> None:
        """Bring every widget in line with the session.

        Args:
            page_changed: The current page changed: reload the name field,
                re-render the preview and scroll it to the top.
            reload_name: Reload the name field from the session without
                touching the preview (after Enter / Shift+Enter). Reloading
                is the only programmatic write to the field (V7) - plain
                refreshes while typing never overwrite what is being typed.
        """
        session = self._import_split_session
        view = self._import_split_view
        if session is None or view is None:
            return
        sections = session.sections()
        plan = plan_split_files(sections)
        current = session.section_for_page(session.current_page)
        view.info_var.set(self._import_split_origin_text(session))
        view.caption_var.set(name_caption(current))
        is_boundary = session.current_page == current.start_page
        view.boundary_var.set(is_boundary)
        view.boundary_check.configure(state="disabled" if session.current_page == 1 else "normal")
        view.count_var.set(counter_text(len(sections), plan))
        if page_changed or reload_name:
            self._show_import_split_name(session.name_for_page(session.current_page))
        self._update_import_split_hint(sections, current)
        self._refresh_import_split_section_list(sections, plan, current)
        if page_changed:
            view.preview.refresh(scroll_to_top=True)

    def _import_split_origin_text(self, session: ImportSplitSession) -> str:
        page = session.current_page
        return origin_text(
            page, session.page_count, session.source_span_for_page(page), multiple_sources=len(session.source_spans) > 1
        )

    def _update_import_split_hint(self, sections: list[SplitSection], current: SplitSection) -> None:
        """Live hint under the name field: duplicate name or invalid filename (wish 3b)."""
        view = self._import_split_view
        name = current.name
        others = find_other_sections_with_name(sections, name, exclude_start_page=current.start_page)
        if others:
            view.hint_var.set(duplicate_hint(others))
        elif name and build_pdf_filename_from_name(name) is None:
            view.hint_var.set(invalid_name_hint())
        else:
            view.hint_var.set(_EMPTY_HINT)

    def _refresh_import_split_section_list(self, sections: list[SplitSection], plan, current: SplitSection) -> None:
        """Rebuild the section list and select the current section (selecting it is a no-op jump)."""
        view = self._import_split_view
        tree = view.section_tree
        tree.delete(*tree.get_children())
        view.tree_start_by_iid = {}
        current_iid = None
        for section in sections:
            iid = tree.insert(
                "", ui.END,
                values=(format_range(section.start_page, section.end_page), section.name or "—", section_status(section, plan)),
            )
            view.tree_start_by_iid[iid] = section.start_page
            if section.start_page == current.start_page:
                current_iid = iid
        if current_iid is not None:
            tree.selection_set(current_iid)
            tree.see(current_iid)

    def _update_import_split_minsize(self, *, initial: bool = False) -> None:
        """Keep every control visible: minsize from the bars' requested sizes plus a minimum preview."""
        view = self._import_split_view
        if view is None:
            return
        popup = view.popup
        if not self._import_split_window_alive(popup):
            return
        popup.update_idletasks()
        bars = [bar for bar in view.bars if int(bar.winfo_exists())]
        bars_height = sum(int(bar.winfo_reqheight()) for bar in bars)
        if not initial and bars_height == view.bars_reqheight:
            return
        view.bars_reqheight = bars_height
        controls_width = max(
            sum(int(widget.winfo_reqwidth()) + 16 for widget in row if int(widget.winfo_exists()))
            for row in view.controls_by_row
        )
        min_width = max(controls_width + 40, _SECTION_LIST_WIDTH + _PREVIEW_MIN_WIDTH + 40)
        min_height = bars_height + _PREVIEW_MIN_HEIGHT + 20
        popup.minsize(min_width, min_height)
        if initial:
            # Cap against the work area of the popup's own monitor (bw-gui screen
            # placement), not winfo_screen* (primary monitor only on Windows).
            work = work_area_for(popup)
            width = min(max(min_width, 1100), work.width - 80)
            height = min(max(min_height, 860), work.height - 80)
            popup.geometry(f"{width}x{height}")

    def _apply_import_split_theme(self) -> None:
        """Re-theme the preview canvas after a theme switch (called from `_apply_canvas_theme_tokens`)."""
        view = self._import_split_view
        if view is not None:
            theme_canvas(view.preview.canvas, self._tooltip_theme_key)
