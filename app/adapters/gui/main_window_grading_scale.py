from __future__ import annotations

from app.adapters.gui.main_window_grading_scale_actions import MainWindowGradingScaleActionsMixin
from app.adapters.gui.main_window_constants import GRADING_SCALE_TYPE_LABEL_BY_VALUE, GRADING_SCALE_TYPE_LABELS
from app.core.domain.grading_scale import STATUS_ACTIVE, STATUS_ARCHIVED

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.dialogs import ScrollablePopupWindow
from bw_gui.runtime import on_treeview_select, ui, widgets


class MainWindowGradingScaleMixin(MainWindowGradingScaleActionsMixin):
    """Notenschluessel-Verwaltung (Meilenstein 2.4): ein Popup fuer die globalen `GradingScale`-Vorlagen.

    Nutzt `bw_gui.dialogs.ScrollablePopupWindow` (bw-gui-Standard fuer
    Popups, siehe `bw-gui/docs/SCROLLABILITY_CONTRACT.md`) - die Liste
    (Treeview) hat zusaetzlich ihren eigenen Scrollbar fuer viele
    Notenschluessel-Eintraege; der aeussere Scroll-Rahmen sorgt dafuer,
    dass bei kleiner Fensterhoehe trotzdem das komplette Formular
    (inkl. Notenstufen-Editor und Aktions-Buttons) erreichbar bleibt.
    Bewusst kein eigener View-Modus (Uebersicht/Detail/Einlesen/Korrektur)
    - die Verwaltung ist klausurunabhaengig und passt als modaler Dialog
    besser zum bestehenden Popup-Mechanismus als zu einem weiteren
    Top-Level-Modus.
    """

    def _open_grading_scale_management_popup(self) -> None:
        if self._controller is None:
            return
        # ScrollablePopupWindow is one-shot (closing destroys the widget
        # tree) - build fresh on every open instead of the previous
        # withdraw()/deiconify() retain pattern.
        self._build_grading_scale_popup()
        self._refresh_grading_scale_tree()
        self._clear_grading_scale_form()

    def _build_grading_scale_popup(self) -> None:
        popup = ScrollablePopupWindow(
            self.root,
            title="Notenschlüssel verwalten",
            geometry="880x560",
            minsize=(640, 420),
            theme_key=self._tooltip_theme_key,
        )

        body = widgets.Frame(popup.content, padding=10)
        body.pack(fill=ui.BOTH, expand=True)

        list_panel = widgets.Frame(body, style="Surface.TFrame", padding=(0, 0, 10, 0))
        list_panel.pack(side=ui.LEFT, fill=ui.BOTH, expand=True)
        widgets.Label(list_panel, text="Vorhandene Notenschlüssel", style="Muted.TLabel").pack(anchor=ui.W)

        tree_shell = widgets.Frame(list_panel, style="Surface.TFrame")
        tree_shell.pack(fill=ui.BOTH, expand=True, pady=(4, 0))
        self._grading_scale_tree = widgets.Treeview(
            tree_shell,
            columns=("subject", "year", "school", "status"),
            show="tree headings",
            height=14,
        )
        self._grading_scale_tree.heading("#0", text="Name")
        self._grading_scale_tree.heading("subject", text="Fach")
        self._grading_scale_tree.heading("year", text="Jahrgang")
        self._grading_scale_tree.heading("school", text="Schule")
        self._grading_scale_tree.heading("status", text="Status")
        self._grading_scale_tree.column("#0", width=160)
        self._grading_scale_tree.column("subject", width=90, anchor=ui.CENTER)
        self._grading_scale_tree.column("year", width=70, anchor=ui.CENTER)
        self._grading_scale_tree.column("school", width=140, anchor=ui.W)
        self._grading_scale_tree.column("status", width=90, anchor=ui.CENTER)
        tree_scroll = widgets.Scrollbar(tree_shell, orient=ui.VERTICAL)
        self._grading_scale_tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.configure(command=self._grading_scale_tree.yview)
        self._grading_scale_tree.pack(side=ui.LEFT, fill=ui.BOTH, expand=True)
        tree_scroll.pack(side=ui.RIGHT, fill=ui.Y)
        on_treeview_select(self._grading_scale_tree, self._on_grading_scale_selected)

        self._grading_scale_usage_var = ui.StringVar(value="Verwendung: -")
        widgets.Label(
            list_panel, textvariable=self._grading_scale_usage_var, style="Muted.TLabel", justify=ui.LEFT
        ).pack(anchor=ui.W, pady=(6, 0))

        form_panel = widgets.Frame(body, style="Surface.TFrame", padding=(10, 0, 0, 0))
        form_panel.pack(side=ui.LEFT, fill=ui.Y)
        widgets.Label(form_panel, text="Notenschlüssel bearbeiten", style="Muted.TLabel").pack(anchor=ui.W)

        self._gs_name_var = ui.StringVar(value="")
        self._gs_subject_var = ui.StringVar(value="")
        self._gs_year_var = ui.StringVar(value="")
        self._gs_school_var = ui.StringVar(value="")
        self._gs_type_var = ui.StringVar(value=GRADING_SCALE_TYPE_LABELS[0])

        for label, var in (
            ("Name", self._gs_name_var),
            ("Fach", self._gs_subject_var),
            ("Jahrgang", self._gs_year_var),
            ("Schule", self._gs_school_var),
        ):
            row = widgets.Frame(form_panel, style="Surface.TFrame")
            row.pack(fill=ui.X, pady=(6, 0))
            widgets.Label(row, text=label, style="Muted.TLabel", width=10).pack(side=ui.LEFT)
            widgets.Entry(row, textvariable=var, width=28).pack(side=ui.LEFT, fill=ui.X, expand=True)

        type_row = widgets.Frame(form_panel, style="Surface.TFrame")
        type_row.pack(fill=ui.X, pady=(6, 0))
        widgets.Label(type_row, text="Skala", style="Muted.TLabel", width=10).pack(side=ui.LEFT)
        widgets.Combobox(
            type_row, textvariable=self._gs_type_var, state="readonly", values=GRADING_SCALE_TYPE_LABELS, width=26
        ).pack(side=ui.LEFT, fill=ui.X, expand=True)

        widgets.Label(
            form_panel,
            text="Notenstufen (eine pro Zeile, Prozent:Note - z. B. 80:1)",
            style="Muted.TLabel",
            justify=ui.LEFT,
        ).pack(anchor=ui.W, pady=(8, 0))
        self._gs_thresholds_text = ui.Text(form_panel, height=8, width=32, wrap="word")
        self._gs_thresholds_text.pack(fill=ui.X, pady=(4, 0))

        actions_row1 = widgets.Frame(form_panel, style="Surface.TFrame")
        actions_row1.pack(fill=ui.X, pady=(10, 0))
        widgets.Button(
            actions_row1, text="Neu", style="SecondaryAction.TButton", command=self._clear_grading_scale_form
        ).pack(side=ui.LEFT)
        widgets.Button(
            actions_row1,
            text="Speichern",
            style="SecondaryAction.TButton",
            command=self._save_grading_scale_from_form,
        ).pack(side=ui.LEFT, padx=(8, 0))

        actions_row2 = widgets.Frame(form_panel, style="Surface.TFrame")
        actions_row2.pack(fill=ui.X, pady=(6, 0))
        self._gs_archive_button = widgets.Button(
            actions_row2,
            text="Archivieren",
            style="SecondaryAction.TButton",
            command=self._archive_selected_grading_scale,
        )
        self._gs_archive_button.pack(side=ui.LEFT)
        self._gs_reactivate_button = widgets.Button(
            actions_row2,
            text="Reaktivieren",
            style="SecondaryAction.TButton",
            command=self._reactivate_selected_grading_scale,
        )
        self._gs_delete_button = widgets.Button(
            actions_row2,
            text="Löschen",
            style="SecondaryAction.TButton",
            command=self._delete_selected_grading_scale,
        )
        self._gs_delete_button.pack(side=ui.LEFT, padx=(8, 0))

        transfer_row = widgets.Frame(form_panel, style="Surface.TFrame")
        transfer_row.pack(fill=ui.X, pady=(16, 0))
        widgets.Label(
            transfer_row,
            text="Notenschlüssel leben lokal auf diesem Rechner - auf einem anderen Rechner"
            " (z. B. anderer Exam-Indexordner) fehlen sie, bis sie hier ex-/importiert wurden.",
            style="Muted.TLabel",
            justify=ui.LEFT,
            wraplength=280,
        ).pack(anchor=ui.W)
        transfer_buttons = widgets.Frame(transfer_row, style="Surface.TFrame")
        transfer_buttons.pack(fill=ui.X, pady=(6, 0))
        export_button = widgets.Button(
            transfer_buttons,
            text="Exportieren...",
            style="SecondaryAction.TButton",
            command=self._export_grading_scales,
        )
        export_button.pack(side=ui.LEFT)
        self._attach_hover_help(export_button, label="Alle Notenschlüssel in eine Datei exportieren")
        import_button = widgets.Button(
            transfer_buttons,
            text="Importieren...",
            style="SecondaryAction.TButton",
            command=self._import_grading_scales,
        )
        import_button.pack(side=ui.LEFT, padx=(8, 0))
        self._attach_hover_help(import_button, label="Notenschlüssel aus einer zuvor exportierten Datei übernehmen")

        widgets.Button(form_panel, text="Schließen", style="SecondaryAction.TButton", command=self._close_grading_scale_popup).pack(
            anchor=ui.E, pady=(14, 0)
        )

        self._grading_scale_popup = popup

    def _refresh_grading_scale_tree(self) -> None:
        if self._grading_scale_tree is None or self._controller is None:
            return
        self._grading_scale_tree.delete(*self._grading_scale_tree.get_children())
        for scale in self._controller.list_grading_scales():
            status_label = "aktiv" if scale.status == STATUS_ACTIVE else "archiviert"
            self._grading_scale_tree.insert(
                "", ui.END, iid=scale.scale_id, text=scale.name,
                values=(scale.subject, scale.year, scale.school, status_label),
            )

    def _on_grading_scale_selected(self, _event: object) -> None:
        if self._grading_scale_tree is None or self._controller is None:
            return
        selection = self._grading_scale_tree.selection()
        if not selection:
            return
        scale_id = selection[0]
        scale = next((item for item in self._controller.list_grading_scales() if item.scale_id == scale_id), None)
        if scale is None:
            return
        self._grading_scale_selected_id = scale.scale_id
        self._gs_name_var.set(scale.name)
        self._gs_subject_var.set(scale.subject)
        self._gs_year_var.set(scale.year)
        self._gs_school_var.set(scale.school)
        self._gs_type_var.set(GRADING_SCALE_TYPE_LABEL_BY_VALUE.get(scale.scale_type, GRADING_SCALE_TYPE_LABELS[0]))
        self._gs_thresholds_text.delete("1.0", ui.END)
        self._gs_thresholds_text.insert(
            "1.0", "\n".join(f"{t.min_percent:g}:{t.grade_label}" for t in scale.thresholds)
        )

        usage = self._controller.list_grading_scale_usage(scale.scale_id)
        if usage:
            lines = "\n".join(f"- {entry.exam_name} ({entry.assigned_at[:10]})" for entry in usage)
            self._grading_scale_usage_var.set(f"Verwendung ({len(usage)}):\n{lines}")
        else:
            self._grading_scale_usage_var.set("Verwendung: noch in keiner Klausur verwendet")

        is_archived = scale.status == STATUS_ARCHIVED
        self._gs_archive_button.pack_forget()
        self._gs_reactivate_button.pack_forget()
        if is_archived:
            self._gs_reactivate_button.pack(side=ui.LEFT)
        else:
            self._gs_archive_button.pack(side=ui.LEFT)

    def _close_grading_scale_popup(self) -> None:
        if self._grading_scale_popup is not None and self._grading_scale_popup.winfo_exists():
            self._grading_scale_popup._request_close()
