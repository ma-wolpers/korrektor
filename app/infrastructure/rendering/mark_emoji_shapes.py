"""Emoji symbols (smile, sad, shocked, heart) in a slim, hand-drawn style.

Drawn like the other shapes (``mark_shapes``): unrotated on a transparent RGBA canvas
sized in em, in the mark colour; the caller crops to the ink. The look is deliberately
"unperfect" - a head that is not an exact circle and whose stroke runs a little past
its start, slightly crooked mouths, eyes that are not twins, a heart outline whose tip
crosses over - but it is computed, not random: every export and every preview of the
same mark is identical.

All strokes use ``_slim_stroke`` (after the catalog scale about the speech bubble's stroke).
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw

Color = tuple[int, int, int, int]
_TRANSPARENT: Color = (0, 0, 0, 0)


def _slim_stroke(em: float) -> int:
    """Pen width of the emoji symbols: 0.095 em, at least 2 px.

    With the catalog scale of the emojis (~0.8) this is about the speech bubble's stroke -
    slim, but not hairline-thin.
    """
    return max(2, round(em * 0.095))


def _canvas(width_em: float, height_em: float, em: float) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Transparent drawing surface of ``width_em × height_em``."""
    image = Image.new("RGBA", (max(1, math.ceil(width_em * em)), max(1, math.ceil(height_em * em))), _TRANSPARENT)
    return image, ImageDraw.Draw(image)


def _hand_loop(cx: float, cy: float, rx: float, ry: float, *, start_deg: float, sweep_deg: float) -> list[tuple[float, float]]:
    """Points of a hand-drawn oval: radius wobbles a little, the stroke overshoots its start.

    ``sweep_deg`` > 360 makes the end run past the beginning (as a pen does); the
    radius grows by 4 % along the way, so the two ends do not lie on top of each other.
    """
    points = []
    steps = 120
    for step in range(steps + 1):
        fraction = step / steps
        angle = math.radians(start_deg + sweep_deg * fraction)
        wobble = 1.0 + 0.025 * math.sin(3 * angle + 0.7) + 0.018 * math.sin(5 * angle + 2.1) + 0.04 * fraction
        points.append((cx + rx * wobble * math.cos(angle), cy + ry * wobble * math.sin(angle)))
    return points


def _curve(start: tuple[float, float], control: tuple[float, float], end: tuple[float, float]) -> list[tuple[float, float]]:
    """Quadratic Bézier from ``start`` to ``end`` bent towards ``control`` (mouths)."""
    points = []
    for step in range(25):
        t = step / 24
        x = (1 - t) ** 2 * start[0] + 2 * (1 - t) * t * control[0] + t**2 * end[0]
        y = (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * control[1] + t**2 * end[1]
        points.append((x, y))
    return points


def _face(em: float, color: Color, mouth: str) -> Image.Image:
    """Hand-drawn head (slightly taller than wide), two round, slightly uneven eyes and a ``mouth``."""
    image, draw = _canvas(0.9, 1.0, em)
    width = _slim_stroke(em)
    head = _hand_loop(0.45 * em, 0.5 * em, 0.36 * em, 0.42 * em, start_deg=-100, sweep_deg=385)
    draw.line(head, fill=color, width=width, joint="curve")
    grow = 1.3 if mouth == "shocked" else 1.0
    # Round, slightly uneven eyes (filled ovals; line ends would look square).
    for eye_x, eye_y, half_w, half_h in ((0.33, 0.41, 0.042, 0.06), (0.57, 0.4, 0.038, 0.056)):
        cx, cy, rx, ry = eye_x * em, eye_y * em, half_w * em * grow, half_h * em * grow
        draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=color)
    if mouth == "smile":
        draw.line(_curve((0.27 * em, 0.6 * em), (0.44 * em, 0.8 * em), (0.64 * em, 0.57 * em)), fill=color, width=width, joint="curve")
    elif mouth == "sad":
        draw.line(_curve((0.29 * em, 0.75 * em), (0.45 * em, 0.58 * em), (0.62 * em, 0.73 * em)), fill=color, width=width, joint="curve")
    else:
        mouth_loop = _hand_loop(0.46 * em, 0.68 * em, 0.07 * em, 0.09 * em, start_deg=-80, sweep_deg=375)
        draw.line(mouth_loop, fill=color, width=width, joint="curve")
    return image


def draw_smile(em: float, color: Color, _font_path: str) -> Image.Image:
    """Smiling face."""
    return _face(em, color, "smile")


def draw_sad(em: float, color: Color, _font_path: str) -> Image.Image:
    """Sad face."""
    return _face(em, color, "sad")


def draw_shocked(em: float, color: Color, _font_path: str) -> Image.Image:
    """Shocked face: bigger eyes, small open mouth."""
    return _face(em, color, "shocked")


def draw_heart(em: float, color: Color, _font_path: str) -> Image.Image:
    """Slim heart outline, drawn in one go like by hand.

    Narrower than the textbook heart curve and a bit taller than wide; the left lobe
    is a little fuller than the right, the whole heart leans slightly, and the pen
    drifts while drawing, so start and end cross visibly at the tip instead of
    meeting exactly.
    """
    image, draw = _canvas(0.85, 1.0, em)
    points = []
    steps = 160
    for step in range(steps + 1):
        fraction = step / steps
        t = math.pi - 0.18 + (2 * math.pi + 0.36) * fraction
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        x *= 1.07 if x < 0 else 0.95  # fuller left lobe
        wobble = 1.0 + 0.025 * math.sin(4 * t + 1.3) + 0.015 * math.sin(7 * t + 0.4)
        px = 0.42 + wobble * x / 57.0 + 0.012 * y / 13.0 + 0.05 * fraction  # lean + drift
        py = 0.44 - wobble * y / 36.0 - 0.03 * fraction
        points.append((px * em, py * em))
    draw.line(points, fill=color, width=_slim_stroke(em), joint="curve")
    return image


EMOJI_SHAPES = {
    "smile": draw_smile,
    "sad": draw_sad,
    "shocked": draw_shocked,
    "heart": draw_heart,
}
