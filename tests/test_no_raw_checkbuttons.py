"""Architektur-Guard: keine rohen Tk/ttk-Checkbuttons (bw-gui TOGGLE_CONTRACT, R6).

Binaere Controls sind bw-gui Checkbox (Auswahl, wirkt erst per Knopf) oder Switch
(sofortige Wirkung); Menues nutzen MenuItem(type="switch"/"checkbox") bzw.
add_menu_switch. Die Pruefung liegt zentral in bw_gui.testing.checkbutton_guard.
"""

from __future__ import annotations

from pathlib import Path

from bw_gui.testing.checkbutton_guard import RULE, find_offenders

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_app_uses_no_raw_checkbuttons():
    offenders = find_offenders(REPO_ROOT / "app")
    assert offenders == {}, f"{RULE} Fundstellen: {offenders}"
