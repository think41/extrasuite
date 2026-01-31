"""Bounding box calculations for slide elements.

Converts Google Slides API size/transform to bounding boxes in points.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from extraslide.units import emu_to_pt


@dataclass
class BoundingBox:
    """Bounding box in points."""

    x: float
    y: float
    w: float
    h: float

    @property
    def x2(self) -> float:
        """Right edge x coordinate."""
        return self.x + self.w

    @property
    def y2(self) -> float:
        """Bottom edge y coordinate."""
        return self.y + self.h

    @property
    def area(self) -> float:
        """Area in square points."""
        return self.w * self.h

    def contains(self, other: BoundingBox, threshold: float = 0.7) -> bool:
        """Check if this box contains most of another box.

        Args:
            other: The box to check for containment
            threshold: Minimum fraction of other's area that must be inside (0.0-1.0)

        Returns:
            True if at least `threshold` of other's area is inside this box
        """
        # Compute intersection
        ix1 = max(self.x, other.x)
        iy1 = max(self.y, other.y)
        ix2 = min(self.x2, other.x2)
        iy2 = min(self.y2, other.y2)

        if ix1 >= ix2 or iy1 >= iy2:
            return False  # No intersection

        intersection_area = (ix2 - ix1) * (iy2 - iy1)

        if other.area == 0:
            return False

        return intersection_area / other.area >= threshold

    def relative_to(self, parent: BoundingBox) -> BoundingBox:
        """Return this box's position relative to a parent box.

        Args:
            parent: The parent box to compute relative position from

        Returns:
            New BoundingBox with x, y relative to parent's origin
        """
        return BoundingBox(
            x=self.x - parent.x,
            y=self.y - parent.y,
            w=self.w,
            h=self.h,
        )

    def absolute_from(self, parent: BoundingBox) -> BoundingBox:
        """Convert relative position to absolute given parent's position.

        Args:
            parent: The parent box to compute absolute position from

        Returns:
            New BoundingBox with absolute x, y
        """
        return BoundingBox(
            x=parent.x + self.x,
            y=parent.y + self.y,
            w=self.w,
            h=self.h,
        )


@dataclass
class Transform:
    """Transform matrix components."""

    scale_x: float = 1.0
    scale_y: float = 1.0
    shear_x: float = 0.0
    shear_y: float = 0.0
    translate_x: float = 0.0  # in EMU
    translate_y: float = 0.0  # in EMU

    @classmethod
    def from_element(cls, element: dict[str, Any]) -> Transform:
        """Extract transform from element."""
        t = element.get("transform", {})
        return cls(
            scale_x=t.get("scaleX", 1),
            scale_y=t.get("scaleY", 1),
            shear_x=t.get("shearX", 0),
            shear_y=t.get("shearY", 0),
            translate_x=t.get("translateX", 0),
            translate_y=t.get("translateY", 0),
        )

    def compose(self, child: Transform) -> Transform:
        """Compose this transform with a child transform.

        Returns the combined transform: parent * child.
        For a point in the child's coordinate system, the combined
        transform gives the position in the root coordinate system.
        """
        # Matrix multiplication for 2D affine transforms:
        # [a c e]   [a' c' e']   [aa'+cb'  ac'+cd'  ae'+cf'+e]
        # [b d f] * [b' d' f'] = [ba'+db'  bc'+dd'  be'+df'+f]
        # [0 0 1]   [0  0  1 ]   [0        0        1        ]
        #
        # Where a=scaleX, b=shearY, c=shearX, d=scaleY, e=translateX, f=translateY
        return Transform(
            scale_x=self.scale_x * child.scale_x + self.shear_x * child.shear_y,
            scale_y=self.shear_y * child.shear_x + self.scale_y * child.scale_y,
            shear_x=self.scale_x * child.shear_x + self.shear_x * child.scale_y,
            shear_y=self.shear_y * child.scale_x + self.scale_y * child.shear_y,
            translate_x=(
                self.scale_x * child.translate_x
                + self.shear_x * child.translate_y
                + self.translate_x
            ),
            translate_y=(
                self.shear_y * child.translate_x
                + self.scale_y * child.translate_y
                + self.translate_y
            ),
        )

    @classmethod
    def identity(cls) -> Transform:
        """Return the identity transform."""
        return cls()


def get_bounds(
    element: dict[str, Any],
    parent_transform: Transform | None = None,
) -> BoundingBox:
    """Extract bounding box from a page element.

    Computes the visual bounding box by transforming all four corners of the
    element and finding the min/max extents. This correctly handles scaling,
    shearing, and negative transforms.

    If parent_transform is provided, composes it with the element's transform
    to get the absolute position on the slide.

    Args:
        element: A pageElement from the Google Slides API
        parent_transform: Optional parent transform to compose with

    Returns:
        BoundingBox with position and size in points
    """
    size = element.get("size", {})
    local_transform = Transform.from_element(element)

    # Compose with parent if provided
    if parent_transform:
        t = parent_transform.compose(local_transform)
    else:
        t = local_transform

    # Base size in EMU
    w_emu = size.get("width", {}).get("magnitude", 0)
    h_emu = size.get("height", {}).get("magnitude", 0)

    # Transform all four corners of the element
    # Local corners: (0,0), (w,0), (0,h), (w,h) in EMU
    # Transform formula: x' = scaleX*x + shearX*y + translateX
    #                    y' = shearY*x + scaleY*y + translateY
    corners_x = [
        t.translate_x,  # (0, 0)
        t.scale_x * w_emu + t.translate_x,  # (w, 0)
        t.shear_x * h_emu + t.translate_x,  # (0, h)
        t.scale_x * w_emu + t.shear_x * h_emu + t.translate_x,  # (w, h)
    ]
    corners_y = [
        t.translate_y,  # (0, 0)
        t.shear_y * w_emu + t.translate_y,  # (w, 0)
        t.scale_y * h_emu + t.translate_y,  # (0, h)
        t.shear_y * w_emu + t.scale_y * h_emu + t.translate_y,  # (w, h)
    ]

    # Find bounding box of transformed corners
    min_x = min(corners_x)
    max_x = max(corners_x)
    min_y = min(corners_y)
    max_y = max(corners_y)

    return BoundingBox(
        x=emu_to_pt(min_x),
        y=emu_to_pt(min_y),
        w=emu_to_pt(max_x - min_x),
        h=emu_to_pt(max_y - min_y),
    )


def get_group_bounds(children_bounds: list[BoundingBox]) -> BoundingBox:
    """Compute bounding box of a group from its children's bounds.

    Args:
        children_bounds: List of bounding boxes for group children

    Returns:
        BoundingBox that encompasses all children
    """
    if not children_bounds:
        return BoundingBox(x=0, y=0, w=0, h=0)

    min_x = min(b.x for b in children_bounds)
    min_y = min(b.y for b in children_bounds)
    max_x = max(b.x2 for b in children_bounds)
    max_y = max(b.y2 for b in children_bounds)

    return BoundingBox(
        x=min_x,
        y=min_y,
        w=max_x - min_x,
        h=max_y - min_y,
    )
