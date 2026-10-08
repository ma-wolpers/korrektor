from pathlib import Path

import fitz
import pytest

from app.infrastructure.pdf.pdf_sources import PdfSourceInfo, inspect_pdf_sources


def _build_pdf(path: Path, page_count: int) -> Path:
    document = fitz.open()
    for _ in range(page_count):
        document.new_page()
    document.save(path)
    document.close()
    return path


def _build_locked_pdf(path: Path) -> Path:
    document = fitz.open()
    document.new_page()
    document.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="y")
    document.close()
    return path


def test_reports_every_problem_and_keeps_valid_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ok = _build_pdf(tmp_path / "ok.pdf", 3)
    locked = _build_locked_pdf(tmp_path / "locked.pdf")
    ok2 = _build_pdf(tmp_path / "ok2.pdf", 1)
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a pdf")

    opened: list = []
    real_open = fitz.open

    def _recording_open(*args, **kwargs):
        document = real_open(*args, **kwargs)
        opened.append(document)
        return document

    monkeypatch.setattr(fitz, "open", _recording_open)

    infos, problems = inspect_pdf_sources([ok, locked, ok2, broken])

    assert infos == [PdfSourceInfo(ok, 3), PdfSourceInfo(ok2, 1)]
    assert [(problem.path, problem.reason.split(" ")[0]) for problem in problems] == [
        (locked, "passwortgeschützt"),
        (broken, "nicht"),
    ]
    assert opened and all(document.is_closed for document in opened)


def test_non_pdf_file_is_reported(tmp_path: Path) -> None:
    """PyMuPDF also opens images as documents; they must not pass as a PDF source."""
    image = tmp_path / "scan.png"
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 4, 4), False)
    image.write_bytes(pixmap.tobytes("png"))

    infos, problems = inspect_pdf_sources([image])

    assert infos == []
    assert [problem.reason for problem in problems] == ["keine PDF-Datei"]
