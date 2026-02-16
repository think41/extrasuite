"""Utility functions for the serde module."""

from __future__ import annotations

import re
from typing import Any
from xml.etree.ElementTree import Element, indent, tostring

from extradoc.api_types._generated import (
    Dimension,
    OptionalColor,
    ParagraphBorder,
    TableCellBorder,
)


def sanitize_tab_name(name: str) -> str:
    """Sanitize a tab name for use as a folder name.

    Replaces special characters with underscores and collapses multiples.
    """
    sanitized = re.sub(r"[^\w\-]", "_", name)
    sanitized = re.sub(r"_+", "_", sanitized)
    sanitized = sanitized.strip("_")
    return sanitized or "untitled"


# ---------------------------------------------------------------------------
# Color conversions
# ---------------------------------------------------------------------------


def rgb_to_hex(r: float, g: float, b: float) -> str:
    """Convert RGB 0-1 floats to #RRGGBB hex string."""
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


def hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    """Convert #RRGGBB hex string to RGB 0-1 floats."""
    h = hex_color.lstrip("#")
    return (
        int(h[0:2], 16) / 255.0,
        int(h[2:4], 16) / 255.0,
        int(h[4:6], 16) / 255.0,
    )


def optional_color_to_hex(oc: OptionalColor | None) -> str | None:
    """Convert OptionalColor to hex string, or None if unset."""
    if not oc or not oc.color or not oc.color.rgb_color:
        return None
    rgb = oc.color.rgb_color
    r = rgb.red if rgb.red is not None else 0.0
    g = rgb.green if rgb.green is not None else 0.0
    b = rgb.blue if rgb.blue is not None else 0.0
    return rgb_to_hex(r, g, b)


def hex_to_optional_color(hex_color: str) -> OptionalColor:
    """Convert hex string to OptionalColor."""
    r, g, b = hex_to_rgb(hex_color)
    return OptionalColor.model_validate(
        {"color": {"rgbColor": {"red": r, "green": g, "blue": b}}}
    )


# ---------------------------------------------------------------------------
# Dimension conversions
# ---------------------------------------------------------------------------


def dim_to_str(dim: Dimension | None) -> str | None:
    """Convert Dimension to string like '12pt'."""
    if not dim or dim.magnitude is None:
        return None
    return f"{dim.magnitude}pt"


def str_to_dim(s: str | None) -> Dimension | None:
    """Convert string like '12pt' to Dimension."""
    if not s:
        return None
    num_str = s.rstrip("pt")
    return Dimension.model_validate({"magnitude": float(num_str), "unit": "PT"})


# ---------------------------------------------------------------------------
# Border conversions
# ---------------------------------------------------------------------------


def para_border_to_str(border: ParagraphBorder | None) -> str | None:
    """Convert ParagraphBorder to 'width,#color,dash,padding' string."""
    if not border or not border.width or border.width.magnitude is None:
        return None
    parts = [str(border.width.magnitude)]
    color_hex = optional_color_to_hex(border.color)
    parts.append(color_hex or "#000000")
    parts.append(border.dash_style.value if border.dash_style else "SOLID")
    if border.padding and border.padding.magnitude is not None:
        parts.append(str(border.padding.magnitude))
    return ",".join(parts)


def str_to_para_border(s: str | None) -> ParagraphBorder | None:
    """Convert 'width,#color,dash,padding' string to ParagraphBorder."""
    if not s:
        return None
    parts = s.split(",")
    if len(parts) < 2:
        return None
    d: dict[str, Any] = {
        "width": {"magnitude": float(parts[0]), "unit": "PT"},
        "color": _hex_to_color_dict(parts[1]),
    }
    if len(parts) > 2 and parts[2]:
        d["dashStyle"] = parts[2]
    if len(parts) > 3 and parts[3]:
        d["padding"] = {"magnitude": float(parts[3]), "unit": "PT"}
    return ParagraphBorder.model_validate(d)


def cell_border_to_str(border: TableCellBorder | None) -> str | None:
    """Convert TableCellBorder to 'width,#color,dash' string."""
    if not border or not border.width or border.width.magnitude is None:
        return None
    parts = [str(border.width.magnitude)]
    color_hex = optional_color_to_hex(border.color)
    parts.append(color_hex or "#000000")
    parts.append(border.dash_style.value if border.dash_style else "SOLID")
    return ",".join(parts)


def str_to_cell_border(s: str | None) -> TableCellBorder | None:
    """Convert 'width,#color,dash' string to TableCellBorder."""
    if not s:
        return None
    parts = s.split(",")
    if len(parts) < 2:
        return None
    d: dict[str, Any] = {
        "width": {"magnitude": float(parts[0]), "unit": "PT"},
        "color": _hex_to_color_dict(parts[1]),
    }
    if len(parts) > 2 and parts[2]:
        d["dashStyle"] = parts[2]
    return TableCellBorder.model_validate(d)


def _hex_to_color_dict(hex_color: str) -> dict[str, Any]:
    """Convert hex color to OptionalColor-compatible dict."""
    r, g, b = hex_to_rgb(hex_color)
    return {"color": {"rgbColor": {"red": r, "green": g, "blue": b}}}


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------


def element_to_string(elem: Element) -> str:
    """Convert Element to pretty-printed XML string with declaration."""
    indent(elem)
    xml_str = tostring(elem, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str + "\n"
