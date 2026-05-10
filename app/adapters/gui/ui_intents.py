"""Central UI intent catalog for Korrektor shortcut semantics."""

from __future__ import annotations


class UiIntent:
    GLOBAL_CREATE_EXAM = "global.create_exam"
    GLOBAL_ESCAPE = "global.escape"
    GLOBAL_UNDO = "global.undo"
    GLOBAL_REDO = "global.redo"
    DETAIL_NAVIGATE_LEFT = "detail.navigate_left"
    DETAIL_NAVIGATE_RIGHT = "detail.navigate_right"
    DETAIL_NAVIGATE_UP = "detail.navigate_up"
    DETAIL_NAVIGATE_DOWN = "detail.navigate_down"
    DETAIL_NAVIGATE_CTRL_UP = "detail.navigate_ctrl_up"
    DETAIL_NAVIGATE_CTRL_DOWN = "detail.navigate_ctrl_down"
    CORRECTION_TOGGLE_FINISHED = "correction.toggle_finished"
    DEBUG_RUNTIME_OVERLAY = "debug.runtime_overlay"
    DEBUG_RUNTIME_OFFLINE = "debug.runtime_offline"
