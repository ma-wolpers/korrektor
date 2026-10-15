"""Drawn correction symbols (``MarkSymbol.drawing == "drawn"``) as Pillow images.

Every shape is drawn unrotated and unmirrored on a transparent RGBA canvas sized in
"em" (1 em = the mark's font size in pixels) and then cropped to its ink plus a small
padding. The image centre is therefore the centre of the visible shape, which is
where ``PdfAnnotation.x/y`` points - for the drawn shapes exactly as for glyphs and
texts (see ``mark_renderer``). Rotation and mirroring are applied afterwards by the
renderer, never here.

Shapes (unrotated), with their size in em:

* ``strike``         - rising diagonal stroke, 2 × 0.75, like a line crossing out a word
* ``wavy``           - horizontal sine wave, 2.4 wide, three periods (underline for form errors)
* ``arrow_straight`` - arrow pointing right, 1.4 long
* ``arrow_curved``   - half-circle arc from left over the top, head pointing down at the right end
* ``jargon``         - empty speech bubble with its tail at the bottom left
* ``example``        - "Bsp" over a bold "≠" over "Bew" (example is no proof)

* ``smile``/``sad``/``shocked``/``heart`` - emojis in a slim hand-drawn style
  (``mark_emoji_shapes.py``)

Compact shapes are about as tall as a glyph (~0.7 em, like ✗); strike, wave and the
straight arrow are longer by nature - their length follows A+/A−.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from PIL import Image, ImageDraw, ImageFont

from app.infrastructure.rendering.mark_emoji_shapes import EMOJI_SHAPES

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
    """Rising diagonal stroke (bottom left -> top right), 2 × 0.75 em."""
    image, draw = _new(2.2, 0.95, em)
    draw.line([(0.1 * em, 0.85 * em), (2.1 * em, 0.1 * em)], fill=color, width=_stroke(em))
    return image


def draw_wavy(em: float, color: Color, _font_path: str) -> Image.Image:
    """Horizontal sine wave, three periods over 2.4 em."""
    image, draw = _new(2.6, 0.6, em)
    steps = 96
    points = [
        (0.1 * em + 2.4 * em * i / steps, 0.3 * em + 0.12 * em * math.sin(2 * math.pi * 3 * i / steps))
        for i in range(steps + 1)
    ]
    draw.line(points, fill=color, width=_stroke(em), joint="curve")
    return image


def draw_arrow_straight(em: float, color: Color, _font_path: str) -> Image.Image:
    """Arrow pointing right, 1.4 em long."""
    image, draw = _new(1.6, 0.7, em)
    draw.line([(0.1 * em, 0.35 * em), (1.15 * em, 0.35 * em)], fill=color, width=_stroke(em))
    _arrow_head(draw, (1.5 * em, 0.35 * em), (1.0, 0.0), em, color)
    return image


def draw_arrow_curved(em: float, color: Color, _font_path: str) -> Image.Image:
    """Arc from the left over the top to the right, head pointing down (like ↷), ~1.1 × 0.75 em."""
    image, draw = _new(1.4, 1.3, em)
    left, top, right, bottom = 0.1 * em, 0.1 * em, 1.2 * em, 1.2 * em
    draw.arc([left, top, right, bottom], start=180, end=355, fill=color, width=_stroke(em))
    center_y = (top + bottom) / 2.0
    _arrow_head(draw, (right - _stroke(em) / 2.0, center_y + 0.3 * em), (0.0, 1.0), em, color)
    return image


def draw_jargon(em: float, color: Color, _font_path: str) -> Image.Image:
    """Empty speech bubble, tail at the bottom left, ~1.1 × 0.75 em."""
    image, draw = _new(1.3, 0.95, em)
    width = _stroke(em)
    bottom = 0.62 * em
    draw.rounded_rectangle([0.05 * em, 0.05 * em, 1.2 * em, bottom], radius=0.18 * em, outline=color, width=width)
    draw.rectangle([0.28 * em, bottom - width, 0.55 * em, bottom + 1], fill=TRANSPARENT)
    draw.line([(0.28 * em, bottom - width / 2.0), (0.18 * em, 0.88 * em), (0.55 * em, bottom - width / 2.0)],
              fill=color, width=width, joint="curve")
    return image


def draw_example(em: float, color: Color, font_path: str) -> Image.Image:
    """"Bsp" over a bold "≠" over "Bew", stacked tightly and centred, ~0.8 em tall."""
    image, draw = _new(1.2, 1.0, em)
    small = ImageFont.truetype(font_path, max(1, round(0.34 * em)))
    big = ImageFont.truetype(font_path, max(1, round(0.48 * em)))
    center_x = 0.6 * em
    draw.text((center_x, 0.2 * em), "Bsp", font=small, fill=color, anchor="mm")
    draw.text((center_x, 0.47 * em), "≠", font=big, fill=color, anchor="mm")
    draw.text((center_x, 0.74 * em), "Bew", font=small, fill=color, anchor="mm")
    return image


COMBO_GAP_EM = 0.07
COMBO_COMPANIONS = frozenset("()[]∅")


def _ink_on_baseline(char: str, font: ImageFont.FreeTypeFont, color: Color) -> tuple[Image.Image, int]:
    """``char`` cropped to its real ink, plus the ink top's offset from the baseline (negative = above).

    ``font.getbbox`` includes the glyph's side bearings, so it cannot give the ink;
    the alpha channel of the rendered glyph does.
    """
    size = font.size
    canvas = Image.new("RGBA", (size * 3, size * 3), TRANSPARENT)
    baseline = size * 2
    ImageDraw.Draw(canvas).text((size, baseline), char, font=font, fill=color, anchor="ls")
    box = canvas.getchannel("A").getbbox() or (0, 0, 1, 1)
    return canvas.crop(box), box[1] - baseline


def draw_combo(
    text: str, em: float, color: Color, font_for: Callable[[str], str], char_scale: dict[str, float],
    gap_em: float = COMBO_GAP_EM,
) -> Image.Image:
    """Characters of ``text`` set tightly: ink to ink with a small fixed gap, on one baseline.

    Used for combined symbols such as "✓∅" and "(✓)": set as plain text, the font's
    side bearings leave wide gaps. ``char_scale`` enlarges single characters the same
    way the catalog does for them alone (its ``scale``), so a ✓ inside a combo
    matches the stand-alone ✓. ``font_for(char)`` picks each character's font (letters
    and symbol glyphs come from different fonts, ``mark_fonts.font_for_char``). ``gap_em`` is the space between the inks (negative =
    slight overlap, e.g. the ✓'s tail reaching into the ∅). Ordinary characters sit on
    the font baseline; companion characters (``COMBO_COMPANIONS``: brackets, ∅) are
    centred vertically on the other characters' ink, so the reduced parentheses of "(✓)"
    enclose the check symmetrically and the reduced ∅ of "✓∅" sits beside its middle.
    """
    pieces = [
        _ink_on_baseline(char, ImageFont.truetype(font_for(char), max(1, round(em * char_scale.get(char, 1.0)))), color)
        for char in text
    ]
    gap = round(gap_em * em)
    content = [(ink, offset) for char, (ink, offset) in zip(text, pieces) if char not in COMBO_COMPANIONS] or pieces
    middle = (min(offset for _i, offset in content) + max(offset + ink.height for ink, offset in content)) / 2.0
    tops = [
        round(middle - ink.height / 2.0) if char in COMBO_COMPANIONS else offset
        for char, (ink, offset) in zip(text, pieces)
    ]
    top = min(tops)
    bottom = max(item_top + ink.height for item_top, (ink, _offset) in zip(tops, pieces))
    width = sum(ink.width for ink, _offset in pieces) + gap * (len(pieces) - 1)
    width = max(width, max(ink.width for ink, _offset in pieces))
    image = Image.new("RGBA", (max(1, width), max(1, bottom - top)), TRANSPARENT)
    x = 0
    for item_top, (ink, _offset) in zip(tops, pieces):
        image.paste(ink, (x, item_top - top), ink)
        x += ink.width + gap
    return image


DRAWN_SHAPES: dict[str, Callable[[float, Color, str], Image.Image]] = {
    "strike": draw_strike,
    "wavy": draw_wavy,
    "arrow_straight": draw_arrow_straight,
    "arrow_curved": draw_arrow_curved,
    "jargon": draw_jargon,
    "example": draw_example,
    **EMOJI_SHAPES,
}
