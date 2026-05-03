from app.adapters.gui.popup_policy import POPUP_KIND_MODAL, PopupPolicy, PopupPolicyRegistry


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
