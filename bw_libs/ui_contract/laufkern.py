"""LaufKern contract bridge with local fallback for offline/shared-unavailable runs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import re

from bw_libs.ui_contract.keybinding import KeyBindingDefinition, KeybindingRegistry, KeybindingRuntimeContext

LK_RCH_NO_SHORTCUT = "LK-RCH-NO_SHORTCUT"
LK_RCH_NO_FOCUS_PATH = "LK-RCH-NO_FOCUS_PATH"
LK_RCH_MODE_BLOCKED = "LK-RCH-MODE_BLOCKED"
LK_RCH_POPUP_BLOCKED = "LK-RCH-POPUP_BLOCKED"
LK_RCH_TEXT_INPUT_BLOCKED = "LK-RCH-TEXT_INPUT_BLOCKED"
LK_MAN_INTENT_UNKNOWN = "LK-MAN-INTENT_UNKNOWN"
LK_MAN_ROUTE_UNKNOWN = "LK-MAN-ROUTE_UNKNOWN"
LK_MAN_EQUIVALENCE_INVALID = "LK-MAN-EQUIVALENCE_INVALID"
LK_TRK_MISSING_MANDATORY = "LK-TRK-MISSING_MANDATORY"
LK_TRK_CHECKSUM_INVALID = "LK-TRK-CHECKSUM_INVALID"
LK_TRK_SEQUENCE_GAP = "LK-TRK-SEQUENCE_GAP"
LK_TRK_PRODUCER_UNTRUSTED = "LK-TRK-PRODUCER_UNTRUSTED"
LK_ROL_FALLBACK_FORBIDDEN = "LK-ROL-FALLBACK_FORBIDDEN"
LK_ARC_IMPORT_VIOLATION = "LK-ARC-IMPORT_VIOLATION"

REASON_CODE_CATALOG = frozenset(
    {
        LK_RCH_NO_SHORTCUT,
        LK_RCH_NO_FOCUS_PATH,
        LK_RCH_MODE_BLOCKED,
        LK_RCH_POPUP_BLOCKED,
        LK_RCH_TEXT_INPUT_BLOCKED,
        LK_MAN_INTENT_UNKNOWN,
        LK_MAN_ROUTE_UNKNOWN,
        LK_MAN_EQUIVALENCE_INVALID,
        LK_TRK_MISSING_MANDATORY,
        LK_TRK_CHECKSUM_INVALID,
        LK_TRK_SEQUENCE_GAP,
        LK_TRK_PRODUCER_UNTRUSTED,
        LK_ROL_FALLBACK_FORBIDDEN,
        LK_ARC_IMPORT_VIOLATION,
    }
)

_STEP_ID_RE = re.compile(r"^LK-([A-I])-([A-Z]{3})-(\d{3})$")
_AREA_CODES = frozenset({"ARC", "API", "MAN", "RTC", "RCH", "TRK", "MIG", "ROL", "GOV"})
_COMPLETED_STATES = frozenset({"done", "completed", "passed", "ok"})


@dataclass(frozen=True)
class LaufKernRoute:
    route_id: str
    intent: str
    route_type: str
    modes: tuple[str, ...] = ()
    binding_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LaufKernManifest:
    manifest_id: str
    repo_name: str
    intents: tuple[str, ...]
    keybindings: tuple[KeyBindingDefinition, ...]
    routes: tuple[LaufKernRoute, ...]
    exclusions: dict[str, str] = field(default_factory=dict)
    equivalence: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ReachabilityResult:
    intent: str
    reachable: bool
    reason_code: str | None = None
    route_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrackingArtifact:
    run_id: str
    repo_name: str
    step_id: str
    phase: str
    state: str
    timestamp: str
    sequence: int
    mandatory: bool
    producer: str
    checksum: str
    reason_code: str | None = None
    evidence_ref: str | None = None

    def checksum_payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "repo_name": self.repo_name,
            "step_id": self.step_id,
            "phase": self.phase,
            "state": self.state,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
            "mandatory": self.mandatory,
            "producer": self.producer,
            "reason_code": self.reason_code,
            "evidence_ref": self.evidence_ref,
        }

    @staticmethod
    def build_checksum(payload: dict[str, object]) -> str:
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def has_valid_checksum(self) -> bool:
        return self.checksum == self.build_checksum(self.checksum_payload())


@dataclass(frozen=True)
class CompletionSummary:
    status: str
    total_steps: int
    completed_steps: int
    mandatory_steps: int
    blockers: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


def build_manifest(
    *,
    manifest_id: str,
    repo_name: str,
    intents: Iterable[str],
    routes: Iterable[LaufKernRoute],
    keybinding_registry: KeybindingRegistry | None = None,
    keybindings: Iterable[KeyBindingDefinition] | None = None,
    exclusions: Mapping[str, str] | None = None,
    equivalence: Mapping[str, str] | None = None,
    metadata: Mapping[str, str] | None = None,
) -> LaufKernManifest:
    if keybinding_registry is not None and keybindings is not None:
        raise ValueError("Provide either keybinding_registry or keybindings, not both")

    if keybinding_registry is not None:
        keybinding_values = keybinding_registry.all()
    else:
        keybinding_values = tuple(keybindings or ())

    return LaufKernManifest(
        manifest_id=manifest_id,
        repo_name=repo_name,
        intents=tuple(intents),
        keybindings=tuple(keybinding_values),
        routes=tuple(routes),
        exclusions=dict(exclusions or {}),
        equivalence=dict(equivalence or {}),
        metadata=dict(metadata or {}),
    )


def verify_manifest(manifest: LaufKernManifest) -> tuple[bool, tuple[str, ...]]:
    errors: list[str] = []
    known_intents = set(manifest.intents)
    binding_ids = {definition.binding_id for definition in manifest.keybindings}
    seen_routes: set[str] = set()

    for route in manifest.routes:
        if route.route_id in seen_routes:
            errors.append(f"duplicate-route-id:{route.route_id}")
        seen_routes.add(route.route_id)

        if route.intent not in known_intents:
            errors.append(f"route-intent-unknown:{route.route_id}:{route.intent}")

        if route.route_type == "shortcut":
            if not route.binding_id:
                errors.append(f"shortcut-missing-binding:{route.route_id}")
            elif route.binding_id not in binding_ids:
                errors.append(f"shortcut-binding-unknown:{route.route_id}:{route.binding_id}")

    for intent, reason_code in manifest.exclusions.items():
        if intent not in known_intents:
            errors.append(f"exclusion-intent-unknown:{intent}")
        if reason_code not in REASON_CODE_CATALOG:
            errors.append(f"exclusion-reason-unknown:{intent}:{reason_code}")

    for source_intent, target_intent in manifest.equivalence.items():
        if source_intent not in known_intents or target_intent not in known_intents:
            errors.append(f"equivalence-invalid:{source_intent}:{target_intent}")

    return (len(errors) == 0, tuple(errors))


def evaluate_intent_routes(
    *,
    manifest: LaufKernManifest,
    intent: str,
    context: KeybindingRuntimeContext,
) -> ReachabilityResult:
    if intent not in set(manifest.intents):
        return ReachabilityResult(intent=intent, reachable=False, reason_code=LK_MAN_INTENT_UNKNOWN)

    if intent in manifest.exclusions:
        return ReachabilityResult(intent=intent, reachable=False, reason_code=manifest.exclusions[intent])

    target_intent = manifest.equivalence.get(intent, intent)
    routes = tuple(route for route in manifest.routes if route.intent == target_intent)
    if not routes:
        has_binding = any(binding.intent == target_intent for binding in manifest.keybindings)
        reason = LK_RCH_NO_FOCUS_PATH if has_binding else LK_RCH_NO_SHORTCUT
        return ReachabilityResult(intent=intent, reachable=False, reason_code=reason)

    binding_by_id = {binding.binding_id: binding for binding in manifest.keybindings}
    registry = KeybindingRegistry()
    registry.register_many(manifest.keybindings)

    blocked_reason = LK_RCH_NO_FOCUS_PATH
    for route in routes:
        if route.route_type == "shortcut":
            if not route.binding_id:
                blocked_reason = LK_MAN_ROUTE_UNKNOWN
                continue
            binding = binding_by_id.get(route.binding_id)
            if binding is None:
                blocked_reason = LK_MAN_ROUTE_UNKNOWN
                continue
            active, runtime_reason = registry.evaluate_runtime(binding, context)
            if active:
                return ReachabilityResult(intent=intent, reachable=True, route_ids=(route.route_id,))
            if runtime_reason == "text-input-focus":
                blocked_reason = LK_RCH_TEXT_INPUT_BLOCKED
            elif runtime_reason == "dialog-priority":
                blocked_reason = LK_RCH_POPUP_BLOCKED
            else:
                blocked_reason = LK_RCH_MODE_BLOCKED
            continue

        if route.modes and context.active_mode not in route.modes:
            blocked_reason = LK_RCH_MODE_BLOCKED
            continue
        if context.dialog_open and route.metadata.get("popup_blocking") == "true":
            blocked_reason = LK_RCH_POPUP_BLOCKED
            continue
        return ReachabilityResult(intent=intent, reachable=True, route_ids=(route.route_id,))

    return ReachabilityResult(intent=intent, reachable=False, reason_code=blocked_reason)


def verify_reachability(
    *,
    manifest: LaufKernManifest,
    context: KeybindingRuntimeContext,
    intents: Iterable[str] | None = None,
) -> tuple[ReachabilityResult, ...]:
    in_scope = tuple(intents) if intents is not None else manifest.intents
    return tuple(
        evaluate_intent_routes(
            manifest=manifest,
            intent=intent,
            context=context,
        )
        for intent in in_scope
    )


def validate_step_id(step_id: str) -> bool:
    match = _STEP_ID_RE.match(step_id)
    if not match:
        return False
    return match.group(2) in _AREA_CODES


def emit_tracking_artifact(
    *,
    run_id: str,
    repo_name: str,
    step_id: str,
    phase: str,
    state: str,
    sequence: int,
    mandatory: bool,
    producer: str,
    reason_code: str | None = None,
    evidence_ref: str | None = None,
    timestamp: str | None = None,
) -> TrackingArtifact:
    if not validate_step_id(step_id):
        raise ValueError(f"Invalid step_id: {step_id}")
    if reason_code is not None and reason_code not in REASON_CODE_CATALOG:
        raise ValueError(f"Unknown reason_code: {reason_code}")

    ts = timestamp or datetime.now(UTC).isoformat()
    payload = {
        "run_id": run_id,
        "repo_name": repo_name,
        "step_id": step_id,
        "phase": phase,
        "state": state,
        "timestamp": ts,
        "sequence": sequence,
        "mandatory": mandatory,
        "producer": producer,
        "reason_code": reason_code,
        "evidence_ref": evidence_ref,
    }
    checksum = TrackingArtifact.build_checksum(payload)
    return TrackingArtifact(checksum=checksum, **payload)


def aggregate_completion(
    artifacts: Sequence[TrackingArtifact] | Iterable[TrackingArtifact],
    *,
    mandatory_steps: set[str] | None = None,
    trusted_producers: set[str] | None = None,
) -> CompletionSummary:
    values = tuple(artifacts)
    trusted = trusted_producers or {"laufkern"}

    errors: list[str] = []
    by_step_latest: dict[str, TrackingArtifact] = {}
    mandatory_candidates: set[str] = set(mandatory_steps or ())
    grouped_sequences: dict[tuple[str, str], list[int]] = defaultdict(list)

    for artifact in values:
        if not artifact.has_valid_checksum():
            errors.append(f"{LK_TRK_CHECKSUM_INVALID}:{artifact.step_id}")
        if artifact.producer not in trusted:
            errors.append(f"{LK_TRK_PRODUCER_UNTRUSTED}:{artifact.step_id}")

        grouped_sequences[(artifact.run_id, artifact.repo_name)].append(artifact.sequence)
        if artifact.mandatory:
            mandatory_candidates.add(artifact.step_id)

        previous = by_step_latest.get(artifact.step_id)
        if previous is None or artifact.sequence >= previous.sequence:
            by_step_latest[artifact.step_id] = artifact

    for key, seq_values in grouped_sequences.items():
        ordered = sorted(seq_values)
        for left, right in zip(ordered, ordered[1:]):
            if right != left + 1:
                errors.append(f"{LK_TRK_SEQUENCE_GAP}:{key[0]}:{key[1]}")
                break

    blockers: list[str] = []
    completed_steps = 0
    for step_id in sorted(mandatory_candidates):
        artifact = by_step_latest.get(step_id)
        if artifact is None or artifact.state not in _COMPLETED_STATES:
            blockers.append(f"{LK_TRK_MISSING_MANDATORY}:{step_id}")
            continue
        completed_steps += 1

    status = "complete"
    if blockers or errors:
        status = "non-complete"

    return CompletionSummary(
        status=status,
        total_steps=len(by_step_latest),
        completed_steps=completed_steps,
        mandatory_steps=len(mandatory_candidates),
        blockers=tuple(sorted(set(blockers))),
        errors=tuple(sorted(set(errors))),
    )


# Pilot bridge: resolve shared bw-gui LaufKern API while preserving local import paths.
try:
    from bw_libs.shared_gui_core import ensure_bw_gui_on_path as _ensure_bw_gui_on_path

    _ensure_bw_gui_on_path()

    from bw_gui.laufkern import (  # type: ignore[assignment]
        CompletionSummary,
        LaufKernManifest,
        LaufKernRoute,
        ReachabilityResult,
        TrackingArtifact,
        aggregate_completion,
        build_manifest,
        build_runtime_context,
        emit_tracking_artifact,
        evaluate_intent_routes,
        is_known_reason_code,
        validate_step_id,
        verify_manifest,
        verify_reachability,
    )
except ModuleNotFoundError:
    # Keep local fallback contracts usable when shared core is unavailable.
    def build_runtime_context(*, active_mode: str, offline: bool = False, text_input_focused: bool = False):
        return KeybindingRuntimeContext(
            active_mode=active_mode,
            offline=offline,
            text_input_focused=text_input_focused,
            dialog_open=False,
        )

    def is_known_reason_code(reason_code: str) -> bool:
        return reason_code in REASON_CODE_CATALOG


__all__ = [
    "CompletionSummary",
    "LaufKernManifest",
    "LaufKernRoute",
    "ReachabilityResult",
    "TrackingArtifact",
    "aggregate_completion",
    "build_manifest",
    "build_runtime_context",
    "emit_tracking_artifact",
    "evaluate_intent_routes",
    "is_known_reason_code",
    "validate_step_id",
    "verify_manifest",
    "verify_reachability",
]
