"""Konfiguration der Korrektor-Guardrails (reine Daten, ``check_ai_guardrails.py``).

Pfadlisten, Marker und Allowlists, die die Checks auswerten. Aus
``check_ai_guardrails.py`` ausgelagert (300-Zeilen-Regel), Inhalt unverändert.
"""

# line-limit: data-only
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

GUARDRAIL_RELEVANT_PATHS = {
    "AGENTS.md",
    ".github/copilot-instructions.md",
    ".github/pull_request_template.md",
    ".github/workflows/quality-guardrails.yml",
    "docs/ARCHITEKTUR.md",
    "docs/DEVELOPMENT_LOG.md",
    "docs/GUI_MIGRATION_BACKLOG.md",
    "CHANGELOG.md",
    "bw_libs/ui_contract/keybinding.py",
    "bw_libs/ui_contract/popup.py",
    "bw_libs/ui_contract/hsm.py",
    "bw_libs/ui_contract/laufkern.py",
    "bw_libs/app_paths.py",
    "tools/ci/check_ai_guardrails.py",
    "tools/ci/guardrail_checks.py",
    "tools/ci/guardrail_config.py",
    "tools/ci/guardrail_process.py",
    "tools/ci/guardrail_support.py",
    "app/adapters/gui/main_window.py",
    "app/adapters/gui/ui_intent_controller.py",
    "app/adapters/gui/ui_intents.py",
    "app/adapters/undo/history.py",
}
PROCESS_GUIDANCE_RULES = {
    "feature_commit": "Feature-Aenderungen werden in eigenstaendigen Commits",
    "manual_push": "Push erfolgt manuell",
}
SHORTCUT_COVERAGE_SOFT_CHECKS = (
    {
        "label": "global-create-exam",
        "intent_paths": ("app/adapters/gui/ui_intents.py",),
        "intent_markers": ("GLOBAL_CREATE_EXAM", "global.create_exam"),
        "shortcut_paths": ("app/adapters/gui/main_window.py",),
        "shortcut_markers": ("intent=UiIntent.GLOBAL_CREATE_EXAM",),
    },
    {
        "label": "global-export",
        "intent_paths": ("app/adapters/gui/ui_intents.py",),
        "intent_markers": ("GLOBAL_EXPORT", "global.export"),
        "shortcut_paths": ("app/adapters/gui/main_window.py",),
        "shortcut_markers": ("intent=UiIntent.GLOBAL_EXPORT",),
    },
    {
        "label": "global-escape",
        "intent_paths": ("app/adapters/gui/ui_intents.py",),
        "intent_markers": ("GLOBAL_ESCAPE", "global.escape"),
        "shortcut_paths": ("app/adapters/gui/main_window.py",),
        "shortcut_markers": ("intent=UiIntent.GLOBAL_ESCAPE",),
    },
    {
        "label": "global-undo",
        "intent_paths": ("app/adapters/gui/ui_intents.py",),
        "intent_markers": ("GLOBAL_UNDO", "global.undo"),
        "shortcut_paths": ("app/adapters/gui/main_window.py",),
        "shortcut_markers": ("intent=UiIntent.GLOBAL_UNDO",),
    },
    {
        "label": "global-redo",
        "intent_paths": ("app/adapters/gui/ui_intents.py",),
        "intent_markers": ("GLOBAL_REDO", "global.redo"),
        "shortcut_paths": ("app/adapters/gui/main_window.py",),
        "shortcut_markers": ("intent=UiIntent.GLOBAL_REDO",),
    },
    {
        "label": "correction-copy-annotation",
        "intent_paths": ("app/adapters/gui/ui_intents.py",),
        "intent_markers": ("CORRECTION_COPY_ANNOTATION", "correction.copy_annotation"),
        "shortcut_paths": ("app/adapters/gui/main_window.py",),
        "shortcut_markers": ("intent=UiIntent.CORRECTION_COPY_ANNOTATION",),
    },
    {
        "label": "correction-cut-annotation",
        "intent_paths": ("app/adapters/gui/ui_intents.py",),
        "intent_markers": ("CORRECTION_CUT_ANNOTATION", "correction.cut_annotation"),
        "shortcut_paths": ("app/adapters/gui/main_window.py",),
        "shortcut_markers": ("intent=UiIntent.CORRECTION_CUT_ANNOTATION",),
    },
    {
        "label": "correction-paste-annotation",
        "intent_paths": ("app/adapters/gui/ui_intents.py",),
        "intent_markers": ("CORRECTION_PASTE_ANNOTATION", "correction.paste_annotation"),
        "shortcut_paths": ("app/adapters/gui/main_window.py",),
        "shortcut_markers": ("intent=UiIntent.CORRECTION_PASTE_ANNOTATION",),
    },
    {
        "label": "debug-runtime-overlay",
        "intent_paths": ("app/adapters/gui/ui_intents.py",),
        "intent_markers": ("DEBUG_RUNTIME_OVERLAY", "debug.runtime_overlay"),
        "shortcut_paths": ("app/adapters/gui/main_window.py",),
        "shortcut_markers": ("intent=UiIntent.DEBUG_RUNTIME_OVERLAY",),
    },
    {
        "label": "debug-runtime-offline",
        "intent_paths": ("app/adapters/gui/ui_intents.py",),
        "intent_markers": ("DEBUG_RUNTIME_OFFLINE", "debug.runtime_offline"),
        "shortcut_paths": ("app/adapters/gui/main_window.py",),
        "shortcut_markers": ("intent=UiIntent.DEBUG_RUNTIME_OFFLINE",),
    },
)
CHANGELOG_RELEVANT_PREFIXES = (
    "app/adapters/gui/",
    "bw_libs/",
)
CHANGELOG_CODEV_RELEVANT_PATHS = {
    "AGENTS.md",
    ".github/copilot-instructions.md",
    ".github/pull_request_template.md",
    "tools/ci/check_ai_guardrails.py",
    "docs/GUI_MIGRATION_BACKLOG.md",
    "bw_libs/ui_contract/keybinding.py",
    "bw_libs/ui_contract/popup.py",
    "bw_libs/ui_contract/hsm.py",
    "bw_libs/ui_contract/laufkern.py",
    "bw_libs/app_paths.py",
    "app/adapters/undo/history.py",
}
LAUFKERN_BRIDGE_PATH = "bw_libs/ui_contract/laufkern.py"
LAUFKERN_FALLBACK_SCAN_ROOTS = ("app", "bw_libs")
FUTURE_GUI_SEARCH_ROOTS = (
    "app/adapters/gui",
    "app/ui",
)
FUTURE_GUI_ENTRY_FILE_NAMES = {
    "main_window.py",
    "ui.py",
    "blatt_ui.py",
    "screen_builder.py",
}
FUTURE_GUI_ENTRY_BASELINES: set[str] = set()
FUTURE_GUI_REQUIRED_SHARED_SNIPPETS = (
    "ensure_bw_gui_on_path()",
    "from bw_gui.runtime import",
    "from bw_gui.menu import",
    "open_tabbed_settings_dialog",
    "compose_hover_text",
    "HoverTooltip",
)
GUI_CONTRACT_SCAN_ROOTS = (*FUTURE_GUI_SEARCH_ROOTS, "bw_libs")
UI_BASECLASS_MODULE_ALIASES = {"ui", "widgets", "tui"}
LEGACY_UI_BASECLASS_ALLOWLIST: set[str] = set()
SHARED_PRIMITIVE_CLASS_NAMES = {"TkRootHost", "ScrollablePopupWindow", "WrappedTextField", "ScrollableFrame"}
SHARED_PRIMITIVE_CLASS_ALLOWLIST: set[str] = set()
GUI_MIGRATION_BACKLOG_PATH = "docs/GUI_MIGRATION_BACKLOG.md"
_FACADE_FAMILY_STEMS = {
    "app/adapters/gui/main_window.py": "main_window",
    "app/adapters/gui/ui_intent_controller.py": "ui_intent_controller",
}
