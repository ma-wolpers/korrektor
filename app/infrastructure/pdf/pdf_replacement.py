"""File transaction of the Scan-Werkstatt: swap edited PDFs in, keep the originals, undo/redo by swapping back.

Layout per apply action (its own namespace, so several actions never collide):

    <Klausurordner>/.korrektor_originale/<aid>/roh/.<Name>_roh.pdf     original before this action
    <Klausurordner>/.korrektor_originale/<aid>/bearbeitet/<Name>.pdf   edited version while undone

Hashes recorded at apply time guard undo/redo: undo only runs if the live
file is still this action's result, redo only if it is still the original
(``B``'s original is ``A``'s result, so the chains fit together). Every
multi-file step is all-or-nothing with rollback; files that cannot be
restored are reported in `ScanWorkshopApplyError.leftover_files`. A hard
crash in the middle is not recoverable automatically (no crash-atomicity);
the backups stay in place in that case. The exam scan is not recursive, so
nothing below ``.korrektor_originale`` is ever loaded as a submission.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

BACKUP_DIR_NAME = ".korrektor_originale"


class ScanWorkshopApplyError(Exception):
    """Applying/undoing/redoing failed; everything was rolled back except ``leftover_files``."""

    def __init__(self, cause: BaseException, leftover_files: list[Path]) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.leftover_files = leftover_files


@dataclass(frozen=True)
class ReplacementRecord:
    """One swapped PDF of one apply action."""

    target: Path
    original_backup: Path
    edited_backup: Path
    original_hash: str
    edited_hash: str


def new_action_dir(folder: Path) -> Path:
    """Fresh, unique backup directory for one apply action (timestamp + short id)."""
    return folder / BACKUP_DIR_NAME / f"{datetime.now().strftime('%Y-%m-%d_%H%M%S')}_{uuid4().hex[:6]}"


def file_hash(path: Path) -> str:
    """SHA-256 of a file's bytes (identity check for undo/redo)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_replacements(action_dir: Path, temp_by_target: dict[Path, Path], after: Callable[[], None]) -> list[ReplacementRecord]:
    """Swap every temp file in for its target, then run ``after`` (saving the exam); all or nothing.

    Order: (1) move each original to ``roh/``, (2) move each temp file to the
    target name, (3) ``after()``. Any error rolls back in reverse order -
    edited files removed, originals restored, temp files deleted - so PDFs
    *and* exam data stay as they were; then `ScanWorkshopApplyError` is raised.
    """
    records = [
        ReplacementRecord(
            target=target,
            original_backup=action_dir / "roh" / f".{target.stem}_roh{target.suffix}",
            edited_backup=action_dir / "bearbeitet" / target.name,
            original_hash=file_hash(target),
            edited_hash=file_hash(temp),
        )
        for target, temp in temp_by_target.items()
    ]
    done: list[tuple[str, ReplacementRecord]] = []
    try:
        for record in records:
            record.original_backup.parent.mkdir(parents=True, exist_ok=True)
            record.target.replace(record.original_backup)
            done.append(("backed_up", record))
            temp_by_target[record.target].replace(record.target)
            done.append(("swapped", record))
        after()
    except Exception as exc:
        leftovers = _rollback_apply(done, temp_by_target)
        raise ScanWorkshopApplyError(exc, leftovers) from exc
    return records


def _rollback_apply(done, temp_by_target) -> list[Path]:
    """Undo the finished steps in reverse order; return the paths that need a manual look.

    If an edited file cannot be removed (e.g. open in a viewer), its original
    deliberately stays in ``roh/`` instead of being forced over it - both
    paths are reported, so nothing is lost and the user can sort it out.
    """
    leftovers: list[Path] = []
    stuck: set[Path] = set()
    for step, record in reversed(done):
        if step == "backed_up" and record.target in stuck:
            leftovers.append(record.original_backup)
            continue
        try:
            if step == "swapped":
                record.target.unlink()
            else:
                record.original_backup.replace(record.target)
        except OSError:
            if step == "swapped":
                stuck.add(record.target)
            leftovers.append(record.target if step == "swapped" else record.original_backup)
    for temp in temp_by_target.values():
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            leftovers.append(temp)
    return leftovers


def undo_replacements(records: list[ReplacementRecord], after: Callable[[], None]) -> None:
    """Put the originals back (edited versions to ``bearbeitet/``), then ``after()``; all or nothing."""
    _swap_all(records, live_hash="edited", after=after)


def redo_replacements(records: list[ReplacementRecord], after: Callable[[], None]) -> None:
    """Put the edited versions back (originals to ``roh/``), then ``after()``; all or nothing."""
    _swap_all(records, live_hash="original", after=after)


def _swap_all(records: list[ReplacementRecord], *, live_hash: str, after: Callable[[], None]) -> None:
    """Hash-check every live file first, then do all moves and ``after()``; any error moves the finished ones back (leftovers reported)."""
    for record in records:
        expected = record.edited_hash if live_hash == "edited" else record.original_hash
        if not record.target.exists() or file_hash(record.target) != expected:
            raise ScanWorkshopApplyError(
                RuntimeError(f"{record.target.name} wurde seitdem verändert - Rückgängig/Wiederholen abgebrochen."), []
            )
    moves: list[tuple[Path, Path]] = []
    for record in records:
        if live_hash == "edited":
            moves += [(record.target, record.edited_backup), (record.original_backup, record.target)]
        else:
            moves += [(record.target, record.original_backup), (record.edited_backup, record.target)]
    done: list[tuple[Path, Path]] = []
    try:
        for source, destination in moves:
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.replace(destination)
            done.append((source, destination))
        after()
    except Exception as exc:
        leftovers = []
        for source, destination in reversed(done):
            try:
                destination.replace(source)
            except OSError:
                leftovers.append(destination)
        raise ScanWorkshopApplyError(exc, leftovers) from exc
