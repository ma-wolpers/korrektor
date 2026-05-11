"""Shared LaufKern bridge for app-local imports."""

from __future__ import annotations

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
