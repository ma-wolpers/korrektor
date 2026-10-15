"""Drawn correction symbols (``MarkSymbol.drawing == "drawn"``) as Pillow images.

Every shape is drawn unrotated and unmirrored on a transparent RGBA canvas sized in
"em" (1 em = the mark's font size in pixels) and then cropped to its ink plus a small
padding. The image centre is therefore the centre of the visible shape, which is
where ``PdfAnnotation.x/y`` points - for the drawn shapes exactly as for glyphs and
texts (see ``mark_renderer``). Rotation and mirroring are applied afterwards by the
renderer, never here.

Shapes (unrotated), with their size in em:

* ``strike``         - rising diagonal stroke, 3 × 1.2, like a line crossing out a word
* ``wavy``           - horizontal sine wave, 4 wide, three periods (underline for form errors)
* ``arrow_straight`` - arrow pointing right, 2.6 long
* ``arrow_curved``   - half-circle arc from left over the top, head pointing down at the right end
* ``jargon``         - empty speech bubble with its tail at the bottom left
* ``example``        - "Bsp" over a bold "≠" over "Bew" (example is no proof)
"""

from __future__ import annotations

import math
from collections.abc import Callable

from PIL import Image, ImageDraw, ImageFont

Color = tuple[int, int, int, int]
TRANSPARENT: Color = (0, 0, 0, 0)


def crop_to_ink(image: Image.Image, padding_px: int) -> Image.Image:
    """Crop ``image`` to its non-transparent pixels plus ``padding_px`` on every side.

    An image without ink is returned as a 1×1 transparent image (never empty).
    """
    box = image.getchannel("A").getbbox()
    if box is None:
        return Image.new("RGBA", (1, 1), TRANSPARENT)
    left, top, right, bottom = box
    padded = Image.new("RGBA", (right - left + 2 * padding_px, bottom - top + 2 * padding_px), TRANSPARENT)
    padded.paste(image.crop(box), (padding_px, padding_px))
    return padded


def _stroke(em: float) -> int:
    """Line width for drawn shapes: about a bold glyph's stem (0.09 em), at least 2 px."""
    return max(2, round(em * 0.09))


def _new(width_em: float, height_em: float, em: float) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Transparent drawing surface of ``width_em × height_em``."""
    image = Image.new("RGBA", (max(1, math.ceil(width_em * em)), max(1, math.ceil(height_em * em))), TRANSPARENT)
    return image, ImageDraw.Draw(image)


def _arrow_head(draw: ImageDraw.ImageDraw, tip: tuple[float, float], direction: tuple[float, float], em: float, color: Color) -> None:
    """Filled triangular head at ``tip`` pointing along ``direction`` (unit vector)."""
    dx, dy = direction
    length, half = 0.42 * em, 0.24 * em
    base_x, base_y = tip[0] - dx * length, tip[1] - dy * length
    draw.polygon(
        [tip, (base_x - dy * half, base_y + dx * half), (base_x + dy * half, base_y - dx * half)],
        fill=color,
    )


def draw_strike(em: float, color: Color, _font_path: str) -> Image.Image:
    """Rising diagonal stroke (bottom left -> top right)."""
    image, draw = _new(3.2, 1.4, em)
    draw.line([(0.1 * em, 1.3 * em), (3.1 * em, 0.1 * em)], fill=color, width=_stroke(em))
    return image


def draw_wavy(em: float, color: Color, _font_path: str) -> Image.Image:
    """Horizontal sine wave, three periods over 4 em."""
    image, draw = _new(4.2, 1.0, em)
    steps = 96
    points = [
        (0.1 * em + 4.0 * em * i / steps, 0.5 * em + 0.18 * em * math.sin(2 * math.pi * 3 * i / steps))
        for i in range(steps + 1)
    ]
    draw.line(points, fill=color, width=_stroke(em), joint="curve")
    return image


def draw_arrow_straight(em: float, color: Color, _font_path: str) -> Image.Image:
    """Arrow pointing right."""
    image, draw = _new(2.8, 1.0, em)
    draw.line([(0.1 * em, 0.5 * em), (2.3 * em, 0.5 * em)], fill=color, width=_stroke(em))
    _arrow_head(draw, (2.65 * em, 0.5 * em), (1.0, 0.0), em, color)
    return image


def draw_arrow_curved(em: float, color: Color, _font_path: str) -> Image.Image:
    """Arc from the left over the top to the right, head pointing down (like ↷)."""
    image, draw = _new(2.8, 2.6, em)
    left, top, right, bottom = 0.2 * em, 0.3 * em, 2.4 * em, 2.5 * em
    draw.arc([left, top, right, bottom], start=180, end=355, fill=color, width=_stroke(em))
    center_y = (top + bottom) / 2.0
    _arrow_head(draw, (right - _stroke(em) / 2.0, center_y + 0.3 * em), (0.0, 1.0), em, color)
    return image


def draw_jargon(em: float, color: Color, _font_path: str) -> Image.Image:
    """Empty speech bubble, tail at the bottom left."""
    image, draw = _new(2.3, 1.9, em)
    width = _stroke(em)
    bottom = 1.3 * em
    draw.rounded_rectangle([0.1 * em, 0.1 * em, 2.2 * em, bottom], radius=0.35 * em, outline=color, width=width)
    draw.rectangle([0.5 * em, bottom - width, 0.9 * em, bottom + 1], fill=TRANSPARENT)
    draw.line([(0.5 * em, bottom - width / 2.0), (0.3 * em, 1.8 * em), (0.9 * em, bottom - width / 2.0)], fill=color, width=width, joint="curve")
    return image


def draw_example(em: float, color: Color, font_path: str) -> Image.Image:
    """"Bsp" over a bold "≠" over "Bew", stacked and centred."""
    image, draw = _new(1.8, 1.95, em)
    small = ImageFont.truetype(font_path, max(1, round(0.5 * em)))
    big = ImageFont.truetype(font_path, max(1, round(0.75 * em)))
    center_x = 0.9 * em
    draw.text((center_x, 0.35 * em), "Bsp", font=small, fill=color, anchor="mm")
    draw.text((center_x, 0.98 * em), "≠", font=big, fill=color, anchor="mm")
    draw.text((center_x, 1.6 * em), "Bew", font=small, fill=color, anchor="mm")
    return image


DRAWN_SHAPES: dict[str, Callable[[float, Color, str], Image.Image]] = {
    "strike": draw_strike,
    "wavy": draw_wavy,
    "arrow_straight": draw_arrow_straight,
    "arrow_curved": draw_arrow_curved,
    "jargon": draw_jargon,
    "example": draw_example,
}
