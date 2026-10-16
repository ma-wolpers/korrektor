"""Readable mark names for hints: catalog label, older symbol, shortened text, location line."""

from app.core.domain.mark_labels import mark_label, mark_location_line
from app.core.domain.mark_symbols import SYMBOL_BY_KEY
from app.core.domain.models import PdfAnnotation


def _mark(annotation_type: str, content: str, task_code: str = "2C") -> PdfAnnotation:
    return PdfAnnotation("m1", "Anna.pdf", 2, annotation_type, content, "#d62828", 10, 10, task_code=task_code)


def test_catalog_symbol_is_named_by_its_label_not_by_its_content():
    heart = SYMBOL_BY_KEY["heart"]
    assert mark_label(_mark("symbol", heart.content)) == heart.label
    assert heart.content != heart.label


def test_older_symbol_keeps_its_raw_content():
    assert mark_label(_mark("symbol", "△")) == "△"


def test_text_is_quoted_and_shortened_to_one_line():
    assert mark_label(_mark("text", "gut")) == "Text „gut“"
    long_label = mark_label(_mark("text", "Ableitung\nfalsch, bitte die Kettenregel noch einmal anschauen"))
    assert long_label.startswith("Text „Ableitung falsch") and long_label.endswith("…“") and "\n" not in long_label


def test_location_line_names_person_page_and_sub_task():
    check = SYMBOL_BY_KEY["check"]
    assert mark_location_line(_mark("symbol", check.content), "Anna") == f"Anna, S. 2, Aufgabe 2C: {check.label}"
    assert mark_location_line(_mark("symbol", check.content, task_code=""), "Anna") == f"Anna, S. 2, ohne Aufgabe: {check.label}"
