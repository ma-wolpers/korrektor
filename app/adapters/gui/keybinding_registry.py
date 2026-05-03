"""Central keybinding registry with mode-aware activation rules."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Iterable

UI_MODE_GLOBAL = "global"
UI_MODE_EDITOR = "editor"
UI_MODE_PREVIEW = "preview"
UI_MODE_DIALOG = "dialog"
UI_MODE_OFFLINE = "offline"


@dataclass(frozen=True)
class KeyBindingDefinition:
    """Declarative keybinding contract used across all apps."""

    binding_id: str
    sequence: str
    intent: str
    modes: tuple[str, ...] = (UI_MODE_GLOBAL,)
    description: str = ""
    allow_modifiers: bool = False
    allow_when_text_input: bool = False
    allow_when_offline: bool = True
    metadata: dict[str, str] = field(default_factory=dict)
    handler: Callable[[], None] | None = field(default=None, repr=False, compare=False)


class KeybindingRegistry:
    """Stores keybindings centrally and exposes mode/diagnostic views."""

    def __init__(self) -> None:
        self._bindings: list[KeyBindingDefinition] = []
        self._by_id: dict[str, KeyBindingDefinition] = {}

    def register(self, definition: KeyBindingDefinition) -> None:
        """Register one keybinding and reject duplicate binding ids."""
        if definition.binding_id in self._by_id:
            raise ValueError(f"Duplicate keybinding id: {definition.binding_id}")
        self._bindings.append(definition)
        self._by_id[definition.binding_id] = definition

    def register_many(self, definitions: Iterable[KeyBindingDefinition]) -> None:
        """Register multiple keybindings preserving declaration order."""
        for definition in definitions:
            self.register(definition)

    def all(self) -> tuple[KeyBindingDefinition, ...]:
        """Return all keybindings in registry order."""
        return tuple(self._bindings)

    def active_for_mode(
        self,
        mode: str,
        *,
        offline: bool,
        text_input_focused: bool,
    ) -> tuple[KeyBindingDefinition, ...]:
        """Return active keybindings for one mode and runtime context."""
        active: list[KeyBindingDefinition] = []
        for definition in self._bindings:
            if mode not in definition.modes and UI_MODE_GLOBAL not in definition.modes:
                continue
            if offline and not definition.allow_when_offline:
                continue
            if text_input_focused and not definition.allow_when_text_input:
                continue
            active.append(definition)
        return tuple(active)

    def conflicts(self) -> dict[str, list[str]]:
        """List sequence collisions per mode (sequence -> binding ids)."""
        collisions: dict[str, list[str]] = {}
        usage: dict[tuple[str, str], list[str]] = defaultdict(list)
        for definition in self._bindings:
            for mode in definition.modes:
                usage[(mode, definition.sequence)].append(definition.binding_id)
        for (mode, sequence), binding_ids in usage.items():
            if len(binding_ids) > 1:
                collisions[f"{mode}:{sequence}"] = sorted(binding_ids)
        return collisions

    def mode_manifest(self) -> dict[str, list[str]]:
        """Expose a compact mode -> binding id overview for audit/help UIs."""
        manifest: dict[str, list[str]] = defaultdict(list)
        for definition in self._bindings:
            for mode in definition.modes:
                manifest[mode].append(definition.binding_id)
        return {mode: values for mode, values in sorted(manifest.items())}
