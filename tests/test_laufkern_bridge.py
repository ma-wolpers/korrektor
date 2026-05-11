from bw_libs.ui_contract import (
    LaufKernManifest,
    LaufKernRoute,
    build_manifest,
    evaluate_intent_routes,
)
from bw_libs.ui_contract.keybinding import KeyBindingDefinition, KeybindingRuntimeContext


def test_laufkern_bridge_manifest_and_reachability():
    manifest = build_manifest(
        manifest_id="blattwerk.test",
        repo_name="blattwerk",
        intents=("open",),
        keybindings=(
            KeyBindingDefinition(
                binding_id="global.open",
                sequence="<Control-o>",
                intent="open",
            ),
        ),
        routes=(
            LaufKernRoute(
                route_id="route.open.shortcut",
                intent="open",
                route_type="shortcut",
                binding_id="global.open",
            ),
        ),
    )

    assert isinstance(manifest, LaufKernManifest)

    result = evaluate_intent_routes(
        manifest=manifest,
        intent="open",
        context=KeybindingRuntimeContext(active_mode="global"),
    )

    assert result.reachable is True
