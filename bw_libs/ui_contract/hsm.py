"""Shared HSM contract primitives for intent, transition, and escape semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

ESCAPE_CLOSE_POPUP = "close_popup"
ESCAPE_EXIT_INLINE_EDITOR = "exit_inline_editor"
ESCAPE_POP_PARENT = "pop_parent"
ESCAPE_ROOT_NOOP = "root_noop"


@dataclass(frozen=True)
class TransitionRule:
    """Declarative transition edge in the UI state graph."""

    from_state: str
    to_state: str


@dataclass(frozen=True)
class HsmIntentSpec:
    """Declarative intent contract with required payload fields."""

    intent: str
    required_payload: tuple[str, ...] = ()


class HsmContract:
    """Central contract validator for intent, transition, and escape semantics."""

    def __init__(
        self,
        *,
        intent_specs: Iterable[HsmIntentSpec],
        transitions: Iterable[TransitionRule],
        escape_priority: tuple[str, ...] = (
            ESCAPE_CLOSE_POPUP,
            ESCAPE_EXIT_INLINE_EDITOR,
            ESCAPE_POP_PARENT,
            ESCAPE_ROOT_NOOP,
        ),
    ) -> None:
        self._intent_specs = {spec.intent: spec for spec in intent_specs}
        self._transition_edges = {(rule.from_state, rule.to_state) for rule in transitions}
        self._escape_priority = escape_priority

    def validate_intent(self, intent: str, payload: dict[str, object] | None = None) -> tuple[bool, str]:
        """Validate that an intent exists and has all required payload fields."""

        spec = self._intent_specs.get(intent)
        if spec is None:
            return False, "unknown-intent"

        payload_dict = payload or {}
        for key in spec.required_payload:
            if key not in payload_dict:
                return False, f"missing-payload:{key}"
        return True, "ok"

    def validate_transition(self, from_state: str, to_state: str) -> tuple[bool, str]:
        """Validate one state transition against the transition registry."""

        if from_state == to_state:
            return True, "stay"
        if (from_state, to_state) in self._transition_edges:
            return True, "ok"
        return False, "transition-forbidden"

    def resolve_escape_action(
        self,
        *,
        has_popup: bool,
        has_inline_editor: bool,
        has_parent_state: bool,
    ) -> str:
        """Resolve centralized escape action with deterministic priority."""

        for action in self._escape_priority:
            if action == ESCAPE_CLOSE_POPUP and has_popup:
                return action
            if action == ESCAPE_EXIT_INLINE_EDITOR and has_inline_editor:
                return action
            if action == ESCAPE_POP_PARENT and has_parent_state:
                return action
            if action == ESCAPE_ROOT_NOOP:
                return action
        return ESCAPE_ROOT_NOOP


def build_ui_hsm_contract(*, intents: Iterable[str]) -> HsmContract:
    """Create a default UI contract with centralized transitions and escape order."""

    specs = [HsmIntentSpec(intent=value) for value in sorted(set(intents))]
    transitions = (
        TransitionRule("global", "preview"),
        TransitionRule("preview", "global"),
        TransitionRule("global", "editor"),
        TransitionRule("editor", "global"),
        TransitionRule("preview", "editor"),
        TransitionRule("editor", "preview"),
        TransitionRule("global", "dialog"),
        TransitionRule("preview", "dialog"),
        TransitionRule("editor", "dialog"),
        TransitionRule("dialog", "global"),
        TransitionRule("dialog", "preview"),
        TransitionRule("dialog", "editor"),
        TransitionRule("global", "offline"),
        TransitionRule("preview", "offline"),
        TransitionRule("editor", "offline"),
        TransitionRule("dialog", "offline"),
        TransitionRule("offline", "global"),
        TransitionRule("offline", "preview"),
        TransitionRule("offline", "editor"),
        TransitionRule("offline", "dialog"),
    )
    return HsmContract(intent_specs=specs, transitions=transitions)


# Bridge target is mandatory in Wave-3; no local fallback branch remains.
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
