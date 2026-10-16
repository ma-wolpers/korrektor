"""Symbol usage contracts: what counts, how often, in which order."""

from __future__ import annotations

from app.core.domain.mark_symbols import MARK_SYMBOLS
from app.core.domain.models import PdfAnnotation
from app.core.domain.symbol_usage import LEGACY_DESCRIPTION, symbols_for_task, used_symbols

PDFS = ["Anna.pdf", "Ben.pdf"]


def _mark(mark_id: str, content: str, pdf: str = "Anna.pdf", task: str = "1A", kind: str = "symbol", group: str = "") -> PdfAnnotation:
    return PdfAnnotation(mark_id, pdf, 1, kind, content, "#d62828", 10, 10, task_code=task, sync_group_id=group)


def test_counts_marks_and_distinct_submissions():
    marks = [_mark("a1", "✓"), _mark("a2", "✓"), _mark("b1", "✓", "Ben.pdf", "1B")]
    (usage,) = used_symbols(marks, PDFS, ["1A", "1B"])
    assert (usage.count, usage.submission_count, usage.task_codes) == (3, 2, ("1A", "1B"))
    assert usage.label == "Richtig" and usage.description == "Dieser Schritt ist richtig."


def test_supersymbols_count_texts_and_foreign_pdfs_do_not():
    marks = [
        _mark("s1", "✗", group="sg"), _mark("s2", "✗", "Ben.pdf", group="sg"),  # Supersymbol clones
        _mark("t1", "Gut", kind="text"), _mark("p1", "8/10", kind="text"),  # comment, points superposition
        _mark("x1", "✓", "Old.pdf"),  # not a current person
    ]
    usages = used_symbols(marks, PDFS)
    assert [(usage.content, usage.count, usage.submission_count) for usage in usages] == [("✗", 2, 2)]


def test_same_mark_is_counted_once():
    marks = [_mark("a1", "?"), _mark("a1", "?")]
    assert used_symbols(marks, PDFS)[0].count == 1


def test_palette_order_then_unknown_by_count_then_content():
    marks = [_mark("1", "△"), _mark("2", "◇"), _mark("3", "◇"), _mark("4", "✗"), _mark("5", "✓"), _mark("6", "□")]
    usages = used_symbols(marks, PDFS)
    assert [usage.content for usage in usages] == ["✓", "✗", "◇", "□", "△"]
    legacy = usages[-1]
    assert legacy.symbol is None and legacy.label == "△" and legacy.description == LEGACY_DESCRIPTION


def test_unknown_content_is_never_mapped_to_a_catalog_symbol():
    (usage,) = used_symbols([_mark("1", " ✓")], PDFS)
    assert usage.symbol is None


def test_symbols_for_task_most_frequent_and_deterministic_ties():
    marks = [_mark("1", "?"), _mark("2", "✗"), _mark("3", "✗"), _mark("4", "✓"), _mark("5", "!"), _mark("6", "✓", task="2A")]
    top = symbols_for_task(marks, PDFS, "1A", limit=3)
    assert [usage.content for usage in top] == ["✗", "✓", "!"]  # 2x, then ties in palette order
    assert all(usage.task_codes == ("1A",) for usage in top)


def test_every_catalog_symbol_has_a_description():
    assert all(symbol.description.strip() for symbol in MARK_SYMBOLS)
