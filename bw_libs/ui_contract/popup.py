"""Shared popup policy bridge for app-local imports."""

from __future__ import annotations

from bw_libs.shared_gui_core import ensure_bw_gui_on_path as _ensure_bw_gui_on_path

_ensure_bw_gui_on_path()

from bw_gui.contracts.popup import (  # type: ignore[assignment]
    POPUP_KIND_MODAL,
    POPUP_KIND_NON_MODAL,
    PopupPolicy,
    PopupPolicyRegistry,
    PopupSession,
)

__all__ = [
    "POPUP_KIND_MODAL",
    "POPUP_KIND_NON_MODAL",
    "PopupPolicy",
    "PopupPolicyRegistry",
    "PopupSession",
]
