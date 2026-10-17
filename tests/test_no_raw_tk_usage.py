"""Architektur-Guard: keine rohen Tk-Ereignisbindungen, -Felder, ``"break"`` und Auswahl-Mutationen.

Prüflogik zentral in bw-gui (``bw_gui.testing.tk_usage_guard``, drei Ebenen dort dokumentiert).
Bewusste Ausnahmen tragen ``# bw-tk: <Grund>`` in der Zeile; derzeit gibt es keine.
"""

from __future__ import annotations

from pathlib import Path

from bw_gui.testing.tk_usage_guard import RULE, find_offenders, opt_outs

APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def test_app_uses_the_bw_gui_event_contracts_only():
    offenders = find_offenders(APP_ROOT)
    assert offenders == {}, f"{RULE} Fundstellen: {offenders}"


def test_no_undocumented_opt_outs():
    assert opt_outs(APP_ROOT) == {}
