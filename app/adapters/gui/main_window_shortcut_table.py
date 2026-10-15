from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.gui.ui_intents import UiIntent
from bw_gui.contracts.key_spec import KeySpec
from bw_gui.contracts.keybinding import UI_MODE_DIALOG, UI_MODE_EDITOR, UI_MODE_GLOBAL, UI_MODE_PREVIEW

if TYPE_CHECKING:
    from app.adapters.gui.ui_intent_controller import UiIntentController

_k = KeySpec.parse
_ALL = (UI_MODE_GLOBAL, UI_MODE_PREVIEW, UI_MODE_DIALOG)
_ALL_EDITOR = (UI_MODE_GLOBAL, UI_MODE_PREVIEW, UI_MODE_DIALOG, UI_MODE_EDITOR)
_DETAIL = (UI_MODE_PREVIEW, UI_MODE_EDITOR)


class MainWindowShortcutTableMixin:
    """The declarative table of main-window shortcuts (moved out of `main_window_shortcuts.py`, file-size rule).

    `main_window_shortcuts.py` keeps the runtime mechanics (binder, gating sources,
    LaufKern tracking); this mixin only declares which key triggers which intent in
    which modes. Keys are ``KeySpec``s in canonical notation (``KeySpec.parse``).

    Modifiers are exact (bw-gui keyboard contract): the former ``bind_all``
    sequences also fired with extra held modifiers (Tk's minimum-set matching, e.g.
    Alt+← ran ``<Left>``); now only the declared combination fires. Named keys
    tolerate Shift where no own Shift variant exists (Escape, ↑/↓, Ctrl+Space,
    Delete), as Shift+Escape etc. did before. Letters follow Shift, never CapsLock
    (``<Control-Shift-d>`` used to fire only with CapsLock on); the keypad
    ``+``/``-`` are the same characters as the main keys.
    """

    def set_controller(self, controller: "UiIntentController") -> None:
        """Attach the controller and register every main-window shortcut (key -> intent, allowed UI modes)."""
        self._controller = controller
        self._init_shortcut_binder()
        b = self._bind_runtime_shortcut
        b(_k("Ctrl+N"), lambda _e: self._controller.create_exam(), binding_id="global.new_exam",
          intent=UiIntent.GLOBAL_CREATE_EXAM, modes=(UI_MODE_GLOBAL, UI_MODE_DIALOG), allow_when_text_input=True)
        b(_k("Escape (tolerate: Shift)"), self._on_escape, binding_id="global.escape",
          intent=UiIntent.GLOBAL_ESCAPE, modes=_ALL, allow_when_text_input=True)
        b(_k("Left"), self._on_left_key, binding_id="detail.left",
          intent=UiIntent.DETAIL_NAVIGATE_LEFT, modes=_DETAIL, allow_when_text_input=True)
        b(_k("Right"), self._on_right_key, binding_id="detail.right",
          intent=UiIntent.DETAIL_NAVIGATE_RIGHT, modes=_DETAIL, allow_when_text_input=True)
        b(_k("Up (tolerate: Shift)"), self._on_up_key, binding_id="detail.up",
          intent=UiIntent.DETAIL_NAVIGATE_UP, modes=_DETAIL, allow_when_text_input=True)
        b(_k("Down (tolerate: Shift)"), self._on_down_key, binding_id="detail.down",
          intent=UiIntent.DETAIL_NAVIGATE_DOWN, modes=_DETAIL, allow_when_text_input=True)
        b(_k("Ctrl+Up"), self._on_ctrl_up_key, binding_id="detail.ctrl_up",
          intent=UiIntent.DETAIL_NAVIGATE_CTRL_UP, modes=_DETAIL, allow_when_text_input=True)
        b(_k("Ctrl+Down"), self._on_ctrl_down_key, binding_id="detail.ctrl_down",
          intent=UiIntent.DETAIL_NAVIGATE_CTRL_DOWN, modes=_DETAIL, allow_when_text_input=True)
        # Symbol letters, digits -> points field, Space ("Fertig") and Ctrl+Space ("alle fertig"):
        # never in the comment field (see `main_window_correction_keys.py`).
        self._register_correction_hotkeys(b)
        b(_k("Ctrl+E"), self._on_ctrl_e_key, binding_id="global.export",
          intent=UiIntent.GLOBAL_EXPORT, modes=_ALL_EDITOR, allow_when_text_input=True)
        b([_k("Ctrl++"), _k("Ctrl+=")], self._on_ctrl_plus_key, binding_id="correction.zoom_in",
          intent=UiIntent.CORRECTION_ZOOM_IN, modes=_DETAIL, allow_when_text_input=True)
        b(_k("Ctrl+-"), self._on_ctrl_minus_key, binding_id="correction.zoom_out",
          intent=UiIntent.CORRECTION_ZOOM_OUT, modes=_DETAIL, allow_when_text_input=True)
        b(_k("Ctrl+0"), self._on_ctrl_zero_key, binding_id="correction.zoom_reset",
          intent=UiIntent.CORRECTION_ZOOM_RESET, modes=_DETAIL, allow_when_text_input=True)
        b(_k("Ctrl+C"), self._on_ctrl_c_key, binding_id="correction.copy_annotation",
          intent=UiIntent.CORRECTION_COPY_ANNOTATION, modes=_DETAIL)
        b(_k("Ctrl+X"), self._on_ctrl_x_key, binding_id="correction.cut_annotation",
          intent=UiIntent.CORRECTION_CUT_ANNOTATION, modes=_DETAIL)
        b(_k("Ctrl+V"), self._on_ctrl_v_key, binding_id="correction.paste_annotation",
          intent=UiIntent.CORRECTION_PASTE_ANNOTATION, modes=_DETAIL)
        b(_k("Ctrl+Shift+D"), lambda _e: self._open_shortcut_runtime_debug_dialog(), binding_id="debug.runtime_overlay",
          intent=UiIntent.DEBUG_RUNTIME_OVERLAY, modes=_ALL, allow_when_text_input=True)
        b(_k("Ctrl+Shift+O"), lambda _e: self._toggle_runtime_offline(), binding_id="debug.runtime_offline",
          intent=UiIntent.DEBUG_RUNTIME_OFFLINE, modes=_ALL, allow_when_text_input=True)
        # allow_when_text_input=False (not True like most others here, e.g. Escape): a
        # focused text field's own native undo (e.g. WrappedTextField's Text(undo=True))
        # must win over the app-wide HistoryAction undo, so correcting a typo never
        # silently undoes an unrelated app action. The binder then blocks this binding
        # while a text field has focus (NOT_HANDLED), so the keystroke stays the widget's.
        b(_k("Ctrl+Z"), lambda _e: self._controller.undo(), binding_id="global.undo",
          intent=UiIntent.GLOBAL_UNDO, modes=_ALL_EDITOR, allow_when_text_input=False)
        b(_k("Ctrl+Y"), lambda _e: self._controller.redo(), binding_id="global.redo",
          intent=UiIntent.GLOBAL_REDO, modes=_ALL_EDITOR, allow_when_text_input=False)
        b(_k("Ctrl+Left"), lambda _e: self._scan_rotate_key(-1), binding_id="scan.rotate_ccw",
          intent=UiIntent.SCAN_ROTATE_CCW, modes=(UI_MODE_PREVIEW,))
        b(_k("Ctrl+Right"), lambda _e: self._scan_rotate_key(1), binding_id="scan.rotate_cw",
          intent=UiIntent.SCAN_ROTATE_CW, modes=(UI_MODE_PREVIEW,))
        # Shift+←/→ = 90° in the Scan-Werkstatt; in every other view they keep the
        # plain ←/→ behaviour (same modes as Left/Right, see `_on_shift_arrow_key`).
        b(_k("Shift+Left"), lambda event: self._on_shift_arrow_key(-1, event), binding_id="scan.rotate_90_ccw",
          intent=UiIntent.SCAN_ROTATE_90_CCW, modes=_DETAIL, allow_when_text_input=True)
        b(_k("Shift+Right"), lambda event: self._on_shift_arrow_key(1, event), binding_id="scan.rotate_90_cw",
          intent=UiIntent.SCAN_ROTATE_90_CW, modes=_DETAIL, allow_when_text_input=True)
        for notation, steps, binding_id, intent in (
            ("Ctrl+Shift+Left", (-1, 0), "scan.shift_left", UiIntent.SCAN_SHIFT_LEFT),
            ("Ctrl+Shift+Right", (1, 0), "scan.shift_right", UiIntent.SCAN_SHIFT_RIGHT),
            ("Ctrl+Shift+Up", (0, -1), "scan.shift_up", UiIntent.SCAN_SHIFT_UP),
            ("Ctrl+Shift+Down", (0, 1), "scan.shift_down", UiIntent.SCAN_SHIFT_DOWN),
        ):
            b(_k(notation), lambda _e, steps=steps: self._scan_shift_key(*steps), binding_id=binding_id,
              intent=intent, modes=(UI_MODE_PREVIEW,))
        # Entf was a raw, ungated bind_all; GLOBAL keeps it active in every mode and
        # dialog (the handler itself checks text input and the active view).
        b(_k("Delete (tolerate: Shift)"), self._on_delete_region_key, binding_id="detail.delete",
          intent=UiIntent.DETAIL_DELETE, modes=(UI_MODE_GLOBAL,), allow_when_text_input=True)
