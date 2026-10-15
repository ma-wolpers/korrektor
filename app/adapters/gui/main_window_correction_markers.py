from __future__ import annotations

from app.adapters.gui.main_window_constants import (
    CORRECTION_DEFAULT_COLOR_NAME,
    CORRECTION_DEFAULT_FONT_SIZE_PT,
    CORRECTION_MARKER_COLORS,
    CORRECTION_MARKER_TOOLS,
)
from app.core.domain.annotation_move import move_annotations
from app.core.domain.annotation_sync import normalize_rotation_deg

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.contracts import KeyModifiers
from bw_gui.contracts.events import EventResult
from bw_gui.runtime import bind_drag, bind_wheel, ui, widgets
from bw_gui.widgets import ScrollableFrame


class MainWindowCorrectionMarkersMixin:
    def _build_correction_view_canvas(self) -> None:
        correction_split = widgets.PanedWindow(self._correction_view, orient=ui.HORIZONTAL)
        correction_split.pack(fill=ui.BOTH, expand=True)

        correction_canvas_panel = widgets.Frame(correction_split, style="Surface.TFrame", padding=(0, 0, 8, 0))
        # ScrollableFrame (bw-gui scroll SSOT, see bw-gui/docs/SCROLLABILITY_CONTRACT.md):
        # this pane has grown to six stacked blocks (Punkte/Kommentar, Fertig-
        # Checkboxen, Markierungswerkzeuge, Transform/Sync, Supersymbol+
        # Superposition, Speichern/Navigation) - at a small window height the
        # lower blocks became unreachable without manually resizing the
        # window. It is a real ttk.Frame, so `correction_split.add(...)`
        # below works exactly as it did for the plain Frame it replaces;
        # every builder method below now targets `.content` instead.
        self._correction_form_panel = ScrollableFrame(correction_split, style="Surface.TFrame", padding=(8, 0, 0, 0))
        correction_split.add(correction_canvas_panel, weight=3)
        correction_split.add(self._correction_form_panel, weight=2)

        correction_canvas_bg, correction_canvas_border = self._canvas_theme_tokens()
        self._correction_canvas = ui.Canvas(
            correction_canvas_panel,
            width=520,
            height=360,
            bg=correction_canvas_bg,
            highlightthickness=1,
            highlightbackground=correction_canvas_border,
        )
        self._correction_canvas.pack(fill=ui.BOTH, expand=True)
        bind_wheel(self._correction_canvas, self._on_correction_mousewheel)
        # Press = select/place (threshold 0), move = live drag, release = commit. A drag
        # aborted by focus loss commits like a release, so the live-moved position and
        # the persisted state never diverge.
        bind_drag(
            self._correction_canvas,
            on_start=self._on_correction_canvas_press,
            on_move=self._on_correction_canvas_drag,
            on_end=self._on_correction_canvas_release,
            on_cancel=lambda _reason: self._on_correction_canvas_release(None),
        )

    def _build_correction_view_form_markers(self) -> None:
        marker_controls = widgets.Frame(self._correction_form_panel.content, style="Surface.TFrame")
        marker_controls.pack(fill=ui.X, pady=(10, 0))

        widgets.Label(marker_controls, text="Markierungen", style="Muted.TLabel").pack(anchor=ui.W)

        color_row = widgets.Frame(marker_controls, style="Surface.TFrame")
        color_row.pack(fill=ui.X, pady=(4, 0))
        widgets.Label(color_row, text="Farbe", style="Muted.TLabel").pack(side=ui.LEFT)
        color_combo = widgets.Combobox(
            color_row,
            textvariable=self._correction_marker_color_name_var,
            values=tuple(CORRECTION_MARKER_COLORS.keys()),
            state="readonly",
            width=12,
        )
        color_combo.pack(side=ui.LEFT, padx=(8, 0))
        color_combo.bind("<<ComboboxSelected>>", self._on_correction_marker_color_changed)

        marker_row = widgets.Frame(marker_controls, style="Surface.TFrame")
        marker_row.pack(fill=ui.X, pady=(6, 0))
        for tool_key, glyph, label in CORRECTION_MARKER_TOOLS:
            marker_button = widgets.Button(
                marker_row,
                text=glyph,
                style="SecondaryAction.TButton",
                width=3,
                command=lambda value=tool_key: self._set_correction_marker_tool(value),
            )
            marker_button.pack(side=ui.LEFT, padx=(0, 4))
            self._attach_hover_help(marker_button, label=f"Markierung: {label}")

        self._correction_marker_controls_frame = marker_controls

    @staticmethod
    def _marker_tool_lookup(tool_key: str) -> tuple[str, str] | None:
        for key, glyph, label in CORRECTION_MARKER_TOOLS:
            if key == tool_key:
                return glyph, label
        return None

    def _set_correction_marker_tool(self, tool_key: str) -> None:
        lookup = self._marker_tool_lookup(tool_key)
        if lookup is None:
            return
        _glyph, label = lookup
        self._correction_marker_tool_key = tool_key
        self._correction_marker_info_var.set(f"Markierung: {label}")

    def _on_correction_marker_color_changed(self, _event: ui.Event[ui.Misc]) -> None:
        color_name = self._correction_marker_color_name_var.get()
        if color_name not in CORRECTION_MARKER_COLORS:
            color_name = CORRECTION_DEFAULT_COLOR_NAME
            self._correction_marker_color_name_var.set(color_name)

        if self._current_exam is None or self._controller is None:
            return
        annotation = self._selected_correction_annotation()
        if annotation is None:
            return

        color_hex = CORRECTION_MARKER_COLORS.get(color_name, CORRECTION_MARKER_COLORS[CORRECTION_DEFAULT_COLOR_NAME])
        updated = self._controller.recolor_annotation_immediate(
            exam=self._current_exam, annotation_id=annotation.annotation_id, color_hex=color_hex
        )
        if updated is None:
            return
        self._current_exam = updated
        self._render_correction_annotations()
        self._status_var.set("Markierungsfarbe aktualisiert")

    @staticmethod
    def _normalize_marker_color_hex(raw_color: object) -> str:
        value = str(raw_color or "").strip().lower()
        if len(value) == 7 and value.startswith("#"):
            return value
        return CORRECTION_MARKER_COLORS[CORRECTION_DEFAULT_COLOR_NAME]

    @staticmethod
    def _normalize_marker_font_size(raw_size: object) -> float:
        try:
            size = float(raw_size)
        except (TypeError, ValueError):
            size = CORRECTION_DEFAULT_FONT_SIZE_PT
        return max(8.0, min(96.0, size))

    @classmethod
    def _marker_color_name_for_hex(cls, color_hex: str) -> str:
        normalized = cls._normalize_marker_color_hex(color_hex)
        for name, hex_value in CORRECTION_MARKER_COLORS.items():
            if hex_value.lower() == normalized:
                return name
        return CORRECTION_DEFAULT_COLOR_NAME

    @staticmethod
    def _event_has_alt_modifier(event) -> bool:
        """Alt held when the drag started (bw-gui modifier contract; unknown state -> no).

        Formerly a raw ``event.state`` mask that also treated 0x0008 as Alt - on win32
        that bit is NumLock, so with NumLock on every drag detached the mark from its
        sync group.
        """
        modifiers = event.start_modifiers
        return isinstance(modifiers, KeyModifiers) and modifiers.alt

    def _current_marker_color_hex(self) -> str:
        selected = self._correction_marker_color_name_var.get()
        if selected in CORRECTION_MARKER_COLORS:
            return CORRECTION_MARKER_COLORS[selected]
        return self._default_annotation_color_hex

    @staticmethod
    def _hex_to_rgb_fraction(color_hex: str) -> tuple[float, float, float]:
        raw = color_hex.strip().lstrip("#")
        if len(raw) != 6:
            return (0.0, 0.0, 0.0)
        try:
            red = int(raw[0:2], 16) / 255.0
            green = int(raw[2:4], 16) / 255.0
            blue = int(raw[4:6], 16) / 255.0
        except ValueError:
            return (0.0, 0.0, 0.0)
        return red, green, blue

    @staticmethod
    def _normalize_rotation_deg(raw_deg: float) -> float:
        return normalize_rotation_deg(raw_deg)

    def _on_correction_canvas_press(self, event):
        """Handle a press on the correction canvas (``DragEvent``): Supersymbol apply, or normal select/place."""
        if not self._correction_mode_active:
            return None
        self._correction_canvas.focus_set()
        canvas_x = float(self._correction_canvas.canvasx(event.x))
        canvas_y = float(self._correction_canvas.canvasy(event.y))

        if self._supersymbol_filter_active:
            self._apply_supersymbol_at_canvas_position(canvas_x, canvas_y)
            return EventResult.HANDLED

        if self._superposition_mode is not None:
            self._apply_superposition_at_canvas_position(canvas_x, canvas_y)
            return EventResult.HANDLED

        self._correction_drag_alt_override = False
        item_under_cursor = self._correction_canvas.find_withtag("current")
        if item_under_cursor:
            item_id = item_under_cursor[0]
            annotation_id = next(
                (key for key, value in self._correction_annotation_items.items() if value == item_id),
                None,
            )
            if annotation_id is not None:
                self._begin_correction_annotation_drag(
                    annotation_id, canvas_x, canvas_y, alt_override=self._event_has_alt_modifier(event)
                )
                return EventResult.HANDLED

        lookup = self._marker_tool_lookup(self._correction_marker_tool_key)
        if lookup is None:
            return EventResult.HANDLED
        glyph, label = lookup
        if self._place_annotation_from_canvas(
            canvas_x=canvas_x,
            canvas_y=canvas_y,
            annotation_type="symbol",
            content=glyph,
        ):
            self._status_var.set(f"Markierung gesetzt: {label}")
        return EventResult.HANDLED

    def _begin_correction_annotation_drag(self, annotation_id: str, canvas_x: float, canvas_y: float, *, alt_override: bool) -> None:
        """Select the mark ``annotation_id`` grabbed at canvas ``(canvas_x, canvas_y)`` and remember the drag start.

        Called by `_on_correction_canvas_press` for the mark under the
        cursor (tests call it directly - the Tk "current" item needs a real
        pointer). The drag starts in the mark's own segment; it switches
        region while dragged over another crop (`_on_correction_canvas_drag`).
        """
        self._correction_selected_annotation_id = annotation_id
        annotation = self._annotation_by_id(annotation_id)
        segment = self._segment_for_annotation(annotation) if annotation is not None else None
        pdf_pos = self._canvas_to_pdf_coords(canvas_x, canvas_y, segment)
        if annotation is not None and pdf_pos is not None and self._current_exam is not None:
            self._correction_drag_segment = segment
            self._correction_drag_annotation_id = annotation_id
            self._correction_drag_offset_pdf = (annotation.x - pdf_pos[0], annotation.y - pdf_pos[1])
            self._correction_drag_alt_override = alt_override
            # Snapshot taken here (drag start), before any position
            # mutation - see commit_annotation_move_immediate's
            # docstring for why this must not be recomputed at
            # release time (that was the Meilenstein-0.2 bug in
            # save_exam_immediate: a post-mutation "before" snapshot
            # makes undo a no-op).
            self._correction_drag_before_payload = self._current_exam.to_dict()
            self._correction_drag_moved = False
        self._render_correction_annotations()

    def _on_correction_canvas_drag(self, event):
        """Live-move the dragged mark (or its sync group); it stays inside a region and follows the cursor's region.

        The point is always clamped into the crop of its region, and over
        another region's crop the mark (or its whole group) is re-homed
        there - see `_drag_target_segment` for which switches are allowed and
        `move_annotations` for the rule. When the segment changes, the grab
        offset is rescaled so the mark keeps its on-screen distance to the
        cursor. Persisted once on release (`_on_correction_canvas_release`).
        """
        if not self._correction_mode_active or self._current_exam is None:
            return None
        if self._correction_drag_annotation_id is None or self._correction_drag_offset_pdf is None:
            return None
        annotation = self._annotation_by_id(self._correction_drag_annotation_id)
        if annotation is None or self._correction_drag_segment is None:
            return EventResult.HANDLED

        canvas_x = float(self._correction_canvas.canvasx(event.x))
        canvas_y = float(self._correction_canvas.canvasy(event.y))
        is_synced = bool(annotation.sync_group_id)
        moves_whole_group = is_synced and not self._correction_drag_alt_override and not annotation.position_detached
        previous_segment = self._correction_drag_segment
        segment = self._drag_target_segment(canvas_y, moves_whole_group=moves_whole_group, is_synced=is_synced)
        if segment != previous_segment:
            factor = previous_segment.scale / segment.scale
            self._correction_drag_offset_pdf = (self._correction_drag_offset_pdf[0] * factor, self._correction_drag_offset_pdf[1] * factor)
            self._correction_drag_segment = segment
        pdf_pos = self._canvas_to_pdf_coords(canvas_x, canvas_y, segment)
        if pdf_pos is None:
            return EventResult.HANDLED

        followers = (
            [item for item in self._sync_group_members(annotation, include_detached=False) if item is not annotation]
            if moves_whole_group
            else []
        )
        moved = move_annotations(
            annotation,
            followers,
            pdf_pos[0] + self._correction_drag_offset_pdf[0],
            pdf_pos[1] + self._correction_drag_offset_pdf[1],
            self._move_target_for_segment(segment),
            self._selected_correction_task()[0] or "",
        )
        if not moved:
            return EventResult.HANDLED
        if is_synced and self._correction_drag_alt_override:
            annotation.position_detached = True
        self._correction_drag_moved = True
        self._render_correction_annotations()
        return EventResult.HANDLED

    def _on_correction_canvas_release(self, _event):
        """End a drag gesture, committing at most one `HistoryAction` for the whole gesture.

        The live position mutation during `_on_correction_canvas_drag` was
        never persisted; this is the single point (Meilenstein 0.3) where a
        moved annotation - or its whole sync group, if it moved together -
        is saved and pushed onto the undo history, using the snapshot taken
        at drag start (`_correction_drag_before_payload`). A drag that never
        actually changed a position (e.g. a plain click-to-select) commits
        nothing.
        """
        if not self._correction_mode_active:
            return None
        moved = self._correction_drag_moved and self._current_exam is not None and self._controller is not None
        before_payload = self._correction_drag_before_payload
        self._correction_drag_annotation_id = None
        self._correction_drag_offset_pdf = None
        self._correction_drag_segment = None
        self._correction_drag_alt_override = False
        self._correction_drag_before_payload = None
        self._correction_drag_moved = False
        if moved and before_payload is not None:
            updated = self._controller.commit_annotation_move_immediate(
                exam=self._current_exam, before_payload=before_payload
            )
            if updated is not None:
                self._current_exam = updated
                self._render_correction_annotations()
        return EventResult.HANDLED
