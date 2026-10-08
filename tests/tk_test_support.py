"""Shared helpers for real-Tk tests against Korrektor's `MainWindow` (synthetic data only).

Used together with the session-scoped ``korrektor_window`` fixture from
`conftest.py`. Key events go to the *focused* widget, so tests that send
key events take the OS focus and are opt-in via ``TK_FOCUS_TESTS=1``
(`FOCUS_ONLY`), the same convention as in bw-gui.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import fitz
import pytest

FOCUS_ONLY = pytest.mark.skipif(
    os.environ.get("TK_FOCUS_TESTS") != "1",
    reason="sends key events to the focused widget; run with TK_FOCUS_TESTS=1",
)


def build_pdf(path: Path, pages: int, tag: str, *, locked: bool = False) -> Path:
    """Write an A4 PDF whose pages contain the text ``"{tag} {n}"`` (optionally password-protected)."""
    document = fitz.open()
    for index in range(pages):
        document.new_page(width=595, height=842).insert_text((50, 80), f"{tag} {index + 1}", fontsize=30)
    if locked:
        document.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="y")
    else:
        document.save(path)
    document.close()
    return path


def pdf_texts(path: Path) -> list[str]:
    """Return the stripped text of every page of ``path``."""
    document = fitz.open(path)
    try:
        return [document.load_page(index).get_text().strip() for index in range(document.page_count)]
    finally:
        document.close()


def settle(window, ms: int = 80) -> None:
    """Process Tk events for ``ms`` milliseconds so debounced ``after`` callbacks can run."""
    deadline = time.monotonic() + ms / 1000
    while time.monotonic() < deadline:
        window.update()
        time.sleep(0.005)
    window.update()
