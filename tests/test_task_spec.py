"""Task input shorthand: parser, formatter round trip, natural order, main task."""

import pytest

from app.core.domain.task_spec import TaskSpec, format_task_specs, main_task_of, parse_task_specs, task_sort_key


def _pairs(text, **kwargs):
    result = parse_task_specs(text, **kwargs)
    assert result.error is None, result.error
    return [(item.code, item.points) for item in result.items]


def test_example_of_the_user_expands_runs_with_individual_points():
    assert _pairs("4a-d:1,4,2,3;5a:2;6b-c:1,4") == [
        ("4A", 1), ("4B", 4), ("4C", 2), ("4D", 3), ("5A", 2), ("6B", 1), ("6C", 4),
    ]
    assert _pairs("4a:1;4b:4;4c:2;4d:3;5a:2;6b:1;6c:4") == _pairs("4a-d:1,4,2,3;5a:2;6b-c:1,4")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("5a:1,5", [("5A", 1.5)]),  # decimal comma for one code
        ("4a-b:1.5,2", [("4A", 1.5), ("4B", 2.0)]),  # decimal point inside lists
        ("4a-c:2", [("4A", 2), ("4B", 2), ("4C", 2)]),  # one value for all
        ("2.1-3:1,2,3", [("2.1", 1), ("2.2", 2), ("2.3", 3)]),  # digit run
        ("1-3:2", [("1", 2), ("2", 2), ("3", 2)]),
        ("4a-4c:1", [("4A", 1), ("4B", 1), ("4C", 1)]),  # long form
        ("4A-d:1", [("4A", 1), ("4B", 1), ("4C", 1), ("4D", 1)]),  # case is canonicalised
        ("4a:1\n 4b : 2 \n\n", [("4A", 1), ("4B", 2)]),  # form mode, whitespace
    ],
)
def test_valid_inputs(text, expected):
    assert _pairs(text) == expected


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("4a-d:1,4,2", "4 Aufgaben, aber 3 Punktwerte"),
        ("4a-c:1,,2", "Punktwert fehlt"),
        ("4a:", "Punktwert fehlt"),
        ("4a", "Punkte fehlen"),
        ("4d-a:1", "rückwärts"),
        ("4a-3:1", "Buchstaben"),
        ("4a-5b:1", "nicht zur selben Aufgabe"),
        ("4a:1;4A:2", "mehrfach"),
        ("4a-c:1;4b:2", "mehrfach"),
        ("4a:x", "keine Zahl"),
        ("4a:-1", "≥ 0"),
        ("4a:1:2", "Doppelpunkte"),
        (":2", "Code fehlt"),
        ("5a:1,5,2", "mehrere Punktwerte"),
    ],
)
def test_invalid_inputs_name_the_problem(text, message):
    result = parse_task_specs(text)
    assert result.items == () and message in result.error


def test_codes_without_points_only_where_allowed():
    assert _pairs("4c-d;5a", require_points=False) == [("4C", None), ("4D", None), ("5A", None)]
    assert _pairs("4c-d;5a:2", require_points=False) == [("4C", None), ("4D", None), ("5A", 2)]


@pytest.mark.parametrize(
    "text",
    ["4a-d:1,4,2,3;5a:2;6b-c:1,4", "5a:1,5", "4a-b:1.5,2", "4a-c:2", "2.1-3:1,2,3", "1;3;5", "4c-d;5a:2", "7A:2;4B"],
)
def test_format_round_trip_keeps_codes_and_points(text):
    parsed = parse_task_specs(text, require_points=False).items
    formatted = format_task_specs(parsed)
    assert parse_task_specs(formatted, require_points=False).items == parsed
    assert parse_task_specs(format_task_specs(parsed, separator="\n"), require_points=False).items == parsed


def test_format_compresses_runs_and_accepts_tuples():
    assert format_task_specs([("4A", 1), ("4B", 4), ("4C", 2), ("5A", 2)]) == "4A-C:1,4,2; 5A:2"
    assert format_task_specs([TaskSpec("4A", 2), TaskSpec("4B", 2)]) == "4A-B:2"
    assert format_task_specs([("5A", 1.5)]) == "5A:1,5"
    assert format_task_specs([("4C", None), ("4D", None), ("4E", 1)]) == "4C-D; 4E:1"


def test_natural_order_and_main_task():
    codes = ["10A", "4B", "2", "4A", "2.10", "2.1"]
    assert sorted(codes, key=task_sort_key) == ["2", "2.1", "2.10", "4A", "4B", "10A"]
    assert main_task_of("4b") == "4" and main_task_of("2.1B") == "2.1" and main_task_of("A") == "A" and main_task_of("12") == "12"
