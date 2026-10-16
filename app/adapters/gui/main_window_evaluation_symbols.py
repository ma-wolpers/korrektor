"""Evaluation symbols view: every symbol used in at least one current submission.

One row per ``SymbolUsage`` (``used_symbols_for_exam``; palette order, older symbols last):
icon in the default marker colour, name, explanation, "n× in m Abgaben" and the tasks.
Older symbols that are no longer in the palette (e.g. △) appear with the legacy
explanation. Counting rules live in ``app/core/domain/symbol_usage.py``.
"""

from __future__ import annotations

import base64

from app.adapters.gui.main_window_correction_marker_palette import palette_icon_png

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets


class MainWindowEvaluationSymbolsMixin:
    """Symbols view of the evaluation window."""

    def _build_evaluation_symbols(self, parent: widgets.Frame) -> None:
        """Back button, intro text and the row container."""
        nav = widgets.Frame(parent)
        nav.pack(fill=ui.X)
        widgets.Button(nav, text="← Übersicht", style="SecondaryAction.TButton",
                       command=lambda: self._show_evaluation_view("overview")).pack(side=ui.LEFT)
        self._evaluation_legend_button = widgets.Button(
            nav, text="Symbol-Legende exportieren…", style="SecondaryAction.TButton", command=self._export_evaluation_legend
        )
        self._evaluation_legend_button.pack(side=ui.LEFT, padx=(12, 0))
        self._attach_hover_help(self._evaluation_legend_button,
                                label="Legende für Schüler:innen als PDF oder PNG: Symbol, Name und Erklärung (ohne Häufigkeiten)")
        widgets.Label(parent, style="Muted.TLabel", justify=ui.LEFT,
                      text="Alle Symbole, die in mindestens einer Abgabe dieser Klausur vorkommen.").pack(anchor=ui.W, pady=(10, 0))
        self._evaluation_symbols_rows = widgets.Frame(parent)
        self._evaluation_symbols_rows.pack(fill=ui.X, pady=(8, 0))
        self._evaluation_symbol_usages = []

    def _fill_evaluation_symbols(self) -> None:
        """Rebuild the rows from the current exam."""
        if self._controller is None or self._current_exam is None:
            return
        frame = self._evaluation_symbols_rows
        for child in frame.winfo_children():
            child.destroy()
        usages = self._controller.used_symbols_for_exam(exam=self._current_exam)
        self._evaluation_symbol_usages = usages
        self._evaluation_legend_button.configure(state="normal" if usages else "disabled")
        for key in [key for key in self._evaluation_photos if key.startswith("symbol_")]:
            del self._evaluation_photos[key]
        if not usages:
            widgets.Label(frame, text="In dieser Klausur wurden noch keine Symbole gesetzt.", style="Muted.TLabel").pack(anchor=ui.W)
            return
        for index, usage in enumerate(usages):
            png = palette_icon_png(usage.content, self._default_annotation_color_hex)
            photo = ui.PhotoImage(data=base64.b64encode(png).decode("ascii"), format="png")
            self._evaluation_photos[f"symbol_{index}"] = photo
            # Fixed icon column, so every text starts at the same x whatever the icon's width.
            row = widgets.Frame(frame)
            row.pack(fill=ui.X, pady=(0, 8))
            row.columnconfigure(0, minsize=44)
            widgets.Label(row, image=photo).grid(row=0, column=0, rowspan=3, sticky=ui.NW)
            tasks = ", ".join(usage.task_codes) if usage.task_codes else "ohne Aufgabe"
            for line, (text, style) in enumerate((
                (usage.label, "Status.TLabel"),
                (usage.description, "TLabel"),
                (f"{usage.count}× in {usage.submission_count} Abgabe(n) · Aufgaben: {tasks}", "Muted.TLabel"),
            )):
                widgets.Label(row, text=text, style=style, justify=ui.LEFT).grid(row=line, column=1, sticky=ui.W)

    def _export_evaluation_legend(self) -> None:
        """Export the symbol legend (file dialog and writing in the controller)."""
        if self._controller is not None and self._current_exam is not None:
            self._controller.export_symbol_legend_for_exam(exam=self._current_exam, color_hex=self._default_annotation_color_hex)
