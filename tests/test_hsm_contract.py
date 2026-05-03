from bw_libs.ui_contract.hsm import (
    ESCAPE_CLOSE_POPUP,
    ESCAPE_EXIT_INLINE_EDITOR,
    ESCAPE_POP_PARENT,
    ESCAPE_ROOT_NOOP,
    HsmIntentSpec,
    HsmContract,
    TransitionRule,
)


def test_hsm_contract_validates_intent_and_required_payload() -> None:
    contract = HsmContract(
        intent_specs=(
            HsmIntentSpec(intent="view.open"),
            HsmIntentSpec(intent="cell.edit", required_payload=("row", "col")),
        ),
        transitions=(TransitionRule("global", "preview"),),
    )

    ok, reason = contract.validate_intent("view.open")
    assert ok is True
    assert reason == "ok"

    ok, reason = contract.validate_intent("cell.edit", payload={"row": 2})
    assert ok is False
    assert reason == "missing-payload:col"


def test_hsm_contract_validates_transitions() -> None:
    contract = HsmContract(
        intent_specs=(HsmIntentSpec(intent="noop"),),
        transitions=(TransitionRule("global", "preview"),),
    )

    ok, reason = contract.validate_transition("global", "preview")
    assert ok is True
    assert reason == "ok"

    ok, reason = contract.validate_transition("preview", "dialog")
    assert ok is False
    assert reason == "transition-forbidden"


def test_hsm_contract_escape_priority() -> None:
    contract = HsmContract(
        intent_specs=(HsmIntentSpec(intent="noop"),),
        transitions=(),
    )

    assert (
        contract.resolve_escape_action(has_popup=True, has_inline_editor=True, has_parent_state=True)
        == ESCAPE_CLOSE_POPUP
    )
    assert (
        contract.resolve_escape_action(has_popup=False, has_inline_editor=True, has_parent_state=True)
        == ESCAPE_EXIT_INLINE_EDITOR
    )
    assert (
        contract.resolve_escape_action(has_popup=False, has_inline_editor=False, has_parent_state=True)
        == ESCAPE_POP_PARENT
    )
    assert (
        contract.resolve_escape_action(has_popup=False, has_inline_editor=False, has_parent_state=False)
        == ESCAPE_ROOT_NOOP
    )
