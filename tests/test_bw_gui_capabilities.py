"""Korrektor's minimum bw-gui capabilities (contract V9 of the PDF import).

Korrektor resolves bw-gui from the sibling workspace via
`bw_libs.shared_gui_core.ensure_bw_gui_on_path` (no pinned version). If an
older bw-gui is picked up - e.g. the stale, untracked fallback copy
``korrektor/bw-gui/`` - these imports fail loudly here instead of the app
only failing when the import wizard or "Neue Klausur" is used.
Minimum bw-gui commit: 732b821 (ScrollableImagePreview), after 689f2f1
(ChoiceDialogService).
"""


def test_bw_gui_provides_widgets_and_dialogs_used_by_the_pdf_import():
    from bw_gui.dialogs import ChoiceDialogService, ChoiceOption
    from bw_gui.runtime import WindowShortcutBinder
    from bw_gui.widgets import ScrollableImagePreview

    assert callable(ChoiceDialogService().askchoice)
    assert ChoiceOption("k", "Label").description == ""
    assert hasattr(ScrollableImagePreview, "refresh") and hasattr(ScrollableImagePreview, "scroll")
    assert hasattr(WindowShortcutBinder, "bind")
