"""Shared keybinding contract bridge for app-local imports."""

from __future__ import annotations

from bw_libs.shared_gui_core import ensure_bw_gui_on_path as _ensure_bw_gui_on_path

_ensure_bw_gui_on_path()

from bw_gui.contracts.keybinding import (  # type: ignore[assignment]
    UI_MODE_DIALOG,
    UI_MODE_EDITOR,
    UI_MODE_GLOBAL,
    UI_MODE_OFFLINE,
    UI_MODE_PREVIEW,
    KeyBindingDefinition,
    KeybindingRegistry,
    KeybindingRuntimeContext,
)

__all__ = [
    "UI_MODE_DIALOG",
    "UI_MODE_EDITOR",
    "UI_MODE_GLOBAL",
    "UI_MODE_OFFLINE",
    "UI_MODE_PREVIEW",
    "KeyBindingDefinition",
    "KeybindingRegistry",
    "KeybindingRuntimeContext",
]
