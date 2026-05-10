"""Central UI intent catalog for Korrektor shortcut semantics."""

from __future__ import annotations


class UiIntent:
    GLOBAL_CREATE_EXAM = "global.create_exam"
    GLOBAL_ESCAPE = "global.escape"
    GLOBAL_UNDO = "global.undo"
    GLOBAL_REDO = "global.redo"
    DETAIL_NAVIGATE_LEFT = "detail.navigate_left"
    DETAIL_NAVIGATE_RIGHT = "detail.navigate_right"
    DEBUG_RUNTIME_OVERLAY = "debug.runtime_overlay"
    DEBUG_RUNTIME_OFFLINE = "debug.runtime_offline"
