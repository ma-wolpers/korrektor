"""The single renderer for correction marks: canvas preview and PDF export use the same image.

Every mark (symbol or comment) becomes a transparent PNG whose centre is the mark's
anchor point ``PdfAnnotation.x/y``. The canvas shows it scaled to the zoom
(``px_per_pt`` = canvas pixels per PDF point), the export stamps it at
``EXPORT_PX_PER_PT`` (600 dpi) into the PDF. Because both come from the same pixels,
preview and PDF can no longer drift apart (the former FreeText export needed ten
per-rotation correction constants and still drifted by up to 24 pt).

Order of operations (the stored state is ``rotation_deg`` + ``mirrored``): the
unrotated image is mirrored horizontally first (if ``mirrored``), then rotated
counter-clockwise by ``rotation_deg`` (Pillow's ``rotate`` direction, same as Tk/PDF).

What is drawn:

* ``annotation_type == "symbol"``: a catalog symbol (``mark_symbols``) - a glyph in
  DejaVu Sans Bold or a drawn shape (``mark_shapes``); unknown content (e.g. the
  removed △) is drawn as plain glyph text, so no stored mark ever disappears.
* ``annotation_type == "text"``: the comment, set by matplotlib (DejaVu Sans Bold).
  Text between unescaped ``$…$`` is matplotlib mathtext (any number of formulas per
  comment, mixed with text; ``\\$`` is a literal dollar). An odd number of unescaped
  ``$`` or an invalid formula draws the comment as typed, ``$`` visible, so it is
  recognisable that nothing was set (``validate_mark_text`` explains why).

Caching (all keys are immutable values, never ids, so a changed text, colour, size,
rotation, mirroring or zoom always yields a new key and no stale image can appear):

1. ``_base_image(annotation_type, content, color_hex, font_size_pt)`` - the untransformed
   RGBA image at export resolution, ``lru_cache(256)``. Never mutated.
2. ``_transformed_png(<stage-1 key>, rotation_deg, mirrored, px_per_pt)`` - resized,
   mirrored, rotated, PNG-encoded, ``lru_cache(512)``; ``px_per_pt`` rounded to 0.01.
"""

from __future__ import annotations

import io
import math
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from PIL import Image, ImageColor, ImageDraw, ImageFont

from app.core.domain.annotation_sync import normalize_rotation_deg
from app.core.domain.mark_symbols import SYMBOL_BY_CONTENT
from app.infrastructure.rendering.mark_shapes import DRAWN_SHAPES, TRANSPARENT, crop_to_ink

EXPORT_DPI = 600
EXPORT_PX_PER_PT = EXPORT_DPI / 72.0
FONT_PATH = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans-Bold.ttf")
_FALLBACK_RGB = (214, 40, 40)
_UNESCAPED_DOLLAR = re.compile(r"(?<!\\)\$")


@dataclass(frozen=True)
class MarkStyle:
    """Everything that determines a mark's pixels (position is not part of it)."""

    annotation_type: str
    content: str
    color_hex: str
    font_size_pt: float
    rotation_deg: float = 0.0
    mirrored: bool = False

    @classmethod
    def of(cls, annotation: Any) -> "MarkStyle":
        """Style of a ``PdfAnnotation`` (rotation snapped to the 45° grid)."""
        return cls(
            annotation_type=str(annotation.annotation_type),
            content=str(annotation.content),
            color_hex=str(annotation.color_hex),
            font_size_pt=float(annotation.font_size),
            rotation_deg=normalize_rotation_deg(annotation.rotation_deg),
            mirrored=bool(getattr(annotation, "mirrored", False)),
        )


@dataclass(frozen=True)
class RenderedMark:
    """A rendered mark: PNG bytes and size; centre = anchor point."""

    png: bytes
    width_px: int
    height_px: int
    px_per_pt: float

    @property
    def width_pt(self) -> float:
        """Width in PDF points."""
        return self.width_px / self.px_per_pt

    @property
    def height_pt(self) -> float:
        """Height in PDF points."""
        return self.height_px / self.px_per_pt


def render_mark(style: MarkStyle, px_per_pt: float) -> RenderedMark:
    """Render ``style`` at ``px_per_pt`` pixels per PDF point (cached, see module docstring)."""
    scale = max(0.05, round(float(px_per_pt), 2))
    png, width, height = _transformed_png(
        style.annotation_type, style.content, style.color_hex, float(style.font_size_pt),
        normalize_rotation_deg(style.rotation_deg), bool(style.mirrored), scale,
    )
    return RenderedMark(png=png, width_px=width, height_px=height, px_per_pt=scale)


def render_mark_image(style: MarkStyle, px_per_pt: float) -> Image.Image:
    """``render_mark`` as a Pillow image (tests and diagnostics)."""
    return Image.open(io.BytesIO(render_mark(style, px_per_pt).png)).convert("RGBA")


def validate_mark_text(text: str) -> str | None:
    """Why ``text`` would be drawn literally instead of with formulas, or ``None`` if it is fine."""
    count = len(_UNESCAPED_DOLLAR.findall(text))
    if count % 2:
        return "Ungerade Anzahl $-Zeichen: Formeln stehen zwischen zwei $ (ein einzelnes $ als \\$ schreiben)."
    if count == 0:
        return None
    try:
        _render_text(text, (0, 0, 0, 255), 10.0, 1.0, parse_math=True)
    except Exception as exc:  # matplotlib raises ValueError subclasses for bad mathtext
        return f"Formel kann nicht gesetzt werden: {_mathtext_reason(exc)}"
    return None


def _mathtext_reason(exc: Exception) -> str:
    r"""The telling part of a mathtext error: its last line without parser class and position.

    matplotlib's message is three lines - the expression, a caret, and e.g.
    "ParseFatalException: Unknown symbol: \begin, found '\'  (at char 0), (line:1, col:1)";
    this returns "Unknown symbol: \begin, found '\'".
    """
    lines = [line.strip() for line in str(exc).splitlines() if line.strip()]
    if not lines:
        return type(exc).__name__
    reason = re.sub(r"^\w+(Exception|Error): ", "", lines[-1])
    return re.sub(r"\s*\(at char \d+\).*$", "", reason)


def clear_mark_caches() -> None:
    """Drop both cache stages (tests)."""
    _base_image.cache_clear()
    _transformed_png.cache_clear()


def mark_cache_sizes() -> tuple[int, int]:
    """Current entry counts of stage 1 and stage 2 (tests)."""
    return _base_image.cache_info().currsize, _transformed_png.cache_info().currsize


def _rgba(color_hex: str) -> tuple[int, int, int, int]:
    """``#rrggbb`` as opaque RGBA; an unreadable colour falls back to the default red."""
    try:
        red, green, blue = ImageColor.getrgb(color_hex)[:3]
    except ValueError:
        red, green, blue = _FALLBACK_RGB
    return red, green, blue, 255


@lru_cache(maxsize=64)
def _font(size_px: int) -> ImageFont.FreeTypeFont:
    """DejaVu Sans Bold at ``size_px`` (fonts are reused across marks)."""
    return ImageFont.truetype(FONT_PATH, max(1, size_px))


def _padding(em: float) -> int:
    """Transparent margin around the ink (keeps antialiased edges and rotation clean)."""
    return max(1, round(0.08 * em))


def _render_glyph(content: str, color: tuple[int, int, int, int], em: float) -> Image.Image:
    """``content`` as DejaVu Sans Bold text, cropped to its ink."""
    font = _font(round(em))
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    left, top, right, bottom = probe.textbbox((0, 0), content or " ", font=font)
    pad = _padding(em)
    image = Image.new("RGBA", (max(1, right - left + 2 * pad), max(1, bottom - top + 2 * pad)), TRANSPARENT)
    ImageDraw.Draw(image).text((pad - left, pad - top), content, font=font, fill=color)
    return crop_to_ink(image, pad)


def _render_text(content: str, color: tuple[int, int, int, int], size_pt: float, px_per_pt: float, *, parse_math: bool) -> Image.Image:
    """Comment text via matplotlib (``parse_math`` = mathtext between ``$``), cropped to its ink."""
    dpi = 72.0 * px_per_pt
    figure = Figure(dpi=dpi)
    FigureCanvasAgg(figure)
    with matplotlib.rc_context({"mathtext.fontset": "dejavusans", "text.usetex": False}):
        figure.text(
            0, 0, content, fontsize=size_pt, color=tuple(c / 255 for c in color), fontweight="bold",
            family="DejaVu Sans", parse_math=parse_math,
        )
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", dpi=dpi, transparent=True, bbox_inches="tight", pad_inches=0.05)
    return crop_to_ink(Image.open(buffer).convert("RGBA"), _padding(size_pt * px_per_pt))


def _text_image(content: str, color: tuple[int, int, int, int], size_pt: float) -> Image.Image:
    """A comment: formulas if the ``$`` are balanced and valid, else the literal text."""
    dollars = len(_UNESCAPED_DOLLAR.findall(content))
    if dollars and dollars % 2 == 0:
        try:
            return _render_text(content, color, size_pt, EXPORT_PX_PER_PT, parse_math=True)
        except Exception:
            pass
    literal = content if dollars else content.replace("\\$", "$")
    return _render_text(literal or " ", color, size_pt, EXPORT_PX_PER_PT, parse_math=False)


@lru_cache(maxsize=256)
def _base_image(annotation_type: str, content: str, color_hex: str, font_size_pt: float) -> Image.Image:
    """Stage 1: the untransformed mark at export resolution (never mutated by callers)."""
    color = _rgba(color_hex)
    em = max(1.0, font_size_pt * EXPORT_PX_PER_PT)
    if annotation_type == "text":
        return _text_image(content, color, font_size_pt)
    symbol = SYMBOL_BY_CONTENT.get(content)
    if symbol is not None and symbol.drawing == "drawn":
        return crop_to_ink(DRAWN_SHAPES[symbol.key](em, color, FONT_PATH), _padding(em))
    return _render_glyph(content, color, em)


@lru_cache(maxsize=512)
def _transformed_png(
    annotation_type: str, content: str, color_hex: str, font_size_pt: float,
    rotation_deg: float, mirrored: bool, px_per_pt: float,
) -> tuple[bytes, int, int]:
    """Stage 2: resize to ``px_per_pt``, mirror, then rotate; PNG bytes and size."""
    image = _base_image(annotation_type, content, color_hex, font_size_pt)
    factor = px_per_pt / EXPORT_PX_PER_PT
    if not math.isclose(factor, 1.0):
        size = (max(1, round(image.width * factor)), max(1, round(image.height * factor)))
        image = image.resize(size, Image.Resampling.LANCZOS)
    if mirrored:
        image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    image = rotate_ccw(image, rotation_deg)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", compress_level=3)
    return buffer.getvalue(), image.width, image.height


def rotate_ccw(image: Image.Image, rotation_deg: float) -> Image.Image:
    """Rotate counter-clockwise; multiples of 90° are exact transposes, others bicubic with expansion."""
    quarter = {90.0: Image.Transpose.ROTATE_90, 180.0: Image.Transpose.ROTATE_180, 270.0: Image.Transpose.ROTATE_270}
    if rotation_deg == 0.0:
        return image
    if rotation_deg in quarter:
        return image.transpose(quarter[rotation_deg])
    return image.rotate(rotation_deg, resample=Image.Resampling.BICUBIC, expand=True)
