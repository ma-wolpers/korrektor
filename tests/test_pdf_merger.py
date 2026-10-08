from pathlib import Path

import fitz
import pytest

from app.infrastructure.pdf import pdf_merger
from app.infrastructure.pdf.pdf_merger import MergedSourceSpan, PdfImportError, open_merged_pdf


def _build_pdf(path: Path, page_count: int, tag: str) -> Path:
    document = fitz.open()
    for i in range(page_count):
        document.new_page(width=200, height=300).insert_text((20, 20), f"{tag} {i + 1}")
    document.save(path)
    document.close()
    return path


def _build_locked_pdf(path: Path) -> Path:
    document = fitz.open()
    document.new_page()
    document.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="y")
    document.close()
    return path


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> list:
    """Record every document `fitz.open` returns, to prove nothing stays open on error paths."""
    documents: list = []
    real_open = fitz.open

    def _recording_open(*args, **kwargs):
        document = real_open(*args, **kwargs)
        documents.append(document)
        return document

    monkeypatch.setattr(fitz, "open", _recording_open)
    return documents


def test_merges_in_given_order_with_one_based_inclusive_spans(tmp_path: Path) -> None:
    a = _build_pdf(tmp_path / "a.pdf", 3, "A")
    b = _build_pdf(tmp_path / "b.pdf", 2, "B")

    merged, spans = open_merged_pdf([b, a])
    try:
        texts = [merged.load_page(index).get_text().strip() for index in range(merged.page_count)]
    finally:
        merged.close()

    assert texts == ["B 1", "B 2", "A 1", "A 2", "A 3"]
    assert spans == [MergedSourceSpan(b, 1, 2), MergedSourceSpan(a, 3, 5)]
    assert spans[1].page_count == 3
    assert spans[1].local_page(3) == 1
    assert spans[1].local_page(5) == 3


def test_sources_are_closed_after_successful_merge(tmp_path: Path, opened: list) -> None:
    a = _build_pdf(tmp_path / "a.pdf", 1, "A")
    b = _build_pdf(tmp_path / "b.pdf", 1, "B")
    opened.clear()

    merged, _spans = open_merged_pdf([a, b])

    try:
        assert [document.is_closed for document in opened if document is not merged] == [True, True]
        assert not merged.is_closed
    finally:
        merged.close()


def test_locked_source_in_the_middle_closes_everything(tmp_path: Path, opened: list) -> None:
    a = _build_pdf(tmp_path / "a.pdf", 2, "A")
    locked = _build_locked_pdf(tmp_path / "locked.pdf")
    c = _build_pdf(tmp_path / "c.pdf", 2, "C")
    opened.clear()

    with pytest.raises(PdfImportError) as excinfo:
        open_merged_pdf([a, locked, c])

    assert excinfo.value.path == locked
    assert excinfo.value.reason == "passwortgeschützt"
    assert opened and all(document.is_closed for document in opened)
    assert len(opened) == 3  # merged target, a, locked - c is never opened


def test_unreadable_source_raises_import_error(tmp_path: Path, opened: list) -> None:
    a = _build_pdf(tmp_path / "a.pdf", 1, "A")
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a pdf")
    opened.clear()

    with pytest.raises(PdfImportError, match="broken.pdf: nicht lesbar"):
        open_merged_pdf([a, broken])

    assert all(document.is_closed for document in opened)


def test_copy_failure_closes_everything(tmp_path: Path, opened: list, monkeypatch: pytest.MonkeyPatch) -> None:
    a = _build_pdf(tmp_path / "a.pdf", 1, "A")
    b = _build_pdf(tmp_path / "b.pdf", 1, "B")
    real_insert = fitz.Document.insert_pdf
    calls = {"n": 0}

    def _flaky_insert(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated copy failure")
        return real_insert(self, *args, **kwargs)

    monkeypatch.setattr(fitz.Document, "insert_pdf", _flaky_insert)
    opened.clear()

    with pytest.raises(PdfImportError, match="Zusammenführen fehlgeschlagen"):
        open_merged_pdf([a, b])

    assert all(document.is_closed for document in opened)


def test_source_without_pages_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _EmptyPdf:
        is_pdf = True
        needs_pass = False
        page_count = 0
        is_closed = False

        def close(self) -> None:
            self.is_closed = True

    empty = _EmptyPdf()
    real_open = fitz.open
    monkeypatch.setattr(pdf_merger.fitz, "open", lambda *args, **kwargs: empty if args and Path(args[0]).name == "empty.pdf" else real_open(*args, **kwargs))

    with pytest.raises(PdfImportError, match="enthält keine Seiten"):
        open_merged_pdf([tmp_path / "empty.pdf"])

    assert empty.is_closed


def test_empty_path_list_is_rejected() -> None:
    with pytest.raises(ValueError):
        open_merged_pdf([])
