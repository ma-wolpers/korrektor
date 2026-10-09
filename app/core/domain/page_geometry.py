"""Pure page geometry of the Scan-Werkstatt: rotation around the page center (no PDF library).

Coordinates are PDF points of the *visible* page, origin top-left, y down -
the convention of `PdfAnnotation.x/y` and the extra-page boxes. Rotation
angles are degrees, **positive = clockwise** (Strg+→). One source of truth
for both the page content (`infrastructure/pdf/page_editing.py`) and the
re-mapping of marks, so preview, written PDF and moved marks always agree.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def normalize_rotation(degrees: float) -> float:
    """Map any angle to (-180, 180]."""
    value = math.fmod(float(degrees), 360.0)
    if value <= -180.0:
        value += 360.0
    elif value > 180.0:
        value -= 360.0
    return 0.0 if abs(value) < 1e-9 else value


def quarter_turns(degrees: float) -> int:
    """Number of clockwise quarter turns contained in ``degrees`` (nearest multiple of 90°)."""
    return int(round(normalize_rotation(degrees) / 90.0)) % 4


@dataclass(frozen=True)
class PageTransform:
    """How one source page maps onto its edited page.

    The edited page keeps the source size (width/height swapped after an odd
    number of quarter turns); the content is rotated clockwise by
    ``rotation_deg`` around the page center at scale 1:1 and then shifted by
    ``offset_x``/``offset_y`` points (in coordinates of the edited page,
    positive = right/down). Content pushed over the edge is clipped,
    uncovered areas stay white.
    """

    source_width: float
    source_height: float
    rotation_deg: float
    offset_x: float = 0.0
    offset_y: float = 0.0

    @property
    def target_size(self) -> tuple[float, float]:
        """Width and height of the edited page."""
        if quarter_turns(self.rotation_deg) % 2:
            return self.source_height, self.source_width
        return self.source_width, self.source_height

    def map_point(self, x: float, y: float) -> tuple[float, float]:
        """Map a point of the source page to the edited page (center rotation clockwise positive, then the shift)."""
        rad = math.radians(self.rotation_deg)
        dx, dy = x - self.source_width / 2, y - self.source_height / 2
        target_width, target_height = self.target_size
        return (
            target_width / 2 + dx * math.cos(rad) - dy * math.sin(rad) + self.offset_x,
            target_height / 2 + dx * math.sin(rad) + dy * math.cos(rad) + self.offset_y,
        )

    def bounding_box_of_rotated_source(self) -> tuple[float, float, float, float]:
        """Rectangle (on the edited page) the rotated source page occupies - centered, then shifted; used for drawing."""
        rad = math.radians(self.rotation_deg)
        width = self.source_width * abs(math.cos(rad)) + self.source_height * abs(math.sin(rad))
        height = self.source_width * abs(math.sin(rad)) + self.source_height * abs(math.cos(rad))
        target_width, target_height = self.target_size
        return (
            target_width / 2 - width / 2 + self.offset_x,
            target_height / 2 - height / 2 + self.offset_y,
            target_width / 2 + width / 2 + self.offset_x,
            target_height / 2 + height / 2 + self.offset_y,
        )
