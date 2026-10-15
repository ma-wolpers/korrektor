"""mark_renderer caches: bounded, never stale, fast when repeated (load test)."""

from __future__ import annotations

import time

from app.core.domain.mark_symbols import MARK_SYMBOLS
from app.infrastructure.rendering.mark_renderer import MarkStyle, clear_mark_caches, mark_cache_sizes, render_mark

ZOOMS = [0.6 + 0.15 * step for step in range(10)]


def _styles() -> list[MarkStyle]:
    """300 comments (every sixth with a formula) and 200 symbol variants."""
    styles = [
        MarkStyle("text", f"Kommentar {n} $x_{{{n}}}^2$" if n % 6 == 0 else f"Kommentar Nummer {n}", "#1d4ed8", 14.0)
        for n in range(300)
    ]
    for n in range(200):
        symbol = MARK_SYMBOLS[n % len(MARK_SYMBOLS)]
        styles.append(MarkStyle("symbol", symbol.content, "#d62828", 12.0 + n % 7, 90.0 * (n % 4), bool(n % 2)))
    return styles


def test_same_values_same_bytes_changed_values_new_bytes():
    clear_mark_caches()
    base = MarkStyle("text", "Gut", "#d62828", 14.0)
    first = render_mark(base, 1.5).png
    assert render_mark(MarkStyle("text", "Gut", "#d62828", 14.0), 1.5).png == first
    variants = [
        MarkStyle("text", "Gut!", "#d62828", 14.0),
        MarkStyle("text", "Gut", "#1d4ed8", 14.0),
        MarkStyle("text", "Gut", "#d62828", 16.0),
        MarkStyle("text", "Gut", "#d62828", 14.0, 90.0),
        MarkStyle("text", "Gut", "#d62828", 14.0, 0.0, True),
    ]
    for variant in variants:
        assert render_mark(variant, 1.5).png != first, variant
    assert render_mark(base, 2.0).png != first  # zoom


def test_load_many_marks_and_repeated_zoom_stays_bounded_and_fast():
    clear_mark_caches()
    styles = _styles()
    visible = styles[:40]  # what one screen shows while zooming (40 × 10 zooms fit into stage 2)
    for style in styles:
        render_mark(style, 1.0)
    for _round in range(2):
        for zoom in ZOOMS:
            for style in visible:
                render_mark(style, zoom)
    stage1, stage2 = mark_cache_sizes()
    assert stage1 <= 256 and stage2 <= 512

    started = time.perf_counter()
    for zoom in ZOOMS:
        for style in visible:
            render_mark(style, zoom)
    assert time.perf_counter() - started < 2.0  # repeated zoom is served from the caches
