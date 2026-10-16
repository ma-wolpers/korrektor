from pathlib import Path

from app.infrastructure.rendering.competency_chart_renderer import (
    figure_to_pdf_bytes,
    figure_to_png_bytes,
    percent_axis_top,
    render_bar_chart,
    render_radar_chart,
    save_figure,
)


def test_render_radar_chart_produces_valid_png_bytes() -> None:
    fig = render_radar_chart([("1A", 80.0), ("1B", 60.0), ("2A", 90.0)], title="Testergebnis")

    png_bytes = figure_to_png_bytes(fig)

    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png_bytes) > 100


def test_render_bar_chart_produces_valid_png_bytes() -> None:
    fig = render_bar_chart([("Geometrie", 75.0), ("Algebra", 50.0)], title="Testergebnis")

    png_bytes = figure_to_png_bytes(fig)

    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_render_radar_chart_handles_empty_values_without_raising() -> None:
    fig = render_radar_chart([], title="Leer")
    png_bytes = figure_to_png_bytes(fig)
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_render_bar_chart_handles_empty_values_without_raising() -> None:
    fig = render_bar_chart([], title="Leer")
    png_bytes = figure_to_png_bytes(fig)
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_save_figure_writes_png_file(tmp_path: Path) -> None:
    fig = render_bar_chart([("1A", 80.0)])
    out_path = tmp_path / "chart.png"

    save_figure(fig, out_path)

    assert out_path.exists()
    assert out_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_figure_to_pdf_bytes_produces_valid_single_page_pdf() -> None:
    fig = render_radar_chart([("1A", 80.0), ("1B", 40.0)], title="Testergebnis")

    pdf_bytes = figure_to_pdf_bytes(fig)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 100


def test_save_figure_writes_pdf_file(tmp_path: Path) -> None:
    fig = render_radar_chart([("1A", 80.0), ("1B", 40.0)])
    out_path = tmp_path / "chart.pdf"

    save_figure(fig, out_path)

    assert out_path.exists()
    assert out_path.read_bytes().startswith(b"%PDF")


def test_percent_axis_grows_above_100_for_bonus_points() -> None:
    assert percent_axis_top([]) == 100.0
    assert percent_axis_top([40.0, 100.0]) == 100.0
    assert percent_axis_top([101.0]) == 125.0
    assert percent_axis_top([150.0]) == 150.0
    assert render_bar_chart([("Geometrie", 140.0)]).axes[0].get_ylim()[1] == 150.0
    assert render_radar_chart([("1A", 140.0), ("1B", 50.0), ("2A", 90.0)]).axes[0].get_ylim()[1] == 150.0
