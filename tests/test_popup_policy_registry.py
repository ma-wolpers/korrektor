from app.adapters.gui.popup_policy import POPUP_KIND_MODAL, POPUP_KIND_NON_MODAL, PopupPolicy, PopupPolicyRegistry


def test_popup_registry_lifecycle() -> None:
    registry = PopupPolicyRegistry()
    registry.register_policy(PopupPolicy(policy_id="dialog.modal", kind=POPUP_KIND_MODAL))

    registry.open_popup("debug", "Shortcut Runtime Debug", "dialog.modal")
    registry.open_popup("extra", "Extraseiten", "dialog.modal")

    assert registry.has_active_popup() is True
    assert registry.active_popup() is not None
    assert registry.active_popup().popup_id == "extra"

    assert registry.close_popup("extra") is True
    assert registry.active_popup() is not None
    assert registry.active_popup().popup_id == "debug"

    registry.close_all()
    assert registry.has_active_popup() is False
    assert registry.active_popup() is None


def test_mode_blocking_popup_respects_policy_flag() -> None:
    registry = PopupPolicyRegistry()
    registry.register_policy(PopupPolicy(policy_id="dialog.modal", kind=POPUP_KIND_MODAL))
    registry.register_policy(
        PopupPolicy(
            policy_id="dialog.non_blocking",
            kind=POPUP_KIND_NON_MODAL,
            affects_mode=False,
            trap_focus=False,
        )
    )

    registry.open_popup("runtime", "Runtime", "dialog.non_blocking")
    assert registry.has_active_popup() is True
    assert registry.has_mode_blocking_popup() is False

    registry.open_popup("modal", "Modal", "dialog.modal")
    assert registry.has_mode_blocking_popup() is True
