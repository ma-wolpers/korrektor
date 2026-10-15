"""Orientation algebra of a correction mark: rotation on the 45° grid plus a mirror flag.

A mark stores only ``rotation_deg`` (θ, counter-clockwise, 45° grid, [0, 360)) and
``mirrored`` (m). Its drawing is defined as **mirror horizontally first (if m), then
rotate by θ**, i.e. the transform ``R(θ) · H^m`` (H = horizontal mirror, flipping
x). The two mirror buttons work in screen terms on whatever is currently shown and
are translated back into this normal form:

* horizontal mirror H:   H · R(θ) · H^m = R(−θ) · H^(m+1)        -> (−θ, not m)
* vertical mirror V:     V = R(180°) · H, so V · R(θ) · H^m = R(180° − θ) · H^(m+1)
                                                                -> (180° − θ, not m)

(H · R(θ) = R(−θ) · H holds because mirroring reverses the rotation direction;
H² = identity, so mirroring twice restores the original.)

Example from the wish list: a mark rotated 45° to the left (θ = 45°, m = False),
mirrored vertically -> m = True, θ = 135°: "mirror horizontally, then rotate 135°
to the left" shows exactly the vertically mirrored mark.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.domain.annotation_sync import normalize_rotation_deg


@dataclass(frozen=True)
class Orientation:
    """Stored orientation of a mark: ``rotation_deg`` (45° grid) and ``mirrored``."""

    rotation_deg: float
    mirrored: bool

    @classmethod
    def of(cls, rotation_deg: float, mirrored: bool) -> "Orientation":
        """Normalized orientation (rotation snapped to the 45° grid, wrapped into [0, 360))."""
        return cls(normalize_rotation_deg(rotation_deg), bool(mirrored))


def rotated(orientation: Orientation, delta_deg: float) -> Orientation:
    """Rotate the shown mark by ``delta_deg`` (positive = counter-clockwise); the mirror flag stays."""
    return Orientation.of(orientation.rotation_deg + delta_deg, orientation.mirrored)


def flipped_horizontally(orientation: Orientation) -> Orientation:
    """Mirror the shown mark left/right: ``(θ, m) -> (−θ, not m)``."""
    return Orientation.of(-orientation.rotation_deg, not orientation.mirrored)


def flipped_vertically(orientation: Orientation) -> Orientation:
    """Mirror the shown mark top/bottom: ``(θ, m) -> (180° − θ, not m)``."""
    return Orientation.of(180.0 - orientation.rotation_deg, not orientation.mirrored)
