from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.gui.ui_intents import UiIntent
from app.adapters.gui.laufkern_manifest_provider import build_runtime_shortcut_manifest
from bw_gui.contracts.keybinding import (
    UI_MODE_DIALOG,
    UI_MODE_EDITOR,
    UI_MODE_GLOBAL,
    UI_MODE_OFFLINE,
    UI_MODE_PREVIEW,
    KeyBindingDefinition,
    KeybindingRuntimeContext,
)
from bw_gui.laufkern import aggregate_completion, emit_tracking_artifact, verify_manifest, verify_reachability

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ui, widgets

if TYPE_CHECKING:
    from app.adapters.gui.ui_intent_controller import UiIntentController


class MainWindowShortcutsMixin:
    def set_controller(self, controller: "UiIntentController") -> None:
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

    def start(self) -> None:
        if self._controller:
            self._controller.refresh_exam_overview()

    def _register_runtime_shortcut(
        self,
        *,
        binding_id: str,
        sequence: str,
        intent: str,
        modes: tuple[str, ...],
        allow_when_text_input: bool = False,
        allow_when_offline: bool = True,
    ) -> KeyBindingDefinition:
        """Register one runtime shortcut definition in the central resolver."""

        intent_ok, _intent_reason = self._hsm_contract.validate_intent(intent)
        if not intent_ok:
            raise ValueError(f"Unknown runtime shortcut intent: {intent}")

        definition = KeyBindingDefinition(
            binding_id=binding_id,
            sequence=sequence,
            intent=intent,
            modes=modes,
            allow_when_text_input=allow_when_text_input,
            allow_when_offline=allow_when_offline,
        )
        self._runtime_shortcuts.register(definition)
        return definition

    def _sync_popup_sessions_from_windows(self) -> None:
        """Synchronize popup registry with currently visible toplevel windows."""

        visible_popup_ids: set[str] = set()
        for child in self.root.winfo_children():
            if not isinstance(child, ui.Toplevel):
                continue
            try:
                if not int(child.winfo_exists()):
                    continue
                if str(child.state()).lower() == "withdrawn":
                    continue
            except Exception:
                continue

            popup_id = str(child)
            visible_popup_ids.add(popup_id)
            if popup_id in self._tracked_popup_ids:
                continue
            title = ""
            try:
                title = str(child.title() or "")
            except Exception:
                title = ""
            self._popup_registry.open_popup(popup_id=popup_id, title=title, policy_id="dialog.modal")
            self._tracked_popup_ids.add(popup_id)

        stale_ids = self._tracked_popup_ids - visible_popup_ids
        for popup_id in tuple(stale_ids):
            self._popup_registry.close_popup(popup_id)
            self._tracked_popup_ids.discard(popup_id)

    def _register_popup_window(self, window: ui.Toplevel, *, policy_id: str = "dialog.modal") -> None:
        """Register popup window immediately in popup policy registry."""

        popup_id = str(window)
        if popup_id in self._tracked_popup_ids:
            return
        self._popup_registry.open_popup(popup_id=popup_id, title=str(window.title() or ""), policy_id=policy_id)
        self._tracked_popup_ids.add(popup_id)

    @staticmethod
    def _is_editable_widget(widget) -> bool:
        if widget is None:
            return False
        return isinstance(widget, (ui.Entry, widgets.Entry, ui.Text, widgets.Combobox, ui.Spinbox))

    def _build_runtime_context(self, event: ui.Event[ui.Misc] | None = None) -> KeybindingRuntimeContext:
        """Build runtime context for evaluating keybinding execution."""

        self._sync_popup_sessions_from_windows()
        focused_widget = getattr(event, "widget", None) or self.root.focus_get()
        text_input_focused = self._is_editable_widget(focused_widget)
        dialog_open = self._popup_registry.has_mode_blocking_popup()
        offline = bool(self._shortcut_debug_offline_var.get())

        if offline:
            active_mode = UI_MODE_OFFLINE
        elif dialog_open:
            active_mode = UI_MODE_DIALOG
        elif text_input_focused:
            active_mode = UI_MODE_EDITOR
        elif self._current_exam is not None:
            active_mode = UI_MODE_PREVIEW
        else:
            active_mode = UI_MODE_GLOBAL

        return KeybindingRuntimeContext(
            active_mode=active_mode,
            offline=offline,
            text_input_focused=text_input_focused,
            dialog_open=dialog_open,
        )

    def _bind_runtime_shortcut(
        self,
        sequence: str,
        handler,
        *,
        binding_id: str,
        intent: str,
        modes: tuple[str, ...],
        allow_when_text_input: bool = False,
        allow_when_offline: bool = True,
    ) -> None:
        """Bind one shortcut through the runtime resolver."""

        definition = self._register_runtime_shortcut(
            binding_id=binding_id,
            sequence=sequence,
            intent=intent,
            modes=modes,
            allow_when_text_input=allow_when_text_input,
            allow_when_offline=allow_when_offline,
        )

        def _wrapped(event):
            context = self._build_runtime_context(event)
            can_execute, _reason = self._runtime_shortcuts.evaluate_runtime(definition, context)
            if not can_execute:
                return None
            try:
                result = handler(event)
            except Exception:
                self._record_laufkern_intent_dispatch(intent, success=False)
                raise

            self._record_laufkern_intent_dispatch(intent, success=True)
            return result

        self.root.bind_all(sequence, _wrapped)

    def _build_laufkern_manifest(self):
        """Build one declarative LaufKern manifest from registered runtime shortcuts."""

        return build_runtime_shortcut_manifest(self._runtime_shortcuts)

    def _summarize_laufkern_reachability(self, *, context: KeybindingRuntimeContext) -> str:
        """Return compact LaufKern reachability summary for current runtime state."""

        manifest = self._build_laufkern_manifest()
        manifest_ok, manifest_errors = verify_manifest(manifest)
        if not manifest_ok:
            return f"LaufKern manifest-errors={len(manifest_errors)}"

        results = verify_reachability(manifest=manifest, context=context)
        reachable = sum(1 for result in results if result.reachable)
        return f"LaufKern intents {reachable}/{len(results)} erreichbar"

    def _laufkern_step_id_for_intent(self, intent: str) -> str:
        """Return stable runtime-tracking step id for one intent during this session."""

        existing = self._laufkern_tracking_step_ids.get(intent)
        if existing is not None:
            return existing

        next_index = len(self._laufkern_tracking_step_ids) + 1
        step_id = f"LK-D-RTC-{next_index:03d}"
        self._laufkern_tracking_step_ids[intent] = step_id
        return step_id

    def _record_laufkern_intent_dispatch(self, intent: str, *, success: bool) -> None:
        """Record runtime intent dispatch result as LaufKern tracking artifact."""

        self._laufkern_tracking_sequence += 1
        artifact = emit_tracking_artifact(
            run_id=self._laufkern_tracking_run_id,
            repo_name="korrektor",
            step_id=self._laufkern_step_id_for_intent(intent),
            phase="D",
            state="done" if success else "failed",
            sequence=self._laufkern_tracking_sequence,
            mandatory=True,
            producer="laufkern-runtime",
            evidence_ref=intent,
        )
        self._laufkern_tracking_artifacts.append(artifact)

    def _summarize_laufkern_completion(self) -> str:
        """Return compact completion status summary from tracked runtime artifacts."""

        if not self._laufkern_tracking_artifacts:
            return "LK completion n/a"

        summary = aggregate_completion(
            self._laufkern_tracking_artifacts,
            trusted_producers={"laufkern-runtime"},
        )
        return f"LK completion {summary.status} {summary.completed_steps}/{summary.mandatory_steps}"

    def _toggle_runtime_offline(self) -> None:
        """Toggle offline simulation for runtime shortcut diagnostics."""

        self._shortcut_debug_offline_var.set(not bool(self._shortcut_debug_offline_var.get()))
        self._refresh_shortcut_runtime_debug_dialog()
