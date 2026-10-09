"""Schritt-0-Invariante: bw_gui stammt aus dem Geschwister-Checkout, nie aus einer verschachtelten Kopie.

Siehe bw-gui ``docs/CONSUMER_SETUP.md``. Ohne diese Prüfung könnten Entwicklung
und Tests unbemerkt gegen unterschiedliche bw-gui-Stände laufen.
"""

from __future__ import annotations

from pathlib import Path

from bw_libs.shared_gui_core import ensure_bw_gui_on_path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_bw_gui_is_imported_from_sibling_checkout():
    ensure_bw_gui_on_path()
    from bw_gui.testing.import_source import assert_bw_gui_from_sibling

    assert_bw_gui_from_sibling(REPO_ROOT)
