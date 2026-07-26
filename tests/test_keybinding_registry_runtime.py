from bw_gui.contracts.keybinding import (
    UI_MODE_DIALOG,
    UI_MODE_EDITOR,
    UI_MODE_GLOBAL,
    UI_MODE_PREVIEW,
    KeyBindingDefinition,
    KeybindingRegistry,
    KeybindingRuntimeContext,
)


def test_runtime_evaluation_returns_blocking_reasons() -> None:
    registry = KeybindingRegistry()
    definition = KeyBindingDefinition(
        binding_id="global.open",
        sequence="<Control-o>",
        intent="global.open",
        modes=(UI_MODE_GLOBAL,),
        allow_when_text_input=False,
        allow_when_offline=False,
    )
    dialog_definition = KeyBindingDefinition(
        binding_id="dialog.ok",
        sequence="<Return>",
        intent="dialog.ok",
        modes=(UI_MODE_DIALOG,),
        allow_when_text_input=True,
    )
    preview_definition = KeyBindingDefinition(
        binding_id="preview.navigate",
        sequence="<Right>",
        intent="preview.navigate",
        modes=(UI_MODE_PREVIEW,),
        allow_when_text_input=False,
    )
    registry.register(definition)
    registry.register(dialog_definition)
    registry.register(preview_definition)

    can_execute, reason = registry.evaluate_runtime(
        definition,
        KeybindingRuntimeContext(active_mode=UI_MODE_EDITOR, text_input_focused=True),
    )
    assert can_execute is False
    assert reason == "text-input-focus"

    can_execute, reason = registry.evaluate_runtime(
        definition,
        KeybindingRuntimeContext(active_mode=UI_MODE_PREVIEW, offline=True),
    )
    assert can_execute is False
    assert reason == "offline-disabled"

    can_execute, reason = registry.evaluate_runtime(
        preview_definition,
        KeybindingRuntimeContext(active_mode=UI_MODE_PREVIEW, dialog_open=True),
    )
    assert can_execute is False
    assert reason == "dialog-priority"

    can_execute, reason = registry.evaluate_runtime(
        dialog_definition,
        KeybindingRuntimeContext(active_mode=UI_MODE_DIALOG, dialog_open=True),
    )
    assert can_execute is True
    assert reason == "active"
