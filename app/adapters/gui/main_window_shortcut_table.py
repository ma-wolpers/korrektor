from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.gui.ui_intents import UiIntent
from bw_gui.contracts.keybinding import UI_MODE_DIALOG, UI_MODE_EDITOR, UI_MODE_GLOBAL, UI_MODE_PREVIEW

if TYPE_CHECKING:
    from app.adapters.gui.ui_intent_controller import UiIntentController


class MainWindowShortcutTableMixin:
    """The declarative table of main-window shortcuts (moved out of `main_window_shortcuts.py`, file-size rule).

    `main_window_shortcuts.py` keeps the runtime mechanics (registry, context,
    gating, LaufKern tracking); this mixin only declares which sequence
    triggers which intent in which modes.
    """

    def set_controller(self, controller: "UiIntentController") -> None:
        """Attach the controller and register every main-window shortcut (sequence -> intent, allowed UI modes) with the runtime registry."""
        self._controller = controller
        self._bind_runtime_shortcut(
            "<Control-n>",
            lambda _event: self._controller.create_exam(),
            binding_id="global.new_exam",
            intent=UiIntent.GLOBAL_CREATE_EXAM,
            modes=(UI_MODE_GLOBAL, UI_MODE_DIALOG),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Escape>",
            self._on_escape,
            binding_id="global.escape",
            intent=UiIntent.GLOBAL_ESCAPE,
            modes=(UI_MODE_GLOBAL, UI_MODE_PREVIEW, UI_MODE_DIALOG),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Left>",
            self._on_left_key,
            binding_id="detail.left",
            intent=UiIntent.DETAIL_NAVIGATE_LEFT,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Right>",
            self._on_right_key,
            binding_id="detail.right",
            intent=UiIntent.DETAIL_NAVIGATE_RIGHT,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Up>",
            self._on_up_key,
            binding_id="detail.up",
            intent=UiIntent.DETAIL_NAVIGATE_UP,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Down>",
            self._on_down_key,
            binding_id="detail.down",
            intent=UiIntent.DETAIL_NAVIGATE_DOWN,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-Up>",
            self._on_ctrl_up_key,
            binding_id="detail.ctrl_up",
            intent=UiIntent.DETAIL_NAVIGATE_CTRL_UP,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-Down>",
            self._on_ctrl_down_key,
            binding_id="detail.ctrl_down",
            intent=UiIntent.DETAIL_NAVIGATE_CTRL_DOWN,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-space>",
            self._on_ctrl_space_key,
            binding_id="correction.toggle_finished",
            intent=UiIntent.CORRECTION_TOGGLE_FINISHED,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
        )
        self._bind_runtime_shortcut(
            "<Control-e>",
            self._on_ctrl_e_key,
            binding_id="global.export",
            intent=UiIntent.GLOBAL_EXPORT,
            modes=(UI_MODE_GLOBAL, UI_MODE_PREVIEW, UI_MODE_DIALOG, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-plus>",
            self._on_ctrl_plus_key,
            binding_id="correction.zoom_in",
            intent=UiIntent.CORRECTION_ZOOM_IN,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-equal>",
            self._on_ctrl_plus_key,
            binding_id="correction.zoom_in_equal",
            intent=UiIntent.CORRECTION_ZOOM_IN,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-KP_Add>",
            self._on_ctrl_plus_key,
            binding_id="correction.zoom_in_numpad",
            intent=UiIntent.CORRECTION_ZOOM_IN,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-minus>",
            self._on_ctrl_minus_key,
            binding_id="correction.zoom_out",
            intent=UiIntent.CORRECTION_ZOOM_OUT,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-KP_Subtract>",
            self._on_ctrl_minus_key,
            binding_id="correction.zoom_out_numpad",
            intent=UiIntent.CORRECTION_ZOOM_OUT,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-Key-0>",
            self._on_ctrl_zero_key,
            binding_id="correction.zoom_reset",
            intent=UiIntent.CORRECTION_ZOOM_RESET,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-c>",
            self._on_ctrl_c_key,
            binding_id="correction.copy_annotation",
            intent=UiIntent.CORRECTION_COPY_ANNOTATION,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
        )
        self._bind_runtime_shortcut(
            "<Control-x>",
            self._on_ctrl_x_key,
            binding_id="correction.cut_annotation",
            intent=UiIntent.CORRECTION_CUT_ANNOTATION,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
        )
        self._bind_runtime_shortcut(
            "<Control-v>",
            self._on_ctrl_v_key,
            binding_id="correction.paste_annotation",
            intent=UiIntent.CORRECTION_PASTE_ANNOTATION,
            modes=(UI_MODE_PREVIEW, UI_MODE_EDITOR),
        )
        self._bind_runtime_shortcut(
            "<Control-Shift-d>",
            lambda _event: self._open_shortcut_runtime_debug_dialog(),
            binding_id="debug.runtime_overlay",
            intent=UiIntent.DEBUG_RUNTIME_OVERLAY,
            modes=(UI_MODE_GLOBAL, UI_MODE_PREVIEW, UI_MODE_DIALOG),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-Shift-o>",
            lambda _event: self._toggle_runtime_offline(),
            binding_id="debug.runtime_offline",
            intent=UiIntent.DEBUG_RUNTIME_OFFLINE,
            modes=(UI_MODE_GLOBAL, UI_MODE_PREVIEW, UI_MODE_DIALOG),
            allow_when_text_input=True,
        )
        self._bind_runtime_shortcut(
            "<Control-z>",
            lambda _event: self._controller.undo(),
            binding_id="global.undo",
            intent=UiIntent.GLOBAL_UNDO,
            modes=(UI_MODE_GLOBAL, UI_MODE_PREVIEW, UI_MODE_DIALOG, UI_MODE_EDITOR),
            # False (not True like most other allow_when_text_input=True shortcuts
            # here, e.g. Escape): a focused text field's own native undo (e.g.
            # WrappedTextField's Text(undo=True)) must win over the app-wide
            # HistoryAction undo, so correcting a typo never silently undoes an
            # unrelated app action instead. evaluate_runtime() then blocks this
            # binding while a text field has focus and _wrapped returns None
            # (not "break"), letting the keystroke reach the widget normally.
            allow_when_text_input=False,
        )
        self._bind_runtime_shortcut(
            "<Control-y>",
            lambda _event: self._controller.redo(),
            binding_id="global.redo",
            intent=UiIntent.GLOBAL_REDO,
            modes=(UI_MODE_GLOBAL, UI_MODE_PREVIEW, UI_MODE_DIALOG, UI_MODE_EDITOR),
            allow_when_text_input=False,
        )
        self._bind_runtime_shortcut(
            "<Control-Left>",
            lambda _event: self._scan_rotate_key(-1),
            binding_id="scan.rotate_ccw",
            intent=UiIntent.SCAN_ROTATE_CCW,
            modes=(UI_MODE_PREVIEW,),
        )
        self._bind_runtime_shortcut(
            "<Control-Right>",
            lambda _event: self._scan_rotate_key(1),
            binding_id="scan.rotate_cw",
            intent=UiIntent.SCAN_ROTATE_CW,
            modes=(UI_MODE_PREVIEW,),
        )
        self._bind_runtime_shortcut(
            "<Control-Shift-Left>",
            lambda _event: self._scan_rotate_quarter_key(-1),
            binding_id="scan.rotate_90_ccw",
            intent=UiIntent.SCAN_ROTATE_90_CCW,
            modes=(UI_MODE_PREVIEW,),
        )
        self._bind_runtime_shortcut(
            "<Control-Shift-Right>",
            lambda _event: self._scan_rotate_quarter_key(1),
            binding_id="scan.rotate_90_cw",
            intent=UiIntent.SCAN_ROTATE_90_CW,
            modes=(UI_MODE_PREVIEW,),
        )
