"""Unit conversion utilities for Google Slides API.

The Google Slides API uses EMU (English Metric Units) for dimensions.
SML uses points (pt) for a more familiar unit.

Conversion: 1 pt = 12700 EMU
"""

from __future__ import annotations

# Conversion constant: 1 point = 12700 EMU
EMU_PER_PT = 12700


def emu_to_pt(emu: float) -> float:
    """Convert EMU to points.

    Args:
        emu: Value in EMU (English Metric Units)

    Returns:
        Value in points
    """
    return emu / EMU_PER_PT


def pt_to_emu(pt: float) -> int:
    """Convert points to EMU.

    Args:
        pt: Value in points

    Returns:
        Value in EMU (rounded to integer)
    """
    return int(pt * EMU_PER_PT)


def rgb_to_hex(red: float = 0, green: float = 0, blue: float = 0) -> str:
    """Convert RGB float values (0-1) to hex color string.

    Args:
        red: Red component (0.0 to 1.0)
        green: Green component (0.0 to 1.0)
        blue: Blue component (0.0 to 1.0)

    Returns:
        Hex color string like "#4285f4"
    """
    r = round(red * 255)
    g = round(green * 255)
    b = round(blue * 255)
    return f"#{r:02x}{g:02x}{b:02x}"


def hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    """Convert hex color string to RGB float values (0-1).

    Args:
        hex_color: Hex color string like "#4285f4" or "4285f4"

    Returns:
        Tuple of (red, green, blue) each 0.0 to 1.0
    """
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        raise ValueError(f"Invalid hex color: {hex_color}")

    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    return (r, g, b)


def format_pt(value: float, precision: int = 2) -> str:
    """Format a point value, removing unnecessary decimal places.

    Args:
        value: Value in points
        precision: Maximum decimal places

    Returns:
        Formatted string (e.g., "100" or "100.5")
    """
    rounded = round(value, precision)
    if rounded == int(rounded):
        return str(int(rounded))
    return str(rounded)
