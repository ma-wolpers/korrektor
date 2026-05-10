import fitz
import pytest

from app.adapters.gui.main_window import CORRECTION_MARKER_TOOLS, MainWindow
from app.core.domain.models import PdfAnnotation


def _detect_pink_bbox(page: fitz.Page) -> tuple[int, int, int, int] | None:
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    samples = pix.samples
    width = pix.width
    height = pix.height
    channels = pix.n

    min_x = width
    min_y = height
    max_x = -1
    max_y = -1

    for y in range(height):
        row = y * width * channels
        for x in range(width):
            index = row + (x * channels)
            r = samples[index]
            g = samples[index + 1]
            b = samples[index + 2]
            if r > 190 and b > 110 and g < 170 and (r - g) > 40:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    if max_x < 0:
        return None
    return (min_x, min_y, max_x, max_y)


def _measure_drift(annotation: PdfAnnotation, font_size: int) -> tuple[float, float]:
    annotation = PdfAnnotation(
        annotation_id=annotation.annotation_id,
        student_pdf=annotation.student_pdf,
        page_number=annotation.page_number,
        annotation_type=annotation.annotation_type,
        content=annotation.content,
        color_hex=annotation.color_hex,
        x=annotation.x,
        y=annotation.y,
        task_code=annotation.task_code,
        area_code=annotation.area_code,
        font_size=annotation.font_size,
        rotation_deg=annotation.rotation_deg,
    )
    rect = MainWindow._estimate_annotation_rect(annotation, font_size)

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    annot = page.add_freetext_annot(
        rect,
        annotation.content,
        fontsize=font_size,
        fontname="helv",
        text_color=(1.0, 0.31, 0.64),
        rotate=int(MainWindow._normalize_rotation_deg(annotation.rotation_deg)),
        align=1,
    )
    annot.update()

    bbox = _detect_pink_bbox(page)
    assert bbox is not None

    center_x = (bbox[0] + bbox[2]) / 4.0
    center_y = (bbox[1] + bbox[3]) / 4.0
    doc.close()
    return (center_x - annotation.x, center_y - annotation.y)


@pytest.mark.parametrize("content", [item[1] for item in CORRECTION_MARKER_TOOLS])
@pytest.mark.parametrize("font_size", [14, 20, 28, 36])
def test_symbol_alignment_unrotated_stays_close(content: str, font_size: int) -> None:
    annotation = PdfAnnotation(
        annotation_id="ann-symbol",
        student_pdf="Student.pdf",
        page_number=1,
        annotation_type="symbol",
        content=content,
        color_hex="#ff4fa3",
        x=300.0,
        y=280.0,
        task_code="A1",
        area_code="A",
        font_size=float(font_size),
        rotation_deg=0.0,
    )
    dx, dy = _measure_drift(annotation, font_size)
    assert abs(dx) <= 1.0
    assert abs(dy) <= 6.0


@pytest.mark.parametrize("content", ["Danke!", "Hinweis", "A1\nTeilpunkte", "Sehr gut gerechnet"])
@pytest.mark.parametrize("font_size", [14, 20, 28, 36])
def test_text_alignment_unrotated_stays_reasonable(content: str, font_size: int) -> None:
    annotation = PdfAnnotation(
        annotation_id="ann-text",
        student_pdf="Student.pdf",
        page_number=1,
        annotation_type="text",
        content=content,
        color_hex="#ff4fa3",
        x=300.0,
        y=280.0,
        task_code="A1",
        area_code="A",
        font_size=float(font_size),
        rotation_deg=0.0,
    )
    dx, dy = _measure_drift(annotation, font_size)
    assert abs(dx) <= 1.0
    assert abs(dy) <= 9.0


@pytest.mark.parametrize("content", ["Danke!", "Hinweis", "A1\nTeilpunkte", "Sehr gut gerechnet"])
@pytest.mark.parametrize("font_size", [14, 20, 28, 36])
@pytest.mark.parametrize("rotation_deg", [90.0, 180.0, 270.0])
def test_text_alignment_rotated_is_bounded(content: str, font_size: int, rotation_deg: float) -> None:
    annotation = PdfAnnotation(
        annotation_id="ann-text-rot",
        student_pdf="Student.pdf",
        page_number=1,
        annotation_type="text",
        content=content,
        color_hex="#ff4fa3",
        x=300.0,
        y=280.0,
        task_code="A1",
        area_code="A",
        font_size=float(font_size),
        rotation_deg=rotation_deg,
    )
    dx, dy = _measure_drift(annotation, font_size)
    assert abs(dx) <= 24.0
    assert abs(dy) <= 24.0


@pytest.mark.parametrize("content", [item[1] for item in CORRECTION_MARKER_TOOLS])
@pytest.mark.parametrize("font_size", [14, 20, 28, 36])
@pytest.mark.parametrize("rotation_deg", [90.0, 180.0, 270.0])
def test_symbol_alignment_rotated_is_bounded(content: str, font_size: int, rotation_deg: float) -> None:
    annotation = PdfAnnotation(
        annotation_id="ann-symbol-rot",
        student_pdf="Student.pdf",
        page_number=1,
        annotation_type="symbol",
        content=content,
        color_hex="#ff4fa3",
        x=300.0,
        y=280.0,
        task_code="A1",
        area_code="A",
        font_size=float(font_size),
        rotation_deg=rotation_deg,
    )
    dx, dy = _measure_drift(annotation, font_size)
    assert abs(dx) <= 10.0
    assert abs(dy) <= 12.0
