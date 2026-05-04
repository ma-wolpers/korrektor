"""Central popup policy primitives with consistent lifecycle behavior."""

from __future__ import annotations

from dataclasses import dataclass

POPUP_KIND_MODAL = "modal"
POPUP_KIND_NON_MODAL = "non_modal"


@dataclass(frozen=True)
class PopupPolicy:
    """Declarative policy for popup behavior and UX guarantees."""

    policy_id: str
    kind: str = POPUP_KIND_MODAL
    close_on_escape: bool = True
    trap_focus: bool = True
    affects_mode: bool = True
    require_close_confirmation: bool = False
    design_variant: str = "default"


@dataclass(frozen=True)
class PopupSession:
    """Runtime popup registration entry."""

    popup_id: str
    title: str
    policy_id: str


class PopupPolicyRegistry:
    """Tracks popup policies and currently open popup stack."""

    def __init__(self) -> None:
        self._policies: dict[str, PopupPolicy] = {}
        self._stack: list[PopupSession] = []

    def register_policy(self, policy: PopupPolicy) -> None:
        """Register one popup policy and reject duplicate ids."""
        if policy.policy_id in self._policies:
            raise ValueError(f"Duplicate popup policy id: {policy.policy_id}")
        self._policies[policy.policy_id] = policy

    def policy(self, policy_id: str) -> PopupPolicy:
        """Resolve a policy by id."""
        return self._policies[policy_id]

    def open_popup(self, popup_id: str, title: str, policy_id: str) -> PopupSession:
        """Push popup onto active stack and return its session object."""
        if policy_id not in self._policies:
            raise KeyError(f"Unknown popup policy id: {policy_id}")
        session = PopupSession(popup_id=popup_id, title=title, policy_id=policy_id)
        self._stack.append(session)
        return session

    def close_popup(self, popup_id: str) -> bool:
        """Close popup by id and return True when one was removed."""
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index].popup_id == popup_id:
                self._stack.pop(index)
                return True
        return False

    def active_popup(self) -> PopupSession | None:
        """Return top-most popup in stack order."""
        if not self._stack:
            return None
        return self._stack[-1]

    def has_active_popup(self) -> bool:
        """Shortcut for active popup check."""
        return bool(self._stack)

    def has_mode_blocking_popup(self) -> bool:
        """Return whether at least one active popup should switch runtime mode to dialog."""

        for session in self._stack:
            policy = self._policies.get(session.policy_id)
            if policy is None:
                continue
            if policy.kind == POPUP_KIND_MODAL and policy.affects_mode:
                return True
        return False

    def close_all(self) -> None:
        """Close all tracked popups."""
        self._stack.clear()

    def popup_manifest(self) -> dict[str, object]:
        """Return policy and stack summaries for diagnostics/help views."""
        return {
            "policies": sorted(self._policies.keys()),
            "active_stack": [session.popup_id for session in self._stack],
        }


# Pilot bridge: resolve shared bw-gui contracts while preserving local import paths.
try:
    from bw_libs.shared_gui_core import ensure_bw_gui_on_path as _ensure_bw_gui_on_path

    _ensure_bw_gui_on_path()

    from bw_gui.contracts.popup import (  # type: ignore[assignment]
        POPUP_KIND_MODAL,
        POPUP_KIND_NON_MODAL,
        PopupPolicy,
        PopupPolicyRegistry,
        PopupSession,
    )
except ModuleNotFoundError:
    # Keep local fallback contracts usable when shared core is unavailable.
    pass
