from app.adapters.undo import HistoryAction, UndoHistory


def test_push_undo_redo_cycle() -> None:
    history = UndoHistory()
    state: list[str] = []

    action = HistoryAction(
        description="append-a",
        undo=lambda: state.pop(),
        redo=lambda: state.append("a"),
    )

    action.redo()
    history.push(action)
    assert state == ["a"]
    assert history.peek_undo() == "append-a"

    undone = history.undo()
    assert undone is not None
    assert undone.description == "append-a"
    assert undone.context == "content"
    assert state == []
    assert history.peek_redo() == "append-a"

    redone = history.redo()
    assert redone is not None
    assert redone.description == "append-a"
    assert state == ["a"]


def test_push_clears_redo_stack() -> None:
    history = UndoHistory()
    state: list[str] = []

    first = HistoryAction(
        description="first",
        undo=lambda: state.pop(),
        redo=lambda: state.append("first"),
    )
    second = HistoryAction(
        description="second",
        undo=lambda: state.pop(),
        redo=lambda: state.append("second"),
    )

    first.redo()
    history.push(first)
    history.undo()
    assert history.can_redo() is True

    second.redo()
    history.push(second)
    assert history.can_redo() is False
    assert history.peek_undo() == "second"
