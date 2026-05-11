"""Shared HSM contract bridge for app-local imports."""

from __future__ import annotations

from bw_libs.shared_gui_core import ensure_bw_gui_on_path as _ensure_bw_gui_on_path

_ensure_bw_gui_on_path()

from bw_gui.contracts.hsm import (  # type: ignore[assignment]
    ESCAPE_CLOSE_POPUP,
    ESCAPE_EXIT_INLINE_EDITOR,
    ESCAPE_POP_PARENT,
    ESCAPE_ROOT_NOOP,
    HsmContract,
    HsmIntentSpec,
    TransitionRule,
    build_ui_hsm_contract,
)

__all__ = [
    "ESCAPE_CLOSE_POPUP",
    "ESCAPE_EXIT_INLINE_EDITOR",
    "ESCAPE_POP_PARENT",
    "ESCAPE_ROOT_NOOP",
    "HsmContract",
    "HsmIntentSpec",
    "TransitionRule",
    "build_ui_hsm_contract",
]
