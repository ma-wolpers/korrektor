from dataclasses import dataclass
from pathlib import Path

import fitz
import pytest

from app.infrastructure.pdf.pdf_splitter import SplitWriteError, write_split_outputs


@dataclass(frozen=True)
class _Output:
    filename: str
    page_ranges: tuple[tuple[int, int], ...]


def _build_pdf(path: Path, page_count: int) -> None:
    document = fitz.open()
    for i in range(page_count):
        document.new_page(width=200, height=300).insert_text((20, 20), f"page {i + 1}")
    document.save(path)
    document.close()


@pytest.fixture
def source(tmp_path: Path):
    path = tmp_path / "combined.pdf"
    _build_pdf(path, page_count=6)
    document = fitz.open(path)
    yield document
    document.close()


def _page_texts(path: Path) -> list[str]:
    document = fitz.open(path)
    try:
        return [document.load_page(index).get_text().strip() for index in range(document.page_count)]
    finally:
        document.close()


def test_writes_one_file_per_output_with_its_pages(source, tmp_path: Path) -> None:
    created = write_split_outputs(
        source, [_Output("Anna.pdf", ((1, 3),)), _Output("Ben.pdf", ((4, 6),))], tmp_path / "out"
    )

    assert [path.name for path in created] == ["Anna.pdf", "Ben.pdf"]
    assert _page_texts(created[0]) == ["page 1", "page 2", "page 3"]
    assert _page_texts(created[1]) == ["page 4", "page 5", "page 6"]


def test_multi_range_output_keeps_given_order(source, tmp_path: Path) -> None:
    created = write_split_outputs(source, [_Output("Anna.pdf", ((2, 3), (6, 6)))], tmp_path / "out")

    assert _page_texts(created[0]) == ["page 2", "page 3", "page 6"]


def test_source_document_stays_open_and_unchanged(source, tmp_path: Path) -> None:
    write_split_outputs(source, [_Output("Anna.pdf", ((1, 6),))], tmp_path / "out")

    assert not source.is_closed
    assert source.page_count == 6


def test_rejects_existing_destination_and_writes_nothing(source, tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "Anna.pdf").write_bytes(b"already here")

    with pytest.raises(FileExistsError, match="Anna.pdf"):
        write_split_outputs(source, [_Output("Anna.pdf", ((1, 2),)), _Output("Ben.pdf", ((3, 4),))], output_dir)

    assert not (output_dir / "Ben.pdf").exists()
    assert (output_dir / "Anna.pdf").read_bytes() == b"already here"


@pytest.mark.parametrize(
    "outputs, message",
    [
        ([_Output("Anna.pdf", ((1, 2),)), _Output("anna.PDF", ((3, 4),))], "Doppelter"),
        ([_Output("Anna.pdf", ())], "Keine Seiten"),
        ([_Output("Anna.pdf", ((5, 7),))], "Ungueltiger Seitenbereich"),
        ([_Output("Anna.pdf", ((0, 2),))], "Ungueltiger Seitenbereich"),
    ],
)
def test_invalid_outputs_raise_before_anything_is_written(source, tmp_path: Path, outputs, message) -> None:
    output_dir = tmp_path / "out"

    with pytest.raises(ValueError, match=message):
        write_split_outputs(source, outputs, output_dir)

    assert not output_dir.exists() or list(output_dir.iterdir()) == []


def test_rolls_back_all_files_on_mid_run_failure(source, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_dir = tmp_path / "out"
    real_open = fitz.open
    calls = {"n": 0}

    def _flaky_open(*args, **kwargs):
        if not args and not kwargs:
            calls["n"] += 1
            if calls["n"] == 3:
                raise RuntimeError("simulated failure")
        return real_open(*args, **kwargs)

    monkeypatch.setattr(fitz, "open", _flaky_open)

    with pytest.raises(SplitWriteError) as excinfo:
        write_split_outputs(
            source, [_Output("A.pdf", ((1, 2),)), _Output("B.pdf", ((3, 4),)), _Output("C.pdf", ((5, 6),))], output_dir
        )

    assert str(excinfo.value.cause) == "simulated failure"
    assert excinfo.value.leftover_files == []
    assert list(output_dir.glob("*.pdf")) == []


def test_partially_saved_destination_is_removed(source, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_dir = tmp_path / "out"
    real_save = fitz.Document.save

    def _save_then_fail(self, filename, *args, **kwargs):
        if Path(filename).name == "B.pdf":
            Path(filename).write_bytes(b"half written")
            raise OSError("disk full")
        return real_save(self, filename, *args, **kwargs)

    monkeypatch.setattr(fitz.Document, "save", _save_then_fail)

    with pytest.raises(SplitWriteError):
        write_split_outputs(source, [_Output("A.pdf", ((1, 2),)), _Output("B.pdf", ((3, 4),))], output_dir)

    assert list(output_dir.glob("*.pdf")) == []


def test_files_that_cannot_be_removed_are_reported(source, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_dir = tmp_path / "out"
    real_save = fitz.Document.save
    real_unlink = Path.unlink

    def _fail_on_b(self, filename, *args, **kwargs):
        if Path(filename).name == "B.pdf":
            raise OSError("disk full")
        return real_save(self, filename, *args, **kwargs)

    def _locked_unlink(self, *args, **kwargs):
        if self.name == "A.pdf":
            raise PermissionError("locked")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(fitz.Document, "save", _fail_on_b)
    monkeypatch.setattr(Path, "unlink", _locked_unlink)

    with pytest.raises(SplitWriteError) as excinfo:
        write_split_outputs(source, [_Output("A.pdf", ((1, 2),)), _Output("B.pdf", ((3, 4),))], output_dir)

    assert [path.name for path in excinfo.value.leftover_files] == ["A.pdf"]


def test_transitional_sequential_wrapper_names_files_abgabe_nn(tmp_path: Path) -> None:
    from app.infrastructure.pdf.pdf_splitter import split_pdf_by_ranges

    path = tmp_path / "combined.pdf"
    _build_pdf(path, page_count=4)

    created = split_pdf_by_ranges(path, [(1, 2), (3, 4)], tmp_path / "out")

    assert [created_path.name for created_path in created] == ["Abgabe_01.pdf", "Abgabe_02.pdf"]
