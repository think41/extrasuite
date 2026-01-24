"""Tailwind-style class system for SML.

This module provides bidirectional conversion between:
- Google Slides API properties (JSON)
- SML Tailwind-style classes (strings)

Class naming follows the pattern: {property}-{subproperty}-{value}[/{modifier}]
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from extraslide.units import emu_to_pt, format_pt, hex_to_rgb, rgb_to_hex


class PropertyState(Enum):
    """Property state values from Google Slides API."""

    RENDERED = "RENDERED"
    NOT_RENDERED = "NOT_RENDERED"
    INHERIT = "INHERIT"


class ThemeColorType(Enum):
    """Theme color types from Google Slides API."""

    DARK1 = "DARK1"
    LIGHT1 = "LIGHT1"
    DARK2 = "DARK2"
    LIGHT2 = "LIGHT2"
    ACCENT1 = "ACCENT1"
    ACCENT2 = "ACCENT2"
    ACCENT3 = "ACCENT3"
    ACCENT4 = "ACCENT4"
    ACCENT5 = "ACCENT5"
    ACCENT6 = "ACCENT6"
    TEXT1 = "TEXT1"
    TEXT2 = "TEXT2"
    BACKGROUND1 = "BACKGROUND1"
    BACKGROUND2 = "BACKGROUND2"
    HYPERLINK = "HYPERLINK"
    FOLLOWED_HYPERLINK = "FOLLOWED_HYPERLINK"


class DashStyle(Enum):
    """Dash styles for outlines/strokes."""

    SOLID = "SOLID"
    DOT = "DOT"
    DASH = "DASH"
    DASH_DOT = "DASH_DOT"
    LONG_DASH = "LONG_DASH"
    LONG_DASH_DOT = "LONG_DASH_DOT"


class ContentAlignment(Enum):
    """Vertical content alignment."""

    TOP = "TOP"
    MIDDLE = "MIDDLE"
    BOTTOM = "BOTTOM"


class TextAlignment(Enum):
    """Horizontal text alignment."""

    START = "START"
    CENTER = "CENTER"
    END = "END"
    JUSTIFIED = "JUSTIFIED"


class AutofitType(Enum):
    """Autofit types for text."""

    NONE = "NONE"
    TEXT_AUTOFIT = "TEXT_AUTOFIT"
    SHAPE_AUTOFIT = "SHAPE_AUTOFIT"


class ArrowStyle(Enum):
    """Arrow styles for lines."""

    NONE = "NONE"
    FILL_ARROW = "FILL_ARROW"
    STEALTH_ARROW = "STEALTH_ARROW"
    OPEN_ARROW = "OPEN_ARROW"
    FILL_CIRCLE = "FILL_CIRCLE"
    OPEN_CIRCLE = "OPEN_CIRCLE"
    FILL_SQUARE = "FILL_SQUARE"
    OPEN_SQUARE = "OPEN_SQUARE"
    FILL_DIAMOND = "FILL_DIAMOND"
    OPEN_DIAMOND = "OPEN_DIAMOND"


class LineCategory(Enum):
    """Line categories."""

    STRAIGHT = "STRAIGHT"
    BENT = "BENT"
    CURVED = "CURVED"


@dataclass
class Color:
    """Represents a color with optional alpha/opacity."""

    hex: str | None = None  # "#rrggbb"
    theme: str | None = None  # Theme color name
    alpha: float = 1.0  # 0.0 to 1.0

    @classmethod
    def from_api(cls, color_obj: dict[str, Any] | None) -> Color | None:
        """Create Color from API color object.

        Handles both rgbColor and themeColor.
        """
        if not color_obj:
            return None

        # Check for themeColor first
        if "themeColor" in color_obj:
            return cls(theme=color_obj["themeColor"].lower().replace("_", "-"))

        # Handle rgbColor
        rgb = color_obj.get("rgbColor", {})
        if not rgb:
            # Empty RGB means black
            return cls(hex="#000000")

        hex_color = rgb_to_hex(
            rgb.get("red", 0), rgb.get("green", 0), rgb.get("blue", 0)
        )
        return cls(hex=hex_color)

    def to_api(self) -> dict[str, Any]:
        """Convert to API color format."""
        if self.theme:
            return {"themeColor": self.theme.upper().replace("-", "_")}

        if self.hex:
            r, g, b = hex_to_rgb(self.hex)
            return {"rgbColor": {"red": r, "green": g, "blue": b}}

        return {"rgbColor": {}}


@dataclass
class Fill:
    """Fill styling (solid color, gradient, or state)."""

    color: Color | None = None
    state: PropertyState | None = None

    @classmethod
    def from_api(cls, fill_obj: dict[str, Any] | None) -> Fill | None:
        """Create Fill from API fill object."""
        if not fill_obj:
            return None

        # Check property state
        if "propertyState" in fill_obj:
            state_str = fill_obj["propertyState"]
            if state_str == "NOT_RENDERED":
                return cls(state=PropertyState.NOT_RENDERED)
            elif state_str == "INHERIT":
                return cls(state=PropertyState.INHERIT)

        # Handle solidFill
        solid = fill_obj.get("solidFill")
        if solid:
            color_obj = solid.get("color")
            color = Color.from_api(color_obj)
            alpha = solid.get("alpha", 1.0)
            if color:
                color.alpha = alpha
            return cls(color=color)

        return None

    def to_class(self, prefix: str = "fill") -> str:
        """Convert to SML class string."""
        if self.state == PropertyState.NOT_RENDERED:
            return f"{prefix}-none"
        if self.state == PropertyState.INHERIT:
            return ""

        if self.color:
            if self.color.theme:
                base = f"{prefix}-theme-{self.color.theme}"
            elif self.color.hex:
                base = f"{prefix}-{self.color.hex}"
            else:
                return ""

            # Add alpha/opacity if not 100%
            if self.color.alpha < 1.0:
                opacity = round(self.color.alpha * 100)
                return f"{base}/{opacity}"
            return base

        return ""


@dataclass
class Stroke:
    """Stroke/outline styling."""

    color: Color | None = None
    weight_pt: float | None = None
    dash_style: DashStyle | None = None
    state: PropertyState | None = None

    @classmethod
    def from_api(cls, outline_obj: dict[str, Any] | None) -> Stroke | None:
        """Create Stroke from API outline object."""
        if not outline_obj:
            return None

        # Check property state
        if "propertyState" in outline_obj:
            state_str = outline_obj["propertyState"]
            if state_str == "NOT_RENDERED":
                return cls(state=PropertyState.NOT_RENDERED)
            elif state_str == "INHERIT":
                return cls(state=PropertyState.INHERIT)

        stroke = cls()

        # Get fill color
        fill = outline_obj.get("outlineFill", {}).get("solidFill")
        if fill:
            color_obj = fill.get("color")
            stroke.color = Color.from_api(color_obj)
            if stroke.color:
                stroke.color.alpha = fill.get("alpha", 1.0)

        # Get weight
        weight = outline_obj.get("weight")
        if weight and weight.get("magnitude"):
            emu = weight["magnitude"]
            stroke.weight_pt = emu_to_pt(emu)

        # Get dash style
        dash = outline_obj.get("dashStyle")
        if dash:
            with contextlib.suppress(ValueError):
                stroke.dash_style = DashStyle(dash)

        return stroke

    def to_classes(self) -> list[str]:
        """Convert to list of SML class strings."""
        classes = []

        if self.state == PropertyState.NOT_RENDERED:
            return ["stroke-none"]
        if self.state == PropertyState.INHERIT:
            return []

        if self.color:
            if self.color.theme:
                base = f"stroke-theme-{self.color.theme}"
            elif self.color.hex:
                base = f"stroke-{self.color.hex}"
            else:
                base = ""

            if base:
                if self.color.alpha < 1.0:
                    opacity = round(self.color.alpha * 100)
                    classes.append(f"{base}/{opacity}")
                else:
                    classes.append(base)

        if self.weight_pt is not None:
            classes.append(f"stroke-w-{format_pt(self.weight_pt)}")

        if self.dash_style and self.dash_style != DashStyle.SOLID:
            dash_map = {
                DashStyle.DOT: "stroke-dot",
                DashStyle.DASH: "stroke-dash",
                DashStyle.DASH_DOT: "stroke-dash-dot",
                DashStyle.LONG_DASH: "stroke-long-dash",
                DashStyle.LONG_DASH_DOT: "stroke-long-dash-dot",
            }
            if self.dash_style in dash_map:
                classes.append(dash_map[self.dash_style])

        return classes


@dataclass
class Shadow:
    """Shadow styling."""

    color: Color | None = None
    blur_pt: float | None = None
    alignment: str | None = None
    alpha: float = 1.0
    state: PropertyState | None = None

    @classmethod
    def from_api(cls, shadow_obj: dict[str, Any] | None) -> Shadow | None:
        """Create Shadow from API shadow object."""
        if not shadow_obj:
            return None

        # Check property state
        if "propertyState" in shadow_obj:
            state_str = shadow_obj["propertyState"]
            if state_str == "NOT_RENDERED":
                return cls(state=PropertyState.NOT_RENDERED)
            elif state_str == "INHERIT":
                return cls(state=PropertyState.INHERIT)

        shadow = cls()
        shadow.alpha = shadow_obj.get("alpha", 1.0)

        # Get color
        color_obj = shadow_obj.get("color")
        if color_obj:
            shadow.color = Color.from_api({"rgbColor": color_obj.get("rgbColor", {})})

        # Get blur
        blur = shadow_obj.get("blurRadius")
        if blur and blur.get("magnitude"):
            shadow.blur_pt = emu_to_pt(blur["magnitude"])

        # Get alignment
        shadow.alignment = shadow_obj.get("alignment")

        return shadow

    def to_classes(self) -> list[str]:
        """Convert to list of SML class strings."""
        if self.state == PropertyState.NOT_RENDERED:
            return ["shadow-none"]
        if self.state == PropertyState.INHERIT:
            return []

        classes = []

        # If we have actual shadow properties, output them
        if self.blur_pt is not None:
            if self.blur_pt <= 2:
                classes.append("shadow-sm")
            elif self.blur_pt <= 4:
                classes.append("shadow")
            elif self.blur_pt <= 8:
                classes.append("shadow-md")
            elif self.blur_pt <= 16:
                classes.append("shadow-lg")
            else:
                classes.append("shadow-xl")

            # Add specific blur if non-standard
            if self.blur_pt not in [2, 4, 8, 16, 24]:
                classes.append(f"shadow-blur-{format_pt(self.blur_pt)}")

        # Add alignment
        alignment_map = {
            "TOP_LEFT": "shadow-tl",
            "TOP_CENTER": "shadow-tc",
            "TOP_RIGHT": "shadow-tr",
            "CENTER_LEFT": "shadow-cl",
            "CENTER": "shadow-c",
            "CENTER_RIGHT": "shadow-cr",
            "BOTTOM_LEFT": "shadow-bl",
            "BOTTOM_CENTER": "shadow-bc",
            "BOTTOM_RIGHT": "shadow-br",
        }
        if self.alignment and self.alignment in alignment_map:
            classes.append(alignment_map[self.alignment])

        return classes


@dataclass
class Transform:
    """Element transform (position, rotation, scale, shear)."""

    translate_x_pt: float = 0
    translate_y_pt: float = 0
    scale_x: float = 1.0
    scale_y: float = 1.0
    shear_x: float = 0
    shear_y: float = 0
    # Derived values
    width_pt: float | None = None
    height_pt: float | None = None

    @classmethod
    def from_api(
        cls,
        transform_obj: dict[str, Any] | None,
        size_obj: dict[str, Any] | None = None,
    ) -> Transform:
        """Create Transform from API transform and size objects."""
        t = cls()

        if transform_obj:
            # Get translation (position)
            t.translate_x_pt = emu_to_pt(transform_obj.get("translateX", 0))
            t.translate_y_pt = emu_to_pt(transform_obj.get("translateY", 0))

            # Get scale
            t.scale_x = transform_obj.get("scaleX", 1.0)
            t.scale_y = transform_obj.get("scaleY", 1.0)

            # Get shear
            t.shear_x = transform_obj.get("shearX", 0)
            t.shear_y = transform_obj.get("shearY", 0)

        # Calculate actual dimensions from size and scale
        if size_obj:
            base_width = emu_to_pt(size_obj.get("width", {}).get("magnitude", 0))
            base_height = emu_to_pt(size_obj.get("height", {}).get("magnitude", 0))
            t.width_pt = abs(base_width * t.scale_x)
            t.height_pt = abs(base_height * t.scale_y)

        return t

    def to_classes(self) -> list[str]:
        """Convert to list of SML class strings."""
        classes = []

        # Position
        classes.append(f"x-{format_pt(self.translate_x_pt)}")
        classes.append(f"y-{format_pt(self.translate_y_pt)}")

        # Size (if known)
        if self.width_pt is not None:
            classes.append(f"w-{format_pt(self.width_pt)}")
        if self.height_pt is not None:
            classes.append(f"h-{format_pt(self.height_pt)}")

        # Rotation - derived from scale/shear if rotated
        # For now, handle simple case of negative scale (flip)
        if self.scale_x < 0:
            classes.append("-scale-x-100")
        if self.scale_y < 0:
            classes.append("-scale-y-100")

        # TODO: Extract rotation angle from transform matrix if needed

        return classes


@dataclass
class TextStyle:
    """Text run styling."""

    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    strikethrough: bool | None = None
    small_caps: bool | None = None
    font_family: str | None = None
    font_size_pt: float | None = None
    font_weight: int | None = None
    foreground_color: Color | None = None
    background_color: Color | None = None
    link: str | None = None
    baseline_offset: str | None = None  # SUPERSCRIPT, SUBSCRIPT, NONE

    @classmethod
    def from_api(cls, style_obj: dict[str, Any] | None) -> TextStyle | None:
        """Create TextStyle from API style object."""
        if not style_obj:
            return None

        ts = cls()

        # Boolean styles
        ts.bold = style_obj.get("bold")
        ts.italic = style_obj.get("italic")
        ts.underline = style_obj.get("underline")
        ts.strikethrough = style_obj.get("strikethrough")
        ts.small_caps = style_obj.get("smallCaps")

        # Font
        ts.font_family = style_obj.get("fontFamily")

        # Font size
        font_size = style_obj.get("fontSize")
        if font_size and font_size.get("magnitude"):
            ts.font_size_pt = font_size["magnitude"]

        # Font weight
        weighted = style_obj.get("weightedFontFamily")
        if weighted:
            ts.font_weight = weighted.get("weight")

        # Foreground color
        fg = style_obj.get("foregroundColor", {}).get("opaqueColor")
        if fg:
            ts.foreground_color = Color.from_api(fg)

        # Background color
        bg = style_obj.get("backgroundColor", {}).get("opaqueColor")
        if bg:
            ts.background_color = Color.from_api(bg)

        # Link
        link = style_obj.get("link")
        if link:
            ts.link = (
                link.get("url") or link.get("slideIndex") or link.get("pageObjectId")
            )

        # Baseline offset
        ts.baseline_offset = style_obj.get("baselineOffset")

        return ts

    def to_classes(self) -> list[str]:
        """Convert to list of SML class strings."""
        classes = []

        # Boolean decorations
        if self.bold:
            classes.append("bold")
        if self.italic:
            classes.append("italic")
        if self.underline:
            classes.append("underline")
        if self.strikethrough:
            classes.append("line-through")
        if self.small_caps:
            classes.append("small-caps")

        # Baseline offset
        if self.baseline_offset == "SUPERSCRIPT":
            classes.append("superscript")
        elif self.baseline_offset == "SUBSCRIPT":
            classes.append("subscript")

        # Font family
        if self.font_family:
            # Normalize font family name for class
            font_name = self.font_family.lower().replace(" ", "-")
            classes.append(f"font-family-{font_name}")

        # Font size
        if self.font_size_pt:
            classes.append(f"text-size-{format_pt(self.font_size_pt)}")

        # Font weight (if not implied by bold)
        if self.font_weight and self.font_weight != 400:
            if self.font_weight == 700 and self.bold:
                pass  # Already have "bold"
            else:
                classes.append(f"font-weight-{self.font_weight}")

        # Text color
        if self.foreground_color:
            if self.foreground_color.theme:
                classes.append(f"text-color-theme-{self.foreground_color.theme}")
            elif self.foreground_color.hex:
                classes.append(f"text-color-{self.foreground_color.hex}")

        # Background/highlight color
        if self.background_color and self.background_color.hex:
            classes.append(f"bg-{self.background_color.hex}")

        return classes


@dataclass
class ParagraphStyle:
    """Paragraph styling."""

    alignment: TextAlignment | None = None
    line_spacing: int | None = None  # Percentage (100 = single)
    space_above_pt: float | None = None
    space_below_pt: float | None = None
    indent_start_pt: float | None = None
    indent_end_pt: float | None = None
    indent_first_line_pt: float | None = None
    direction: str | None = None
    spacing_mode: str | None = None
    # Bullet properties
    has_bullet: bool = False
    bullet_glyph: str | None = None
    nesting_level: int = 0

    @classmethod
    def from_api(cls, style_obj: dict[str, Any] | None) -> ParagraphStyle | None:
        """Create ParagraphStyle from API style object."""
        if not style_obj:
            return None

        ps = cls()

        # Alignment
        align = style_obj.get("alignment")
        if align:
            with contextlib.suppress(ValueError):
                ps.alignment = TextAlignment(align)

        # Line spacing
        ps.line_spacing = style_obj.get("lineSpacing")

        # Space above/below
        space_above = style_obj.get("spaceAbove")
        if space_above and space_above.get("magnitude"):
            ps.space_above_pt = space_above["magnitude"]

        space_below = style_obj.get("spaceBelow")
        if space_below and space_below.get("magnitude"):
            ps.space_below_pt = space_below["magnitude"]

        # Indentation
        indent_start = style_obj.get("indentStart")
        if indent_start and indent_start.get("magnitude"):
            ps.indent_start_pt = indent_start["magnitude"]

        indent_end = style_obj.get("indentEnd")
        if indent_end and indent_end.get("magnitude"):
            ps.indent_end_pt = indent_end["magnitude"]

        indent_first = style_obj.get("indentFirstLine")
        if indent_first and indent_first.get("magnitude"):
            ps.indent_first_line_pt = indent_first["magnitude"]

        # Direction
        ps.direction = style_obj.get("direction")

        # Spacing mode
        ps.spacing_mode = style_obj.get("spacingMode")

        return ps

    def to_classes(self) -> list[str]:
        """Convert to list of SML class strings."""
        classes = []

        # Alignment
        if self.alignment:
            align_map = {
                TextAlignment.START: "text-align-left",
                TextAlignment.CENTER: "text-align-center",
                TextAlignment.END: "text-align-right",
                TextAlignment.JUSTIFIED: "text-align-justify",
            }
            if self.alignment in align_map:
                classes.append(align_map[self.alignment])

        # Line spacing
        if self.line_spacing:
            classes.append(f"leading-{self.line_spacing}")

        # Space above/below
        if self.space_above_pt:
            classes.append(f"space-above-{format_pt(self.space_above_pt)}")
        if self.space_below_pt:
            classes.append(f"space-below-{format_pt(self.space_below_pt)}")

        # Indentation
        if self.indent_start_pt:
            classes.append(f"indent-start-{format_pt(self.indent_start_pt)}")
        if self.indent_first_line_pt:
            classes.append(f"indent-first-{format_pt(self.indent_first_line_pt)}")

        # Direction
        if self.direction == "RIGHT_TO_LEFT":
            classes.append("dir-rtl")

        # Spacing mode
        if self.spacing_mode == "NEVER_COLLAPSE":
            classes.append("spacing-never-collapse")
        elif self.spacing_mode == "COLLAPSE_LISTS":
            classes.append("spacing-collapse-lists")

        # Bullet styling
        if self.has_bullet:
            classes.append("bullet")
            if self.bullet_glyph:
                # Map common glyphs to classes
                glyph_map = {
                    "●": "bullet-disc",
                    "○": "bullet-circle",
                    "■": "bullet-square",
                    "◆": "bullet-diamond",
                    "➔": "bullet-arrow",
                    "★": "bullet-star",
                }
                if self.bullet_glyph in glyph_map:
                    classes.append(glyph_map[self.bullet_glyph])

            # Nesting level
            if self.nesting_level > 0:
                classes.append(f"indent-level-{self.nesting_level}")

        return classes


# ============================================================================
# Class Parsing (SML → Data Structures)
# ============================================================================


def parse_class_string(class_str: str) -> list[str]:
    """Parse class string into individual classes."""
    return class_str.split() if class_str else []


def parse_position_classes(classes: list[str]) -> dict[str, float]:
    """Extract position values from classes.

    Returns dict with keys: x, y, w, h
    """
    result: dict[str, float] = {}

    for cls in classes:
        # x-{value}
        if match := re.match(r"^x-(-?\d+(?:\.\d+)?)$", cls):
            result["x"] = float(match.group(1))
        # y-{value}
        elif match := re.match(r"^y-(-?\d+(?:\.\d+)?)$", cls):
            result["y"] = float(match.group(1))
        # w-{value}
        elif match := re.match(r"^w-(\d+(?:\.\d+)?)$", cls):
            result["w"] = float(match.group(1))
        # h-{value}
        elif match := re.match(r"^h-(\d+(?:\.\d+)?)$", cls):
            result["h"] = float(match.group(1))

    return result


def parse_fill_class(cls: str) -> Fill | None:
    """Parse a fill class into a Fill object."""
    if cls == "fill-none":
        return Fill(state=PropertyState.NOT_RENDERED)
    if cls == "fill-inherit":
        return Fill(state=PropertyState.INHERIT)

    # fill-theme-{name}[/opacity]
    if match := re.match(r"^fill-theme-([a-z0-9-]+)(?:/(\d+))?$", cls):
        theme_name = match.group(1)
        opacity = int(match.group(2)) / 100 if match.group(2) else 1.0
        return Fill(color=Color(theme=theme_name, alpha=opacity))

    # fill-#{hex}[/opacity]
    if match := re.match(r"^fill-(#[0-9a-fA-F]{6})(?:/(\d+))?$", cls):
        hex_color = match.group(1).lower()
        opacity = int(match.group(2)) / 100 if match.group(2) else 1.0
        return Fill(color=Color(hex=hex_color, alpha=opacity))

    return None


def parse_stroke_classes(classes: list[str]) -> Stroke | None:
    """Parse stroke-related classes into a Stroke object."""
    stroke = Stroke()
    found_stroke = False

    for cls in classes:
        if cls == "stroke-none":
            return Stroke(state=PropertyState.NOT_RENDERED)
        if cls == "stroke-inherit":
            return Stroke(state=PropertyState.INHERIT)

        # stroke-theme-{name}[/opacity]
        if match := re.match(r"^stroke-theme-([a-z0-9-]+)(?:/(\d+))?$", cls):
            theme_name = match.group(1)
            opacity = int(match.group(2)) / 100 if match.group(2) else 1.0
            stroke.color = Color(theme=theme_name, alpha=opacity)
            found_stroke = True

        # stroke-#{hex}[/opacity]
        elif match := re.match(r"^stroke-(#[0-9a-fA-F]{6})(?:/(\d+))?$", cls):
            hex_color = match.group(1).lower()
            opacity = int(match.group(2)) / 100 if match.group(2) else 1.0
            stroke.color = Color(hex=hex_color, alpha=opacity)
            found_stroke = True

        # stroke-w-{value}
        elif match := re.match(r"^stroke-w-(\d+(?:\.\d+)?)$", cls):
            stroke.weight_pt = float(match.group(1))
            found_stroke = True

        # stroke dash styles
        elif cls == "stroke-solid":
            stroke.dash_style = DashStyle.SOLID
            found_stroke = True
        elif cls == "stroke-dot":
            stroke.dash_style = DashStyle.DOT
            found_stroke = True
        elif cls == "stroke-dash":
            stroke.dash_style = DashStyle.DASH
            found_stroke = True
        elif cls == "stroke-dash-dot":
            stroke.dash_style = DashStyle.DASH_DOT
            found_stroke = True
        elif cls == "stroke-long-dash":
            stroke.dash_style = DashStyle.LONG_DASH
            found_stroke = True
        elif cls == "stroke-long-dash-dot":
            stroke.dash_style = DashStyle.LONG_DASH_DOT
            found_stroke = True

    return stroke if found_stroke else None


def parse_text_style_classes(classes: list[str]) -> TextStyle:
    """Parse text styling classes into a TextStyle object."""
    ts = TextStyle()

    for cls in classes:
        # Boolean styles
        if cls == "bold":
            ts.bold = True
        elif cls == "italic":
            ts.italic = True
        elif cls == "underline":
            ts.underline = True
        elif cls == "line-through":
            ts.strikethrough = True
        elif cls == "small-caps":
            ts.small_caps = True
        elif cls == "superscript":
            ts.baseline_offset = "SUPERSCRIPT"
        elif cls == "subscript":
            ts.baseline_offset = "SUBSCRIPT"

        # Font family
        elif match := re.match(r"^font-family-(.+)$", cls):
            font_name = match.group(1).replace("-", " ").title()
            ts.font_family = font_name

        # Font size
        elif match := re.match(r"^text-size-(\d+(?:\.\d+)?)$", cls):
            ts.font_size_pt = float(match.group(1))

        # Font weight
        elif match := re.match(r"^font-weight-(\d+)$", cls):
            ts.font_weight = int(match.group(1))

        # Text color
        elif match := re.match(r"^text-color-theme-([a-z0-9-]+)$", cls):
            ts.foreground_color = Color(theme=match.group(1))
        elif match := re.match(r"^text-color-(#[0-9a-fA-F]{6})(?:/(\d+))?$", cls):
            opacity = int(match.group(2)) / 100 if match.group(2) else 1.0
            ts.foreground_color = Color(hex=match.group(1).lower(), alpha=opacity)

        # Background color
        elif match := re.match(r"^bg-(#[0-9a-fA-F]{6})$", cls):
            ts.background_color = Color(hex=match.group(1).lower())

    return ts
