"""Inhaltliche Guardrail-Checks (Shortcut-Integration, Undo/Redo, GUI-Contracts, Bridges).

Aus ``check_ai_guardrails.py`` ausgelagert (300-Zeilen-Regel), Inhalt unverändert.
"""

from __future__ import annotations

import ast

from guardrail_config import (
    FUTURE_GUI_ENTRY_BASELINES,
    FUTURE_GUI_REQUIRED_SHARED_SNIPPETS,
    GUI_MIGRATION_BACKLOG_PATH,
    LAUFKERN_FALLBACK_SCAN_ROOTS,
    LEGACY_UI_BASECLASS_ALLOWLIST,
    SHARED_PRIMITIVE_CLASS_ALLOWLIST,
    SHARED_PRIMITIVE_CLASS_NAMES,
)
from guardrail_support import (
    _contains_direct_tkinter_import,
    _forbid_substring,
    _iter_facade_family_files,
    _iter_future_gui_entry_candidates,
    _iter_python_files_under,
    _iter_repo_gui_python_files,
    _local_ui_bases,
    _read,
    _read_concatenated,
    _require_substring,
)


def _check_runtime_shortcut_integration(errors: list[str]) -> None:
    """Require explicit runtime shortcut and popup policy integration somewhere in the main_window family."""

    main_window_files = _iter_facade_family_files("main_window")
    main_window = _read_concatenated(main_window_files)
    label = "app/adapters/gui/main_window*.py"
    _require_substring(
        main_window,
        "self._runtime_shortcuts.evaluate_runtime(",
        label,
        errors,
    )
    _require_substring(
        main_window,
        "self._popup_registry = PopupPolicyRegistry()",
        label,
        errors,
    )
    _require_substring(
        main_window,
        "self._register_popup_window(window, policy_id=\"dialog.non_blocking\")",
        label,
        errors,
    )
    _require_substring(
        main_window,
        "self._popup_registry.close_popup(popup_id)",
        label,
        errors,
    )


def _find_class(module: ast.Module, class_name: str) -> ast.ClassDef | None:
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    return None


def _method_calls_self_helper(class_node: ast.ClassDef, method_name: str, helper_names: set[str]) -> bool:
    for node in class_node.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name != method_name:
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            func = child.func
            if not isinstance(func, ast.Attribute):
                continue
            if not isinstance(func.value, ast.Name):
                continue
            if func.value.id != "self":
                continue
            if func.attr in helper_names:
                return True
    return False


def _function_has_arg(node: ast.FunctionDef, arg_name: str) -> bool:
    all_args = node.args.args + node.args.posonlyargs + node.args.kwonlyargs
    return any(arg.arg == arg_name for arg in all_args)


def _check_undo_redo_contracts(errors: list[str]) -> None:
    """Verify the undo/redo contract across the whole ui_intent_controller*/main_window* mixin families.

    `ui_intent_controller.py`/`main_window.py` are thin facades (no method
    bodies of their own - see `docs/ARCHITEKTUR.md` "Datei-Organisation"),
    so every check here operates on the concatenation of the whole family
    instead of the facade file alone.
    """
    controller_files = _iter_facade_family_files("ui_intent_controller")
    controller_text = _read_concatenated(controller_files)
    controller_label = "app/adapters/gui/ui_intent_controller*.py"
    intents_text = _read("app/adapters/gui/ui_intents.py")
    main_window_files = _iter_facade_family_files("main_window")
    main_window = _read_concatenated(main_window_files)
    main_window_label = "app/adapters/gui/main_window*.py"

    _require_substring(controller_text, "def undo(self) -> bool:", controller_label, errors)
    _require_substring(controller_text, "def redo(self) -> bool:", controller_label, errors)
    _require_substring(controller_text, "self._deps.undo_history", controller_label, errors)
    _require_substring(controller_text, "def _record_history_action(", controller_label, errors)

    _require_substring(intents_text, "GLOBAL_UNDO", "app/adapters/gui/ui_intents.py", errors)
    _require_substring(intents_text, "GLOBAL_REDO", "app/adapters/gui/ui_intents.py", errors)
    _require_substring(main_window, "label=\"Bearbeiten\"", main_window_label, errors)
    _require_substring(main_window, '_k("Ctrl+Z")', main_window_label, errors)
    _require_substring(main_window, '_k("Ctrl+Y")', main_window_label, errors)

    # Every "<verb>_immediate" method that mutates a given exam (signature
    # includes an `exam` parameter) must register undo/redo history -
    # directly, or via one of the established shared tail-helpers that
    # themselves call the raw history recorders (see
    # app/adapters/gui/ui_intent_controller_annotations.py:
    # _save_annotation_mutation_immediate, and
    # ui_intent_controller_superposition.py: _apply_superposition_clones).
    # `_immediate` methods *without* an `exam` parameter (e.g. the global
    # Notenschluessel-CRUD in ui_intent_controller_grading_scale.py) are
    # deliberately exempt - they mutate a global store, not an open exam,
    # and never go through the exam-content undo/redo history by design
    # (see that file's docstring).
    # Exam creation: `create_exam` (folder choice) and the PDF-import
    # completion callback `_create_exam_from_split` both go through the
    # shared tail-helper `_create_exam_from_folder`, which is itself tracked
    # here and must call `_record_history_action` directly.
    # Region edits: `upsert_region_immediate`/`delete_region_immediate` save
    # through the shared tail-helper `_save_region_edit`
    # (ui_intent_controller_regions.py), which is itself tracked here and must
    # call `_record_exam_payload_action` directly.
    baseline_mutators = {
        "create_exam",
        "_create_exam_from_folder",
        "_save_region_edit",
        "delete_selected_exam",
        "update_exam_index_dir",
        "finish_reading_mode",
    }
    history_helpers = {
        "_record_history_action",
        "_record_exam_payload_action",
        "_save_annotation_mutation_immediate",
        "_apply_superposition_clones",
        "_create_exam_from_folder",
        "_save_region_edit",
    }

    for rel_path in controller_files:
        try:
            module = ast.parse(_read(rel_path), filename=rel_path)
        except Exception as exc:
            errors.append(f"{rel_path}: failed to parse Python AST -> {exc}")
            continue

        for class_node in (node for node in module.body if isinstance(node, ast.ClassDef)):
            for method_node in (node for node in class_node.body if isinstance(node, ast.FunctionDef)):
                is_tracked = method_node.name in baseline_mutators or (
                    method_node.name.endswith("_immediate") and _function_has_arg(method_node, "exam")
                )
                if not is_tracked:
                    continue
                if not _method_calls_self_helper(class_node, method_node.name, history_helpers):
                    errors.append(
                        f"{rel_path}: mutator '{method_node.name}' must register undo/redo history via "
                        f"_record_history_action/_record_exam_payload_action (directly or via an established tail-helper)"
                    )


def _check_shared_ui_contracts(errors: list[str]) -> None:
    """Require shared UI imports and block legacy fallback branches, anywhere in the main_window family."""

    main_window_files = _iter_facade_family_files("main_window")
    main_window = _read_concatenated(main_window_files)
    label = "app/adapters/gui/main_window*.py"

    required_snippets = (
        "from bw_gui.dialogs import open_tabbed_settings_dialog",
        "from bw_gui.menu import section_spec",
        "from bw_gui.shortcuts import compose_hover_text",
        "from bw_gui.widgets import HoverTooltip as SharedHoverTooltip",
        "def build_menu(self) -> list:",
        "tooltip = SharedHoverTooltip(widget, text, theme_key=self._tooltip_theme_key)",
        "open_tabbed_settings_dialog(",
    )
    forbidden_snippets = (
        "except ModuleNotFoundError",
        "if SharedHoverTooltip is None",
        "if compose_hover_text is None",
        "if open_tabbed_settings_dialog is None",
    )

    for snippet in required_snippets:
        _require_substring(main_window, snippet, label, errors)
    for snippet in forbidden_snippets:
        _forbid_substring(main_window, snippet, label, errors)


def _check_future_gui_entry_contracts(errors: list[str]) -> None:
    """Require shared GUI bootstrap contracts for newly added entrypoint files.

    `app/adapters/gui/main_window.py` is this repo's established entry
    file, but it is a thin facade (see `docs/ARCHITEKTUR.md`
    "Datei-Organisation") - its bootstrap contract lives in its
    `main_window_*.py` mixin family (mainly `main_window_base.py`), not in
    the facade file itself, so that one candidate is checked against the
    concatenated family instead of just its own text. Any *other* future
    entry-file candidate (a genuinely new GUI entry point, not yet split
    into a mixin family) is still checked as a single file - that is the
    scenario this guard exists to catch.
    """

    for rel_path in _iter_future_gui_entry_candidates():
        if rel_path in FUTURE_GUI_ENTRY_BASELINES:
            continue

        if rel_path == "app/adapters/gui/main_window.py":
            text = _read_concatenated(_iter_facade_family_files("main_window"))
            label = "app/adapters/gui/main_window*.py"
        else:
            text = _read(rel_path)
            label = rel_path

        for snippet in FUTURE_GUI_REQUIRED_SHARED_SNIPPETS:
            _require_substring(text, snippet, label, errors)

        _forbid_substring(text, "import tkinter", label, errors)
        _forbid_substring(text, "from tkinter import", label, errors)


def _check_repo_wide_gui_contracts(errors: list[str]) -> None:
    """Enforce repo-wide GUI contract: no direct tkinter imports and no new local widget bases."""

    for rel_path in _iter_repo_gui_python_files():
        try:
            source = _read(rel_path).lstrip("\ufeff")
            module = ast.parse(source, filename=rel_path)
        except Exception as exc:
            errors.append(f"{rel_path}: failed to parse Python AST -> {exc}")
            continue

        if _contains_direct_tkinter_import(module):
            errors.append(
                f"{rel_path}: direct tkinter/ttk import is forbidden; use bw_gui.runtime and shared bw_gui modules"
            )

        for node in ast.walk(module):
            if not isinstance(node, ast.ClassDef):
                continue

            if node.name in SHARED_PRIMITIVE_CLASS_NAMES:
                marker = f"{rel_path}:{node.name}"
                if marker not in SHARED_PRIMITIVE_CLASS_ALLOWLIST:
                    errors.append(
                        f"{rel_path}:{node.lineno} class '{node.name}' redefines a reserved shared primitive; "
                        "import it from bw_gui.runtime/dialogs/widgets instead"
                    )

            bases = _local_ui_bases(node)
            if not bases:
                continue
            marker = f"{rel_path}:{node.name}"
            if marker in LEGACY_UI_BASECLASS_ALLOWLIST:
                continue
            errors.append(
                f"{rel_path}:{node.lineno} class '{node.name}' uses local UI base {bases}; "
                "move reusable widget implementation to bw-gui"
            )


def _check_gui_migration_backlog(errors: list[str]) -> None:
    """Require explicit backlog tracking for all active GUI exemption baselines/allowlists."""

    backlog = _read(GUI_MIGRATION_BACKLOG_PATH)
    _require_substring(backlog, "## Active Exemptions", GUI_MIGRATION_BACKLOG_PATH, errors)
    _require_substring(backlog, "remove_by:", GUI_MIGRATION_BACKLOG_PATH, errors)

    for rel_path in sorted(FUTURE_GUI_ENTRY_BASELINES):
        _require_substring(backlog, f"- {rel_path}", GUI_MIGRATION_BACKLOG_PATH, errors)

    for marker in sorted(LEGACY_UI_BASECLASS_ALLOWLIST):
        _require_substring(backlog, f"- {marker}", GUI_MIGRATION_BACKLOG_PATH, errors)


def _check_laufkern_fallback_sunset(errors: list[str]) -> None:
    """Wave-3 sunset gate: no ModuleNotFoundError fallback branches remain."""

    for rel_path in _iter_python_files_under(LAUFKERN_FALLBACK_SCAN_ROOTS):
        if "except ModuleNotFoundError" in _read(rel_path):
            errors.append(
                f"{rel_path}: ModuleNotFoundError fallback is forbidden in Wave-3; require shared imports without local fallback branches"
            )


def _check_ui_contract_bridge_decommission(errors: list[str]) -> None:
    """Phase-I decommission gate: ui_contract bridges stay thin shared re-export shims."""

    required_imports = {
        "bw_libs/ui_contract/keybinding.py": "from bw_gui.contracts.keybinding import",
        "bw_libs/ui_contract/popup.py": "from bw_gui.contracts.popup import",
        "bw_libs/ui_contract/hsm.py": "from bw_gui.contracts.hsm import",
        "bw_libs/ui_contract/laufkern.py": "from bw_gui.laufkern import",
    }
    forbidden_local_markers = {
        "bw_libs/ui_contract/keybinding.py": ("class KeyBindingDefinition", "class KeybindingRegistry"),
        "bw_libs/ui_contract/popup.py": ("class PopupPolicy", "class PopupPolicyRegistry"),
        "bw_libs/ui_contract/hsm.py": ("class HsmContract", "def build_ui_hsm_contract"),
        "bw_libs/ui_contract/laufkern.py": ("class LaufKernManifest", "def aggregate_completion("),
    }

    for rel_path, import_marker in required_imports.items():
        source = _read(rel_path).lstrip("\ufeff")
        _require_substring(source, "ensure_bw_gui_on_path", rel_path, errors)
        _require_substring(source, import_marker, rel_path, errors)
        for forbidden in forbidden_local_markers[rel_path]:
            _forbid_substring(source, forbidden, rel_path, errors)
