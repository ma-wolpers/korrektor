"""Builds LaufKern manifests from Korrektor runtime shortcut registry state."""

from __future__ import annotations

from bw_libs.ui_contract.keybinding import KeybindingRegistry
from bw_libs.ui_contract.laufkern import LaufKernRoute, build_manifest


def build_runtime_shortcut_manifest(registry: KeybindingRegistry):
    """Build one declarative manifest from current runtime shortcut registrations."""

    definitions = registry.all()
    intents = tuple(sorted({definition.intent for definition in definitions}))
    routes = tuple(
        LaufKernRoute(
            route_id=f"shortcut.{definition.binding_id}",
            intent=definition.intent,
            route_type="shortcut",
            modes=tuple(definition.modes),
            binding_id=definition.binding_id,
            metadata={"sequence": definition.sequence},
        )
        for definition in definitions
    )
    return build_manifest(
        manifest_id="korrektor.shortcuts.runtime",
        repo_name="korrektor",
        intents=intents,
        routes=routes,
        keybinding_registry=registry,
        metadata={"provider": "korrektor.app.adapters.gui.laufkern_manifest_provider"},
    )
