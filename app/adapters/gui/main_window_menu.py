from __future__ import annotations

from pathlib import Path

from app.adapters.gui.dialog_services import messagebox
from app.adapters.gui.main_window_constants import CORRECTION_DEFAULT_COLOR_NAME, CORRECTION_MARKER_COLORS
from app.app_info import APP_INFO
from app.infrastructure.repositories.json_app_settings_repository import AppRuntimeSettings
from bw_gui.dialogs import SettingsDialogSpec as SharedSettingsDialogSpec
from bw_gui.dialogs import SettingsFieldSpec as SharedSettingsFieldSpec
from bw_gui.dialogs import SettingsSectionSpec as SharedSettingsSectionSpec
from bw_gui.dialogs import open_tabbed_settings_dialog
from bw_gui.menu import MenuItem as SharedMenuItem
from bw_gui.shortcuts import compose_hover_text
from bw_gui.widgets import HoverTooltip as SharedHoverTooltip

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui


class MainWindowMenuMixin:
    def _attach_hover_help(self, widget: ui.Widget, *, label: str, shortcut: str | None = None) -> None:
        """Attach hover help; shortcut details are shown here, not in button labels."""

        shortcut_text = (shortcut or "").strip()
        text = compose_hover_text(label, shortcut_text)
        tooltip = SharedHoverTooltip(widget, text, theme_key=self._tooltip_theme_key)
        self._hover_tooltips.append(tooltip)

    def _menu_create_exam(self) -> None:
        if self._controller is not None:
            self._controller.create_exam()

    def _menu_open_selected_exam(self) -> None:
        if self._controller is not None:
            self._controller.open_selected_exam()

    def _menu_export_scores(self) -> None:
        if self._controller is None:
            return
        exam = self._current_exam
        if exam is None:
            selected = self.get_selected_row()
            if selected is None:
                messagebox.showinfo("Hinweis", "Bitte zuerst eine Klausur auswählen.")
                return
            try:
                exam = self.deps.load_exam_usecase.execute(exam_file=selected.source_file)
            except Exception as exc:
                messagebox.showerror("Fehler", f"Klausur konnte nicht geladen werden: {exc}")
                return
        self._controller.export_scores_for_exam(exam=exam)

    def _menu_undo(self) -> None:
        if self._controller is not None:
            self._controller.undo()

    def _menu_redo(self) -> None:
        if self._controller is not None:
            self._controller.redo()

    def _menu_items_file(self):
        return (
            SharedMenuItem(type="command", label="Neue Klausur (Strg+N)", command=self._menu_create_exam),
            SharedMenuItem(type="command", label="Ausgewaehlte Klausur oeffnen", command=self._menu_open_selected_exam),
            SharedMenuItem(type="command", label="Punkte exportieren (Strg+E)", command=self._menu_export_scores),
            SharedMenuItem(type="separator"),
            SharedMenuItem(type="command", label="Beenden", command=self.destroy),
        )

    def _menu_items_edit(self):
        can_undo = self._controller is not None and self._controller.can_undo()
        can_redo = self._controller is not None and self._controller.can_redo()
        undo_label = self._controller.undo_label() if self._controller is not None else None
        redo_label = self._controller.redo_label() if self._controller is not None else None

        undo_text = "Rueckgaengig (Strg+Z)"
        redo_text = "Wiederholen (Strg+Y)"
        if undo_label:
            undo_text = f"Rueckgaengig: {undo_label} (Strg+Z)"
        if redo_label:
            redo_text = f"Wiederholen: {redo_label} (Strg+Y)"

        undo_item = (
            SharedMenuItem(type="command", label=undo_text, command=self._menu_undo)
            if can_undo
            else SharedMenuItem(type="disabled", label="Rueckgaengig (leer)")
        )
        redo_item = (
            SharedMenuItem(type="command", label=redo_text, command=self._menu_redo)
            if can_redo
            else SharedMenuItem(type="disabled", label="Wiederholen (leer)")
        )
        return (undo_item, redo_item)

    def _menu_items_mode(self):
        return (
            SharedMenuItem(type="command", label="Einlesemodus starten", command=self._start_reading_mode),
            SharedMenuItem(type="command", label="Korrekturmodus starten", command=self._start_correction_mode),
            SharedMenuItem(type="command", label="Extraseiten-Modus starten", command=self._start_extra_mode),
            SharedMenuItem(type="separator"),
            SharedMenuItem(type="command", label="Zur Übersicht", command=self._return_to_overview),
        )

    def _menu_items_debug(self):
        return (
            SharedMenuItem(
                type="command",
                label="Shortcut-Runtime-Debug anzeigen (Strg+Shift+D)",
                command=self._open_shortcut_runtime_debug_dialog,
            ),
            SharedMenuItem(
                type="command",
                label="Offline simulieren umschalten (Strg+Shift+O)",
                command=self._toggle_runtime_offline,
            ),
        )

    def _menu_items_help(self):
        return (
            SharedMenuItem(type="command", label="Ueber Korrektor", command=self._menu_show_about),
        )

    def _menu_show_about(self) -> None:
        messagebox.showinfo(
            "Ueber Korrektor",
            f"{APP_INFO.name}\nVersion: {APP_INFO.version}",
            parent=self.root,
        )

    def _build_settings_dialog_spec(self):
        """Build shared settings schema for Korrektor runtime options."""

        return SharedSettingsDialogSpec(
            sections=(
                SharedSettingsSectionSpec(
                    key="ui",
                    label="UI",
                    fields=(
                        SharedSettingsFieldSpec(
                            key="assignment_mode",
                            label="Zuordnungsmodus (Detailansicht)",
                            field_type="enum",
                            enum_values=("quick", "form"),
                            default=self._assignment_mode_var.get(),
                        ),
                        SharedSettingsFieldSpec(
                            key="exam_index_dir",
                            label="Ablageordner Klausur-JSON",
                            field_type="string",
                            default=self._exam_index_dir_value,
                            hint="Ein einzelner Ordner fuer alle Klausur-JSON-Dateien.",
                        ),
                        SharedSettingsFieldSpec(
                            key="default_annotation_color",
                            label="Standardfarbe Markierungen",
                            field_type="enum",
                            enum_values=tuple(CORRECTION_MARKER_COLORS.keys()),
                            default=self._marker_color_name_for_hex(self._default_annotation_color_hex),
                        ),
                        SharedSettingsFieldSpec(
                            key="default_annotation_pdf_font_size",
                            label="Standardgroesse Markierungen (pt im PDF)",
                            field_type="string",
                            default=f"{self._default_annotation_font_size:.0f}",
                            hint="Gueltiger Bereich: 8 bis 96 pt.",
                        ),
                    ),
                ),
                SharedSettingsSectionSpec(
                    key="debug",
                    label="Debug",
                    fields=(
                        SharedSettingsFieldSpec(
                            key="runtime_offline",
                            label="Runtime offline simulieren",
                            field_type="bool",
                            default=bool(self._shortcut_debug_offline_var.get()),
                        ),
                    ),
                ),
            )
        )

    def _settings_dialog_values(self) -> dict[str, object]:
        """Collect current runtime values for shared settings dialog defaults."""

        return {
            "assignment_mode": self._assignment_mode_var.get(),
            "exam_index_dir": self._exam_index_dir_value,
            "default_annotation_color": self._marker_color_name_for_hex(self._default_annotation_color_hex),
            "default_annotation_pdf_font_size": f"{self._default_annotation_font_size:.0f}",
            "runtime_offline": bool(self._shortcut_debug_offline_var.get()),
        }

    def _apply_settings_dialog_payload(self, payload: dict[str, object]) -> None:
        """Apply committed settings payload to runtime state."""

        if not isinstance(payload, dict):
            return

        self._build_styles()

        assignment_mode = str(payload.get("assignment_mode", self._assignment_mode_var.get()) or "quick")
        if assignment_mode not in {"quick", "form"}:
            assignment_mode = "quick"
        self._assignment_mode_var.set(assignment_mode)

        requested_exam_index_dir = str(payload.get("exam_index_dir", self._exam_index_dir_value) or "").strip()
        if requested_exam_index_dir and self._controller is not None:
            normalized = self._controller.update_exam_index_dir(requested_exam_index_dir)
            if normalized is not None:
                self._exam_index_dir_value = str(normalized)

        selected_color_name = str(
            payload.get("default_annotation_color", self._marker_color_name_for_hex(self._default_annotation_color_hex))
            or CORRECTION_DEFAULT_COLOR_NAME
        ).strip()
        if selected_color_name not in CORRECTION_MARKER_COLORS:
            selected_color_name = CORRECTION_DEFAULT_COLOR_NAME
        self._default_annotation_color_hex = CORRECTION_MARKER_COLORS[selected_color_name]
        self._correction_marker_color_name_var.set(selected_color_name)

        requested_size = payload.get("default_annotation_pdf_font_size", self._default_annotation_font_size)
        self._default_annotation_font_size = self._normalize_marker_font_size(requested_size)

        try:
            current_index_dir = Path(self._exam_index_dir_value).resolve()
            persisted_settings = self.deps.settings_repository.save(
                AppRuntimeSettings(
                    exam_index_dir=current_index_dir,
                    default_annotation_color=self._default_annotation_color_hex,
                    default_annotation_pdf_font_size=self._default_annotation_font_size,
                )
            )
            self._default_annotation_color_hex = self._normalize_marker_color_hex(
                persisted_settings.default_annotation_color
            )
            self._default_annotation_font_size = self._normalize_marker_font_size(
                persisted_settings.default_annotation_pdf_font_size
            )
            self._exam_index_dir_value = str(persisted_settings.exam_index_dir)
        except Exception as exc:
            messagebox.showerror("Fehler", f"Einstellungen konnten nicht gespeichert werden: {exc}")
            return

        self._shortcut_debug_offline_var.set(bool(payload.get("runtime_offline", self._shortcut_debug_offline_var.get())))
        self._refresh_shortcut_runtime_debug_dialog()
        self.set_status("Einstellungen aktualisiert")

    def _open_settings_dialog(self) -> None:
        """Open shared tabbed settings dialog for runtime UI options."""

        spec = self._build_settings_dialog_spec()

        open_tabbed_settings_dialog(
            self.root,
            title="Einstellungen",
            theme_key=self._tooltip_theme_key,
            spec=spec,
            initial_values=self._settings_dialog_values(),
            on_commit=self._apply_settings_dialog_payload,
        )
