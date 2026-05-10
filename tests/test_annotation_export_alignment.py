import fitz
import pytest

from app.adapters.gui.main_window import MainWindow
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


@pytest.mark.parametrize(
    "annotation_type,content,font_size,max_abs_dy",
    [
        ("text", "Danke!", 20, 5.0),
        ("text", "A1\nDanke", 18, 5.0),
        ("symbol", "✔", 28, 5.0),
    ],
)
def test_estimate_annotation_rect_keeps_freetext_close_to_anchor(
    annotation_type: str,
    content: str,
    font_size: int,
    max_abs_dy: float,
) -> None:
    annotation = PdfAnnotation(
        annotation_id="ann-test",
        student_pdf="Student.pdf",
        page_number=1,
        annotation_type=annotation_type,
        content=content,
        color_hex="#ff4fa3",
        x=300.0,
        y=280.0,
        task_code="A1",
        area_code="A",
        font_size=float(font_size),
        rotation_deg=0.0,
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
        rotate=0,
        align=1,
    )
    annot.update()

    bbox = _detect_pink_bbox(page)
    assert bbox is not None

    center_x = (bbox[0] + bbox[2]) / 4.0
    center_y = (bbox[1] + bbox[3]) / 4.0

    assert abs(center_x - annotation.x) <= 1.0
    assert abs(center_y - annotation.y) <= max_abs_dy

    doc.close()
