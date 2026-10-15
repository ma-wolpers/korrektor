"""`move_annotations`: a moved mark stays inside its region and is re-homed into the region it is dragged into."""

from app.core.domain.annotation_move import MoveTarget, clamp_into_box, move_annotations
from app.core.domain.models import PdfAnnotation

_SUP = MoveTarget("sup", 1, (40.0, 40.0, 400.0, 300.0), ("1A", "1B"))
_SINGLE = MoveTarget("anna2", 2, (40.0, 400.0, 400.0, 600.0), ("1A",))


def _mark(annotation_id="m1", *, x=100.0, y=100.0, region_id="sup", page=1, task_code="1A", annotation_type="symbol", student="Anna.pdf"):
    return PdfAnnotation(annotation_id, student, page, annotation_type, "✓", "#ff0000", x, y, task_code=task_code, region_id=region_id)


def test_clamp_into_box_keeps_inside_points_and_moves_outside_points_to_the_edge() -> None:
    assert clamp_into_box(100.0, 100.0, _SUP.box) == (100.0, 100.0)
    assert clamp_into_box(10.0, 900.0, _SUP.box) == (40.0, 300.0)


def test_move_within_the_region_clamps_the_point_into_the_box() -> None:
    mark = _mark()

    assert move_annotations(mark, [], 120.0, 950.0, _SUP, "1A")

    assert (mark.x, mark.y, mark.region_id, mark.page_number) == (120.0, 300.0, "sup", 1)


def test_text_and_symbol_are_re_homed_into_the_target_region_the_same_way() -> None:
    for annotation_type in ("symbol", "text"):
        mark = _mark(annotation_type=annotation_type)

        assert move_annotations(mark, [], 200.0, 450.0, _SINGLE, "1A")

        assert (mark.region_id, mark.page_number, mark.x, mark.y) == ("anna2", 2, 200.0, 450.0)


def test_task_code_follows_the_target_region_but_an_empty_one_stays_empty() -> None:
    foreign = _mark("m-1b", task_code="1B")
    kept = _mark("m-1a", task_code="1A")
    supersymbol = _mark("m-sigma", task_code="")

    for mark in (foreign, kept, supersymbol):
        move_annotations(mark, [], 200.0, 450.0, _SINGLE, "1A")

    assert [foreign.task_code, kept.task_code, supersymbol.task_code] == ["1A", "1A", ""]


def test_followers_move_by_the_same_delta_and_are_each_clamped_and_re_homed() -> None:
    anchor = _mark("anchor", x=100.0, y=100.0)
    near = _mark("near", x=110.0, y=100.0, student="Ben.pdf")
    at_edge = _mark("edge", x=390.0, y=100.0, student="Cem.pdf")

    move_annotations(anchor, [near, at_edge], 150.0, 120.0, _SUP, "1A")

    assert [(m.x, m.y) for m in (anchor, near, at_edge)] == [(150.0, 120.0), (160.0, 120.0), (400.0, 120.0)]


def test_nothing_to_do_reports_no_change() -> None:
    mark = _mark()

    assert not move_annotations(mark, [], 100.0, 100.0, _SUP, "1A")
