from __future__ import annotations

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


class MainWindowShortcutsMixin:
    """Runtime mechanics of main-window shortcuts: registry, context, gating, popup sync, LaufKern tracking.

    The declarative shortcut table lives in `MainWindowShortcutTableMixin` (`main_window_shortcut_table.py`).
    """

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
