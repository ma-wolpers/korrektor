"""Klausur-Zuordnung of the PDF import wizard: the Klausur bar, its keys and its name prompts.

Rules live Tk-free in `pdf_split_groups` / `ImportSplitSession`; this mixin
only binds keys, asks for names and shows the state.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Any

from app.adapters.gui.dialog_services import simpledialog
from app.adapters.gui.import_split_texts import group_label, group_name_problem_text, group_overview_text
from app.adapters.gui.ui_intents import UiIntent
from app.core.domain.pdf_split_groups import MAX_GROUPS, default_group_name, section_counts
from app.core.domain.pdf_split_naming import SplitSection
from bw_gui.contracts.key_spec import KeySpec
from bw_gui.shortcuts import humanize_shortcut

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets

_k = KeySpec.parse

# Klausur keys, shared by the binding table and the hover help of the bar (one source).
GROUP_KEYS = tuple(_k(f"Ctrl+{number}") for number in range(1, MAX_GROUPS + 1))
GROUP_PREV_KEY = _k("Ctrl+Up")
GROUP_NEXT_KEY = _k("Ctrl+Down")
GROUP_RENAME_KEY = _k("F2")
_EMPTY = " "


@dataclass
class ImportSplitGroupBar:
    """Widgets of the Klausur bar (one row between page navigation and name field)."""

    frame: Any
    current_var: Any
    overview_var: Any
    controls: list[Any]


class MainWindowImportSplitGroupsMixin:
    """Keys and bar of the Klausur-Zuordnung (user decisions: both key schemes, "Wechsel gilt ab hier").

    Keyboard contract (bound like the other wizard keys, while the name
    field has the focus):

    - Ctrl+1 … Ctrl+9: the current Abgabe and all following ones (up to the
      next switch) belong to Klausur N. N = next free number first asks for
      the name of a new Klausur; a number beyond that only shows a hint.
    - Ctrl+Up / Ctrl+Down: the previous / next Klausur, same "ab hier" rule;
      Down after the last Klausur asks for a new one.
    - F2: rename the Klausur of the current Abgabe (= its folder name).

    Name prompts validate inline via bw-gui's ``askstring(validate=...)``
    (invalid folder name, duplicate, more than nine).
    """

    def _import_split_group_key_rows(self) -> list[tuple]:
        """Rows for ``local_keys.bind_popup_table`` (appended to the wizard table)."""
        rows = [
            (key, f"group_{number}", UiIntent.IMPORT_SPLIT_GROUP_ASSIGN, partial(self._choose_import_split_group, number - 1))
            for number, key in enumerate(GROUP_KEYS, start=1)
        ]
        rows += [
            (GROUP_PREV_KEY, "group_prev", UiIntent.IMPORT_SPLIT_GROUP_PREV, lambda: self._step_import_split_group(-1)),
            (GROUP_NEXT_KEY, "group_next", UiIntent.IMPORT_SPLIT_GROUP_NEXT, lambda: self._step_import_split_group(1)),
            (GROUP_RENAME_KEY, "group_rename", UiIntent.IMPORT_SPLIT_GROUP_RENAME, self._rename_import_split_group),
        ]
        return rows

    def _build_import_split_group_bar(self, popup) -> ImportSplitGroupBar:
        """Create the (not yet packed) Klausur bar: ◀ current ▶, rename, overview of all Klausuren."""
        frame = widgets.Frame(popup, padding=(10, 2, 10, 2))
        caption = widgets.Label(frame, text="Klausur:", anchor=ui.W)
        caption.pack(side=ui.LEFT)
        prev_button = widgets.Button(
            frame, text="◀", style="SecondaryAction.TButton", takefocus=False,
            command=lambda: self._step_import_split_group(-1),
        )
        prev_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(prev_button, label="Vorherige Klausur ab dieser Abgabe", shortcut=GROUP_PREV_KEY)
        current_var = ui.StringVar(value="")
        current = widgets.Label(frame, textvariable=current_var, style="Status.TLabel", width=20, anchor=ui.CENTER)
        current.pack(side=ui.LEFT, padx=4)
        first, last = humanize_shortcut(GROUP_KEYS[0]), humanize_shortcut(GROUP_KEYS[-1])
        self._attach_hover_help(current, label=f"Ab dieser Abgabe direkt Klausur 1 bis {MAX_GROUPS} zuordnen: {first} … {last}")
        next_button = widgets.Button(
            frame, text="▶", style="SecondaryAction.TButton", takefocus=False,
            command=lambda: self._step_import_split_group(1),
        )
        next_button.pack(side=ui.LEFT)
        self._attach_hover_help(
            next_button, label="Nächste Klausur ab dieser Abgabe (nach der letzten: neue Klausur)", shortcut=GROUP_NEXT_KEY
        )
        rename_button = widgets.Button(
            frame, text="Umbenennen…", style="SecondaryAction.TButton", takefocus=False,
            command=self._rename_import_split_group,
        )
        rename_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(rename_button, label="Klausur umbenennen (= Ordnername)", shortcut=GROUP_RENAME_KEY)
        overview_var = ui.StringVar(value=_EMPTY)
        widgets.Label(frame, textvariable=overview_var, style="Muted.TLabel", anchor=ui.W).pack(
            side=ui.LEFT, fill=ui.X, expand=True, padx=(16, 0)
        )
        controls = [caption, prev_button, current, next_button, rename_button]
        return ImportSplitGroupBar(frame=frame, current_var=current_var, overview_var=overview_var, controls=controls)

    def _refresh_import_split_group_bar(self, sections: list[SplitSection]) -> None:
        """Show the current Abgabe's Klausur; the overview only once there is more than one Klausur."""
        session = self._import_split_session
        bar = self._import_split_view.group_bar
        index = session.group_index_for_page(session.current_page)
        names = session.group_names
        bar.current_var.set(group_label(index, names[index] if index < len(names) else default_group_name(index)))
        if len(names) > 1:
            counts = section_counts(sections, session.group_switches, len(names))
            bar.overview_var.set(group_overview_text(names, counts))
        else:
            bar.overview_var.set(_EMPTY)

    def _choose_import_split_group(self, index: int) -> None:
        """Ctrl+digit (and the target of Ctrl+Up/Down): assign Klausur ``index`` from the current Abgabe on."""
        session = self._import_split_session
        if session is None:
            return
        count = len(session.group_names)
        if index == count:
            index = self._ask_new_import_split_group()
        elif index > count:
            self._flash_import_split_info(f"Klausur {index + 1} gibt es noch nicht – die nächste neue ist {count + 1}.")
            index = None
        if index is not None and self._import_split_session is session:
            session.assign_group_for_page(session.current_page, index)
            self._refresh_import_split_view()
        self._focus_import_split_name_field()

    def _step_import_split_group(self, delta: int) -> None:
        """Ctrl+Up/Down and ◀/▶ of the bar: previous / next Klausur (past the last: a new one)."""
        session = self._import_split_session
        if session is None:
            return
        target = session.neighbor_group_index(session.current_page, delta)
        if target is None:
            self._flash_import_split_info("Das ist bereits Klausur 1.")
            self._focus_import_split_name_field()
            return
        self._choose_import_split_group(target)

    def _rename_import_split_group(self) -> None:
        """F2 / "Umbenennen…": rename the Klausur of the current Abgabe."""
        session = self._import_split_session
        if session is None:
            return
        index = session.group_index_for_page(session.current_page)
        if index < len(session.group_names):
            name = self._ask_import_split_group_name(
                "Klausur umbenennen", initial=session.group_names[index], exclude_index=index
            )
            if name is not None and self._import_split_session is session:
                session.rename_group(index, name)
                self._refresh_import_split_view()
        self._focus_import_split_name_field()

    def _ask_new_import_split_group(self) -> int | None:
        """Ask for the name of a new Klausur and add it; ``None`` when cancelled or nine exist already."""
        session = self._import_split_session
        if len(session.group_names) >= MAX_GROUPS:
            self._flash_import_split_info(group_name_problem_text("too_many"))
            return None
        name = self._ask_import_split_group_name(
            "Neue Klausur im Import", initial=default_group_name(len(session.group_names)), exclude_index=None
        )
        if name is None or self._import_split_session is not session:
            return None
        return session.add_group(name)

    def _ask_import_split_group_name(self, title: str, *, initial: str, exclude_index: int | None) -> str | None:
        """Name prompt with inline validation (the dialog stays open on a rejected name)."""
        session = self._import_split_session
        view = self._import_split_view

        def _validate(text: str) -> str | None:
            problem = session.group_name_problem(text, exclude_index=exclude_index)
            return None if problem is None else group_name_problem_text(problem)

        return simpledialog.askstring(
            title,
            "Name der Klausur (wird zum Ordnernamen):",
            validate=_validate,
            initialvalue=initial,
            parent=view.popup if view is not None else None,
        )
