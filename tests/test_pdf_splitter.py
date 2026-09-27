from pathlib import Path

import fitz
import pytest

from app.infrastructure.pdf.pdf_splitter import split_pdf_by_ranges


def _build_pdf(path: Path, page_count: int) -> None:
    document = fitz.open()
    for i in range(page_count):
        document.new_page(width=200, height=300).insert_text((20, 20), f"page {i + 1}")
    document.save(path)
    document.close()


def test_split_creates_one_file_per_range(tmp_path: Path) -> None:
    source = tmp_path / "combined.pdf"
    _build_pdf(source, page_count=6)
    output_dir = tmp_path / "out"

    created = split_pdf_by_ranges(source, [(1, 3), (4, 6)], output_dir)

    assert [path.name for path in created] == ["Abgabe_01.pdf", "Abgabe_02.pdf"]
    for path, expected_pages in zip(created, [3, 3]):
        document = fitz.open(path)
        try:
            assert document.page_count == expected_pages
        finally:
            document.close()


def test_split_preserves_page_content_in_correct_order(tmp_path: Path) -> None:
    source = tmp_path / "combined.pdf"
    _build_pdf(source, page_count=4)
    output_dir = tmp_path / "out"

    created = split_pdf_by_ranges(source, [(1, 2), (3, 4)], output_dir)

    second_file = fitz.open(created[1])
    try:
        assert "page 3" in second_file.load_page(0).get_text()
        assert "page 4" in second_file.load_page(1).get_text()
    finally:
        second_file.close()


def test_split_never_touches_source(tmp_path: Path) -> None:
    source = tmp_path / "combined.pdf"
    _build_pdf(source, page_count=4)
    output_dir = tmp_path / "out"

    split_pdf_by_ranges(source, [(1, 2), (3, 4)], output_dir)

    document = fitz.open(source)
    try:
        assert document.page_count == 4
    finally:
        document.close()


def test_split_rejects_when_destination_already_exists_and_writes_nothing(tmp_path: Path) -> None:
    source = tmp_path / "combined.pdf"
    _build_pdf(source, page_count=4)
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "Abgabe_01.pdf").write_bytes(b"already here")

    with pytest.raises(FileExistsError, match="Abgabe_01.pdf"):
        split_pdf_by_ranges(source, [(1, 2), (3, 4)], output_dir)

    assert not (output_dir / "Abgabe_02.pdf").exists()
    assert (output_dir / "Abgabe_01.pdf").read_bytes() == b"already here"


def test_split_rolls_back_all_files_on_mid_run_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "combined.pdf"
    _build_pdf(source, page_count=6)
    output_dir = tmp_path / "out"

    real_open = fitz.open
    call_count = {"n": 0}

    def _flaky_open(*args, **kwargs):
        if not args and not kwargs:
            call_count["n"] += 1
            if call_count["n"] == 3:  # the third new_document = fitz.open() call (last range)
                raise RuntimeError("simulated failure")
        return real_open(*args, **kwargs)

    monkeypatch.setattr(fitz, "open", _flaky_open)

    with pytest.raises(RuntimeError):
        split_pdf_by_ranges(source, [(1, 2), (3, 4), (5, 6)], output_dir)

    assert list(output_dir.glob("*.pdf")) == []
