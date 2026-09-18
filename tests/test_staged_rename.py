from pathlib import Path

import pytest

from app.adapters.gui.ui_intent_controller import UiIntentController


def _touch(folder: Path, name: str, content: str) -> None:
    (folder / name).write_text(content, encoding="utf-8")


def test_apply_staged_renames_handles_a_b_swap(tmp_path: Path) -> None:
    _touch(tmp_path, "A.pdf", "content-a")
    _touch(tmp_path, "B.pdf", "content-b")

    UiIntentController._apply_staged_renames(tmp_path, [("A.pdf", "B.pdf"), ("B.pdf", "A.pdf")])

    assert (tmp_path / "A.pdf").read_text(encoding="utf-8") == "content-b"
    assert (tmp_path / "B.pdf").read_text(encoding="utf-8") == "content-a"


def test_apply_staged_renames_rolls_back_completely_on_mid_operation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _touch(tmp_path, "A.pdf", "content-a")
    _touch(tmp_path, "B.pdf", "content-b")
    _touch(tmp_path, "C.pdf", "content-c")

    original_rename = Path.rename
    call_count = {"n": 0}

    def _flaky_rename(self: Path, target: Path) -> Path:
        call_count["n"] += 1
        # Fail on the 4th physical rename call (partway through phase 2),
        # simulating e.g. a locked file or a transient OS error.
        if call_count["n"] == 4:
            raise OSError("simulated failure")
        return original_rename(self, target)

    monkeypatch.setattr(Path, "rename", _flaky_rename)

    with pytest.raises(OSError):
        UiIntentController._apply_staged_renames(
            tmp_path, [("A.pdf", "X.pdf"), ("B.pdf", "Y.pdf"), ("C.pdf", "Z.pdf")]
        )

    # Folder must be back exactly as it started - no temp files, no partial renames.
    assert (tmp_path / "A.pdf").read_text(encoding="utf-8") == "content-a"
    assert (tmp_path / "B.pdf").read_text(encoding="utf-8") == "content-b"
    assert (tmp_path / "C.pdf").read_text(encoding="utf-8") == "content-c"
    remaining_names = {path.name for path in tmp_path.iterdir()}
    assert remaining_names == {"A.pdf", "B.pdf", "C.pdf"}
