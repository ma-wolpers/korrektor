from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # noqa: E402 - must run before any other matplotlib import/use in this process;
# korrektor never embeds a live matplotlib canvas in Tkinter (a rendered
# PNG is shown instead, see main_window_student_result.py), so a
# non-interactive backend is always correct here and avoids pulling in a
# GUI-toolkit-specific matplotlib backend as an accidental extra dependency.

from matplotlib.axes import Axes  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402


def draw_radar(axes: Axes, values: list[tuple[str, float]], *, title: str = "") -> None:
    """Draw a Spinnennetz/radar chart of already-normalized percentages (0-100) into `axes`.

    `axes` must already have been created with `projection="polar"` (a
    plain rectangular Axes cannot be converted after the fact) - see
    `render_radar_chart` for the standalone-figure case and
    `student_result_report_renderer.py` for the full-report case, which
    both create their own `axes` and call this to actually draw into it.
    Purely a rendering step (Meilenstein 6 der Korrektor-Wunschliste,
    "Infrastructure rendert fertige Werte, berechnet nichts fachlich
    selbst") - `values` must already come from
    `app.core.domain.student_result.task_competency_percentages`/
    `category_competency_percentages`.
    """
    labels = [label for label, _percent in values]
    percents = [percent for _label, percent in values]
    count = len(labels)
    if count == 0:
        axes.text(0.5, 0.5, "Keine Daten", ha="center", va="center", transform=axes.transAxes)
        return

    angles = [index / count * 2 * math.pi for index in range(count)]
    angles_closed = angles + angles[:1]
    percents_closed = percents + percents[:1]

    axes.plot(angles_closed, percents_closed, linewidth=2, color="#1d4ed8")
    axes.fill(angles_closed, percents_closed, alpha=0.25, color="#1d4ed8")
    axes.set_xticks(angles)
    axes.set_xticklabels(labels)
    axes.set_ylim(0, 100)
    axes.set_yticks([0, 25, 50, 75, 100])
    if title:
        axes.set_title(title)


def draw_bar(axes: Axes, values: list[tuple[str, float]], *, title: str = "") -> None:
    """Draw a bar chart of already-normalized percentages (0-100) into `axes`. See `draw_radar`."""
    labels = [label for label, _percent in values]
    percents = [percent for _label, percent in values]
    if not labels:
        axes.text(0.5, 0.5, "Keine Daten", ha="center", va="center", transform=axes.transAxes)
        return

    axes.bar(labels, percents, color="#1d4ed8")
    axes.set_ylim(0, 100)
    axes.set_ylabel("%")
    if title:
        axes.set_title(title)
    for label in axes.get_xticklabels():
        label.set_rotation(30)
        label.set_ha("right")


def render_radar_chart(values: list[tuple[str, float]], *, title: str = "") -> Figure:
    """Render a standalone Spinnennetz/radar chart Figure. Uses the `Figure` API directly (not `pyplot`).

    so repeated calls in this long-running GUI process never leak into
    pyplot's global figure registry.
    """
    fig = Figure(figsize=(5.0, 5.0))
    axes = fig.add_subplot(111, polar=True)
    draw_radar(axes, values, title=title)
    fig.tight_layout()
    return fig


def render_bar_chart(values: list[tuple[str, float]], *, title: str = "") -> Figure:
    """Render a standalone bar chart Figure. See `render_radar_chart`."""
    fig = Figure(figsize=(6.0, 4.0))
    axes = fig.add_subplot(111)
    draw_bar(axes, values, title=title)
    fig.tight_layout()
    return fig


def figure_to_png_bytes(fig: Figure) -> bytes:
    """Render `fig` to PNG bytes, for display as a `tk.PhotoImage` (no file written)."""
    import io

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=100)
    return buffer.getvalue()


def save_figure(fig: Figure, path: Path) -> None:
    """Save `fig` to `path`; the format is inferred from the file extension (.png/.jpg/.pdf)."""
    fig.savefig(path)
