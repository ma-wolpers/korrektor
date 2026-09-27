from app.infrastructure.repositories.file_utils import render_filename_template


def test_render_filename_template_substitutes_all_known_placeholders() -> None:
    result = render_filename_template(
        "{Nachname}_{Name}_{Klasse}_{Fach}_{Nr}",
        display_name="Anna Müller",
        school_class="10a",
        subject="Mathematik",
        index=3,
    )
    assert result == "{Nachname}_Anna Müller_10a_Mathematik_03"


def test_render_filename_template_pads_nr_to_two_digits() -> None:
    result = render_filename_template(
        "{Nr}", display_name="Anna", school_class="", subject="", index=7
    )
    assert result == "07"


def test_render_filename_template_does_not_truncate_nr_beyond_two_digits() -> None:
    result = render_filename_template(
        "{Nr}", display_name="Anna", school_class="", subject="", index=123
    )
    assert result == "123"


def test_render_filename_template_leaves_unknown_placeholder_literal() -> None:
    result = render_filename_template(
        "{Unbekannt}_{Name}", display_name="Anna", school_class="", subject="", index=1
    )
    assert result == "{Unbekannt}_Anna"


def test_render_filename_template_keeps_spaces_instead_of_underscoring() -> None:
    """Export filenames favour readability - unlike Namenmodus, spaces are kept."""
    result = render_filename_template(
        "{Name}", display_name="Anna Müller", school_class="", subject="", index=1
    )
    assert result == "Anna Müller"


def test_render_filename_template_strips_invalid_windows_characters() -> None:
    result = render_filename_template(
        "{Name}", display_name='Anna "Ana" Müller?!', school_class="", subject="", index=1
    )
    assert result == "Anna Ana Müller!"


def test_render_filename_template_returns_none_when_nothing_valid_remains() -> None:
    result = render_filename_template(
        "{Name}", display_name='???***"""', school_class="", subject="", index=1
    )
    assert result is None


def test_render_filename_template_nr_is_stable_across_export_selection_subsets() -> None:
    """The `{Nr}` contract: the caller must pass the person's stable index within
    `exam.students`, not their position within the current export selection - a
    person's number must not change depending on who else is exported alongside them."""
    students = ["Anna", "Ben", "Chris"]
    index_by_student = {name: position for position, name in enumerate(students, start=1)}

    full_selection_ben = render_filename_template(
        "{Nr}_{Name}", display_name="Ben", school_class="", subject="", index=index_by_student["Ben"]
    )
    partial_selection_ben = render_filename_template(
        "{Nr}_{Name}", display_name="Ben", school_class="", subject="", index=index_by_student["Ben"]
    )

    assert full_selection_ben == partial_selection_ben == "02_Ben"
