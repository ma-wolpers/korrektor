from app.infrastructure.repositories.file_utils import build_pdf_filename_from_name


def test_build_pdf_filename_replaces_spaces_and_keeps_case() -> None:
    assert build_pdf_filename_from_name("Anna Müller") == "Anna_Müller.pdf"


def test_build_pdf_filename_collapses_internal_whitespace() -> None:
    assert build_pdf_filename_from_name("  Anna   Müller  ") == "Anna_Müller.pdf"


def test_build_pdf_filename_strips_invalid_windows_characters() -> None:
    assert build_pdf_filename_from_name('Anna "Ana" Müller?!') == "Anna_Ana_Müller!.pdf"


def test_build_pdf_filename_strips_trailing_dots_and_spaces() -> None:
    assert build_pdf_filename_from_name("Anna Müller. ") == "Anna_Müller.pdf"


def test_build_pdf_filename_defuses_reserved_windows_device_name() -> None:
    result = build_pdf_filename_from_name("CON")
    assert result is not None
    assert result != "CON.pdf"
    assert result == "CON_name.pdf"


def test_build_pdf_filename_defuses_reserved_name_case_insensitively() -> None:
    result = build_pdf_filename_from_name("con")
    assert result is not None
    assert result.upper() != "CON.PDF"


def test_build_pdf_filename_truncates_overlong_names() -> None:
    result = build_pdf_filename_from_name("A" * 300)
    assert result is not None
    assert len(result) <= 154  # 150 stem chars + ".pdf"


def test_build_pdf_filename_returns_none_for_empty_input() -> None:
    assert build_pdf_filename_from_name("") is None


def test_build_pdf_filename_returns_none_when_only_invalid_characters() -> None:
    assert build_pdf_filename_from_name('???***"""') is None


def test_build_pdf_filename_returns_none_for_whitespace_only_input() -> None:
    assert build_pdf_filename_from_name("   ") is None
