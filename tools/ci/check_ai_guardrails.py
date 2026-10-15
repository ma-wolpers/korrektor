#!/usr/bin/env python3
"""Korrektor-Guardrails: Einstieg für lokale Läufe und CI (``python tools/ci/check_ai_guardrails.py``).

Konfiguration in ``guardrail_config.py``, Helfer in ``guardrail_support.py``,
Prozess-Checks in ``guardrail_process.py``, inhaltliche Checks in ``guardrail_checks.py``.
Die Module liegen neben diesem Skript; Python nimmt dessen Ordner beim Skriptstart in
``sys.path`` auf.
"""
from __future__ import annotations

from guardrail_support import _read, _repo_root, _require_substring, _staged_files
from guardrail_process import (
    _check_changelog_updated,
    _check_development_log_updated,
    _collect_process_guidance_warnings,
    _collect_shortcut_coverage_warnings,
    _has_relevant_staged_changes,
    _is_ci_environment,
)
from guardrail_checks import (
    _check_future_gui_entry_contracts,
    _check_gui_migration_backlog,
    _check_laufkern_fallback_sunset,
    _check_repo_wide_gui_contracts,
    _check_runtime_shortcut_integration,
    _check_shared_ui_contracts,
    _check_ui_contract_bridge_decommission,
    _check_undo_redo_contracts,
)


def main() -> int:
    repo_root = _repo_root()
    staged = _staged_files(repo_root)
    if staged and not _has_relevant_staged_changes(staged, repo_root):
        print("AI guardrail check skipped (no guardrail-relevant staged files).")
        return 0

    errors: list[str] = []

    _read("AGENTS.md")
    _read(".github/copilot-instructions.md")
    _read(".github/pull_request_template.md")
    _read(".github/workflows/quality-guardrails.yml")
    _read("docs/ARCHITEKTUR.md")
    _read("docs/DEVELOPMENT_LOG.md")
    _read("CHANGELOG.md")
    _read("bw_libs/ui_contract/keybinding.py")
    _read("bw_libs/ui_contract/popup.py")
    _read("bw_libs/ui_contract/hsm.py")
    _read("bw_libs/ui_contract/laufkern.py")
    _read("bw_libs/app_paths.py")

    architecture = _read("docs/ARCHITEKTUR.md")
    _require_substring(architecture, "Schichten", "docs/ARCHITEKTUR.md", errors)

    _check_development_log_updated(staged, errors)
    _check_changelog_updated(staged, errors)
    _check_runtime_shortcut_integration(errors)
    _check_undo_redo_contracts(errors)
    _check_shared_ui_contracts(errors)
    _check_laufkern_fallback_sunset(errors)
    _check_ui_contract_bridge_decommission(errors)
    _check_future_gui_entry_contracts(errors)
    _check_repo_wide_gui_contracts(errors)
    _check_gui_migration_backlog(errors)
    warnings = _collect_process_guidance_warnings()
    warnings.extend(_collect_shortcut_coverage_warnings())

    if errors:
        print("AI guardrail check failed:")
        for item in errors:
            print(f" - {item}")
        return 2

    if warnings and not _is_ci_environment():
        print("AI guardrail process warnings (non-blocking):")
        for item in warnings:
            print(f" - {item}")

    print("AI guardrail check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
