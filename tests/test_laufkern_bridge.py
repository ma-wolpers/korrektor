from bw_gui.contracts.key_spec import KeySpec
from bw_gui.contracts.keybinding import KeyBindingDefinition, KeybindingRuntimeContext
from bw_gui.laufkern import (
    LaufKernManifest,
    LaufKernRoute,
    build_manifest,
    evaluate_intent_routes,
)


def test_laufkern_bridge_manifest_and_reachability():
    manifest = build_manifest(
        manifest_id="blattwerk.test",
        repo_name="blattwerk",
        intents=("open",),
        keybindings=(
            KeyBindingDefinition(
                binding_id="global.open",
                keys=(KeySpec.parse("Ctrl+O"),),
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
