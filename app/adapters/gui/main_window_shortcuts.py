from __future__ import annotations

from collections.abc import Iterable

from app.adapters.gui.laufkern_manifest_provider import build_runtime_shortcut_manifest
from bw_gui.contracts.key_spec import KeySpec
from bw_gui.contracts.keybinding import (
    UI_MODE_GLOBAL,
    UI_MODE_PREVIEW,
    KeyBindingDefinition,
    KeybindingRuntimeContext,
)
from bw_gui.laufkern import aggregate_completion, emit_tracking_artifact, verify_manifest, verify_reachability

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

ensure_bw_gui_on_path()
from bw_gui.runtime import ApplicationShortcutBinder, ui, widgets
from bw_gui.runtime.overlay_stack import OverlayCategory, blocking, register_overlay


class MainWindowShortcutsMixin:
    """Runtime mechanics of main-window shortcuts: binder, gating sources, popup gating, LaufKern tracking.

    The declarative shortcut table lives in `MainWindowShortcutTableMixin` (`main_window_shortcut_table.py`).
    """

    def start(self) -> None:
        if self._controller:
            self._controller.refresh_exam_overview()

    def _init_shortcut_binder(self) -> None:
        """Create the single application-wide shortcut binder (bw-gui ``all`` router).

        Replaces the former ``bind_all`` registrations: the binder sits where
        ``bind_all`` sat (after widget, class and toplevel bindtags), so popup
        overrides on a toplevel still win. Gating: mode from the open exam (PREVIEW
        with an exam, GLOBAL without), dialogs from the bw-gui overlay stack, text input
        from bw-gui's text-input contract, offline simulation from the debug toggle.
        """
        self._shortcut_binder = ApplicationShortcutBinder(
            self.root,
            registry=self._runtime_shortcuts,
            hsm_contract=self._hsm_contract,
            dialog_open=self._shortcut_dialog_open,
            offline=lambda: bool(self._shortcut_debug_offline_var.get()),
            mode_provider=lambda: UI_MODE_PREVIEW if self._current_exam is not None else UI_MODE_GLOBAL,
            on_dispatch=self._record_laufkern_intent_dispatch,
        )

    def _shortcut_dialog_open(self) -> bool:
        """Report whether a blocking overlay is open (bw-gui overlay stack, ``blocking(include_menus=True)``).

        Modal popups (``ScrollablePopupWindow`` registers itself; raw popups via
        :meth:`_register_popup_window`) and menu popups block the guide shortcuts; the
        shortcut debug window registers as non-modal and does not. This reproduces the
        former scan, which counted every visible direct child toplevel of the root
        (menu popups included) unless it had been registered as non-blocking
        (``tests/test_overlay_gating_tk.py``).
        """
        return blocking(self.root, include_menus=True)()

    def _register_popup_window(self, window: ui.Toplevel, *, blocking_shortcuts: bool = True) -> None:
        """Register a raw ``Toplevel`` popup of the main window in the bw-gui overlay stack.

        ``ScrollablePopupWindow`` registers itself; this is for plain toplevels (naming,
        import split, extra pages, shortcut debug). The registration ends with the
        window's ``<Destroy>``.

        Args:
            blocking_shortcuts: ``True`` (default) registers a ``MODAL_DIALOG`` that blocks
                the main window's shortcuts while open; ``False`` a ``NON_MODAL_POPUP``
                tool window that does not.
        """
        category = OverlayCategory.MODAL_DIALOG if blocking_shortcuts else OverlayCategory.NON_MODAL_POPUP
        register_overlay(window, category, toplevel=window)

    @staticmethod
    def _is_editable_widget(widget) -> bool:
        if widget is None:
            return False
        return isinstance(widget, (ui.Entry, widgets.Entry, ui.Text, widgets.Combobox, ui.Spinbox))

    def _bind_runtime_shortcut(
        self,
        keys: KeySpec | Iterable[KeySpec],
        handler,
        *,
        binding_id: str,
        intent: str,
        modes: tuple[str, ...],
        allow_when_text_input: bool = False,
        allow_when_offline: bool = True,
        description: str = "",
        applies_when=None,
    ) -> KeyBindingDefinition:
        """Register one application shortcut (thin delegation to the binder).

        Args:
            keys: One ``KeySpec`` or several alternative specs of the same definition.
            handler: ``handler(KeyEvent) -> EventResult | None``; ``None`` lets the
                key event continue (menu mnemonics, Tk defaults).
            binding_id: Unique binding id.
            intent: ``UiIntent`` (must be known to the HSM contract).
            modes: Allowed UI modes.
            allow_when_text_input: Also active while a text input has the focus.
            allow_when_offline: Also active in the offline simulation.
            description: Text for the shortcut diagnostics.
            applies_when: Optional ``applies_when(KeyEvent) -> bool``; ``False`` lets
                the key continue unhandled (e.g. Space on a focused button).

        Returns:
            The registered definition (registry, debug dialog, LaufKern manifest).
        """
        return self._shortcut_binder.bind(
            keys,
            handler,
            binding_id=binding_id,
            intent=intent,
            modes=modes,
            allow_when_text_input=allow_when_text_input,
            allow_when_offline=allow_when_offline,
            description=description,
            applies_when=applies_when,
        ).definition

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
