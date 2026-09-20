from app.core.domain.grading_scale import (
    SCALE_TYPE_SCHOOL_1_6,
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    GradeThreshold,
    GradingScale,
)


def _scale(**overrides) -> GradingScale:
    base = dict(
        scale_id="scale-1",
        name="Mathe 8",
        subject="Mathe",
        year="8",
        school="Musterschule",
        scale_type=SCALE_TYPE_SCHOOL_1_6,
        thresholds=[
            GradeThreshold(min_percent=80.0, grade_label="1"),
            GradeThreshold(min_percent=65.0, grade_label="2"),
        ],
    )
    base.update(overrides)
    return GradingScale(**base)


def test_grading_scale_to_dict_from_dict_roundtrip() -> None:
    scale = _scale()
    restored = GradingScale.from_dict(scale.to_dict())

    assert restored.scale_id == scale.scale_id
    assert restored.name == scale.name
    assert restored.scale_type == scale.scale_type
    assert restored.status == STATUS_ACTIVE
    assert [t.to_dict() for t in restored.thresholds] == [t.to_dict() for t in scale.thresholds]


def test_grading_scale_from_dict_defaults_status_to_active() -> None:
    scale = GradingScale.from_dict({"scale_id": "x", "name": "n", "subject": "s", "year": "8", "school": "sch", "scale_type": "t"})
    assert scale.status == STATUS_ACTIVE


def test_grading_scale_archived_status_roundtrips() -> None:
    scale = _scale(status=STATUS_ARCHIVED)
    restored = GradingScale.from_dict(scale.to_dict())
    assert restored.status == STATUS_ARCHIVED


def test_to_snapshot_copies_fields_and_sets_source_scale_id() -> None:
    scale = _scale()
    snapshot = scale.to_snapshot(assigned_at="2026-09-19T10:00:00.000000Z")

    assert snapshot.source_scale_id == scale.scale_id
    assert snapshot.name == scale.name
    assert snapshot.subject == scale.subject
    assert snapshot.scale_type == scale.scale_type
    assert snapshot.assigned_at == "2026-09-19T10:00:00.000000Z"
    assert [t.grade_label for t in snapshot.thresholds] == [t.grade_label for t in scale.thresholds]


def test_to_snapshot_is_independent_of_later_template_edits() -> None:
    """The whole point of the snapshot mechanism: editing the template afterwards must not reach back."""
    scale = _scale()
    snapshot = scale.to_snapshot(assigned_at="2026-09-19T10:00:00.000000Z")

    scale.thresholds[0].grade_label = "changed"
    scale.name = "changed name"

    assert snapshot.thresholds[0].grade_label == "1"
    assert snapshot.name == "Mathe 8"


def test_grading_scale_snapshot_to_dict_from_dict_roundtrip() -> None:
    scale = _scale()
    snapshot = scale.to_snapshot(assigned_at="2026-09-19T10:00:00.000000Z")

    from app.core.domain.grading_scale import GradingScaleSnapshot

    restored = GradingScaleSnapshot.from_dict(snapshot.to_dict())
    assert restored.source_scale_id == snapshot.source_scale_id
    assert restored.assigned_at == snapshot.assigned_at
    assert [t.to_dict() for t in restored.thresholds] == [t.to_dict() for t in snapshot.thresholds]
