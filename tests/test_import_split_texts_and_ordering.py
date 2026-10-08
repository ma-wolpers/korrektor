from pathlib import Path

from app.adapters.gui.import_split_ordering import move_item, natural_sort_paths
from app.adapters.gui.import_split_texts import (
    counter_text,
    duplicate_hint,
    fallback_warning_text,
    format_page_ranges,
    name_caption,
    origin_text,
    section_status,
    write_error_text,
)
from app.core.domain.pdf_split_naming import SplitSection, plan_split_files
from app.infrastructure.pdf.pdf_merger import MergedSourceSpan


def test_format_page_ranges_german_prose():
    assert format_page_ranges([(9, 9)]) == "Seite 9"
    assert format_page_ranges([(2, 6)]) == "Seiten 2-6"
    assert format_page_ranges([(2, 6), (13, 19)]) == "Seiten 2-6 und 13-19"
    assert format_page_ranges([(1, 2), (5, 5), (9, 10)]) == "Seiten 1-2, 5 und 9-10"


def test_duplicate_hint_names_the_other_sections():
    hint = duplicate_hint([SplitSection(2, 6, "Anna"), SplitSection(13, 19, "anna")])
    assert "Seiten 2-6 und 13-19" in hint
    assert "\n" not in hint


def test_origin_text_shows_source_only_for_several_pdfs():
    span = MergedSourceSpan(Path("scan_02.pdf"), 21, 40)
    assert origin_text(23, 40, span, multiple_sources=False) == "Seite 23/40"
    assert origin_text(23, 40, span, multiple_sources=True) == "Seite 23/40 · aus scan_02.pdf, S. 3/20"


def test_caption_counter_and_status():
    sections = [SplitSection(1, 2, "Anna"), SplitSection(3, 4, ""), SplitSection(5, 6, "anna")]
    plan = plan_split_files(sections)
    assert name_caption(sections[0]) == "Name (Abgabe S. 1-2):"
    assert counter_text(3, plan) == "3 Abgaben · 1 ohne gültigen Namen · 1 Name doppelt"
    assert [section_status(s, plan) for s in sections] == ["zusammengeführt", "ohne Namen", "zusammengeführt"]


def test_fallback_warning_lists_placeholder_files():
    plan = plan_split_files([SplitSection(1, 2, "Anna"), SplitSection(3, 4, "")])
    text = fallback_warning_text(plan)
    assert "Seiten 3-4 → Abgabe_02.pdf" in text
    assert "Anna" not in text


def test_write_error_text_mentions_leftovers_or_clean_rollback():
    assert "keine Dateien angelegt" in write_error_text(OSError("voll"), [])
    assert "A.pdf" in write_error_text(OSError("voll"), [Path("out/A.pdf")])


def test_natural_sort_with_deterministic_tiebreak():
    paths = [Path("x/scan_10.pdf"), Path("x/Scan_2.pdf"), Path("x/scan_2.pdf"), Path("x/scan_1.pdf")]
    assert [p.name for p in natural_sort_paths(paths)] == ["scan_1.pdf", "Scan_2.pdf", "scan_2.pdf", "scan_10.pdf"]


def test_move_item_never_mutates_and_clamps_at_edges():
    items = ["a", "b", "c"]
    assert move_item(items, 2, -1) == (["a", "c", "b"], 1)
    assert move_item(items, 0, -1) == (["a", "b", "c"], 0)
    assert move_item(items, 2, 1) == (["a", "b", "c"], 2)
    assert move_item(items, 5, -1) == (["a", "b", "c"], 5)
    assert items == ["a", "b", "c"]
