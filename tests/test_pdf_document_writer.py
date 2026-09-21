from pathlib import Path

import fitz
import pytest

from app.infrastructure.pdf.pdf_document_writer import (
    KORREKTOR_STATS_PAGE_MARKER,
    append_marked_stats_page,
    read_trailing_page_bytes,
    read_trailing_page_marker,
    remove_trailing_page,
    rewrite_pdf_atomically,
)


def _build_pdf(path: Path, page_count: int) -> None:
    document = fitz.open()
    for _ in range(page_count):
        document.new_page(width=200, height=300)
    document.save(path)
    document.close()


def _one_page_pdf_bytes(text: str = "stats") -> bytes:
    document = fitz.open()
    page = document.new_page(width=200, height=300)
    page.insert_text((20, 20), text)
    data = document.tobytes()
    document.close()
    return data


def test_rewrite_pdf_atomically_applies_mutation(tmp_path: Path) -> None:
    pdf_path = tmp_path / "exam.pdf"
    _build_pdf(pdf_path, page_count=2)

    rewrite_pdf_atomically(pdf_path, lambda document: document.new_page(width=200, height=300))

    document = fitz.open(pdf_path)
    try:
        assert document.page_count == 3
    finally:
        document.close()


def test_rewrite_pdf_atomically_leaves_original_untouched_on_error(tmp_path: Path) -> None:
    pdf_path = tmp_path / "exam.pdf"
    _build_pdf(pdf_path, page_count=2)

    def _failing_mutate(document: fitz.Document) -> None:
        document.new_page(width=200, height=300)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        rewrite_pdf_atomically(pdf_path, _failing_mutate)

    document = fitz.open(pdf_path)
    try:
        assert document.page_count == 2
    finally:
        document.close()
    assert not pdf_path.with_name("exam.korrektor.tmp.pdf").exists()


def test_rewrite_pdf_atomically_closes_document_before_replace_no_stale_handle(tmp_path: Path) -> None:
    """Windows-relevant: a second rewrite on the same file must succeed immediately afterwards -
    if the first call left a handle open, os.replace (or this second open) would fail/lock."""
    pdf_path = tmp_path / "exam.pdf"
    _build_pdf(pdf_path, page_count=1)

    rewrite_pdf_atomically(pdf_path, lambda document: document.new_page(width=200, height=300))
    rewrite_pdf_atomically(pdf_path, lambda document: document.new_page(width=200, height=300))

    document = fitz.open(pdf_path)
    try:
        assert document.page_count == 3
    finally:
        document.close()


def test_read_trailing_page_bytes_extracts_last_page_only(tmp_path: Path) -> None:
    pdf_path = tmp_path / "exam.pdf"
    document = fitz.open()
    document.new_page(width=200, height=300).insert_text((20, 20), "first")
    document.new_page(width=200, height=300).insert_text((20, 20), "last")
    document.save(pdf_path)
    document.close()

    extracted = read_trailing_page_bytes(pdf_path)
    assert extracted is not None

    check = fitz.open(stream=extracted, filetype="pdf")
    try:
        assert check.page_count == 1
        assert "last" in check.load_page(0).get_text()
    finally:
        check.close()


def test_read_trailing_page_marker_none_when_absent(tmp_path: Path) -> None:
    pdf_path = tmp_path / "exam.pdf"
    _build_pdf(pdf_path, page_count=1)

    assert read_trailing_page_marker(pdf_path) is None


def test_append_marked_stats_page_grows_page_count_and_stamps(tmp_path: Path) -> None:
    pdf_path = tmp_path / "exam.pdf"
    _build_pdf(pdf_path, page_count=2)

    append_marked_stats_page(pdf_path, _one_page_pdf_bytes("v1"), replace_existing=False)

    document = fitz.open(pdf_path)
    try:
        assert document.page_count == 3
        assert "v1" in document.load_page(2).get_text()
    finally:
        document.close()
    assert read_trailing_page_marker(pdf_path) == KORREKTOR_STATS_PAGE_MARKER


def test_append_marked_stats_page_replace_existing_keeps_page_count(tmp_path: Path) -> None:
    pdf_path = tmp_path / "exam.pdf"
    _build_pdf(pdf_path, page_count=2)
    append_marked_stats_page(pdf_path, _one_page_pdf_bytes("v1"), replace_existing=False)

    append_marked_stats_page(pdf_path, _one_page_pdf_bytes("v2"), replace_existing=True)

    document = fitz.open(pdf_path)
    try:
        assert document.page_count == 3
        text = document.load_page(2).get_text()
        assert "v2" in text
        assert "v1" not in text
    finally:
        document.close()
    assert read_trailing_page_marker(pdf_path) == KORREKTOR_STATS_PAGE_MARKER


def test_remove_trailing_page(tmp_path: Path) -> None:
    pdf_path = tmp_path / "exam.pdf"
    _build_pdf(pdf_path, page_count=2)
    append_marked_stats_page(pdf_path, _one_page_pdf_bytes(), replace_existing=False)

    remove_trailing_page(pdf_path)

    document = fitz.open(pdf_path)
    try:
        assert document.page_count == 2
    finally:
        document.close()
    assert read_trailing_page_marker(pdf_path) is None
