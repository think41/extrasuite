"""
Format compression for Google Sheets cell formats.

Compresses verbose per-cell formatting into compact cascading rules:
- Range-based rules with largest ranges first
- Later rules override earlier ones (cascade)
- Optimized format representation (hex colors, no deprecated fields, delta encoding)
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

# =============================================================================
# Range handling
# =============================================================================

@dataclass(frozen=True)
class Range:
    """A rectangular range of cells."""

    start_row: int
    start_col: int
    end_row: int  # inclusive
    end_col: int  # inclusive

    def cell_count(self) -> int:
        return (self.end_row - self.start_row + 1) * (self.end_col - self.start_col + 1)

    def cells(self) -> set[tuple[int, int]]:
        return {
            (r, c)
            for r in range(self.start_row, self.end_row + 1)
            for c in range(self.start_col, self.end_col + 1)
        }

    def to_a1(self) -> str:
        """Convert to A1 notation."""
        start = _coord_to_a1(self.start_row, self.start_col)
        end = _coord_to_a1(self.end_row, self.end_col)
        if start == end:
            return start
        return f"{start}:{end}"

    @classmethod
    def from_cells(cls, cells: set[tuple[int, int]]) -> Range:
        """Create bounding box range from a set of cells."""
        if not cells:
            raise ValueError("Cannot create range from empty cells")
        rows = [c[0] for c in cells]
        cols = [c[1] for c in cells]
        return cls(min(rows), min(cols), max(rows), max(cols))


def _coord_to_a1(row: int, col: int) -> str:
    """Convert (row, col) to A1 notation."""
    col_str = ""
    c = col
    while c >= 0:
        col_str = chr(ord('A') + c % 26) + col_str
        c = c // 26 - 1
    return f"{col_str}{row + 1}"


def find_largest_rectangle(cells: set[tuple[int, int]]) -> Range | None:
    """
    Find the largest rectangle that fits entirely within the given cells.
    Uses the maximal rectangle in histogram algorithm.
    """
    if not cells:
        return None

    if len(cells) == 1:
        c = next(iter(cells))
        return Range(c[0], c[1], c[0], c[1])

    min_row = min(c[0] for c in cells)
    max_row = max(c[0] for c in cells)
    min_col = min(c[1] for c in cells)
    max_col = max(c[1] for c in cells)

    # Check if entire bounding box is filled
    bbox = Range(min_row, min_col, max_row, max_col)
    if bbox.cells() == cells:
        return bbox

    # Build binary matrix
    height = max_row - min_row + 1
    width = max_col - min_col + 1
    matrix = [[0] * width for _ in range(height)]
    for r, c in cells:
        matrix[r - min_row][c - min_col] = 1

    # Find largest rectangle using histogram method
    best_area = 0
    best_rect = None

    heights = [0] * width
    for row in range(height):
        for col in range(width):
            if matrix[row][col] == 1:
                heights[col] += 1
            else:
                heights[col] = 0

        # Find largest rectangle in histogram
        stack: list[int] = []
        for col in range(width + 1):
            h = heights[col] if col < width else 0
            while stack and heights[stack[-1]] > h:
                height_idx = stack.pop()
                rect_height = heights[height_idx]
                rect_width = col if not stack else col - stack[-1] - 1
                area = rect_height * rect_width

                if area > best_area:
                    best_area = area
                    left_col = stack[-1] + 1 if stack else 0
                    right_col = col - 1
                    bottom_row = row
                    top_row = row - rect_height + 1
                    best_rect = Range(
                        top_row + min_row,
                        left_col + min_col,
                        bottom_row + min_row,
                        right_col + min_col
                    )
            stack.append(col)

    return best_rect


# =============================================================================
# Format optimization
# =============================================================================

def _rgb_to_hex(color: dict[str, Any]) -> str:
    """Convert {"red": 0.84, "green": 1, "blue": 0.84} to "#D7FFD7"."""
    r = int(color.get("red", 0) * 255)
    g = int(color.get("green", 0) * 255)
    b = int(color.get("blue", 0) * 255)
    return f"#{r:02X}{g:02X}{b:02X}"


def _is_empty_color(color: dict[str, Any] | None) -> bool:
    """Check if color is empty/black."""
    if not color:
        return True
    return (
        color.get("red", 0) == 0 and
        color.get("green", 0) == 0 and
        color.get("blue", 0) == 0
    )


def _compact_color_style(color_style: dict[str, Any] | None) -> str | dict[str, Any] | None:
    """Convert colorStyle to compact form."""
    if not color_style:
        return None

    # Keep theme colors as-is
    if "themeColor" in color_style:
        return color_style

    rgb = color_style.get("rgbColor", {})
    if _is_empty_color(rgb):
        return "#000000"
    return _rgb_to_hex(rgb)


def _optimize_border(border: dict[str, Any] | None) -> dict[str, Any] | None:
    """Optimize a single border definition."""
    if not border:
        return None

    result: dict[str, Any] = {}

    if "style" in border:
        result["style"] = border["style"]
    if "width" in border and border["width"] != 1:
        result["width"] = border["width"]

    # Prefer colorStyle over color
    if "colorStyle" in border:
        color = _compact_color_style(border["colorStyle"])
        if color and color != "#000000":
            result["color"] = color
    elif "color" in border:
        if not _is_empty_color(border["color"]):
            result["color"] = _rgb_to_hex(border["color"])

    return result if result else None


def _optimize_borders(borders: dict[str, Any] | None) -> dict[str, Any] | None:
    """Optimize borders object."""
    if not borders:
        return None

    result: dict[str, Any] = {}
    for side in ["top", "bottom", "left", "right"]:
        if side in borders:
            optimized = _optimize_border(borders[side])
            if optimized:
                result[side] = optimized

    return result if result else None


def _optimize_text_format(text_format: dict[str, Any] | None) -> dict[str, Any] | None:
    """Optimize textFormat object."""
    if not text_format:
        return None

    result: dict[str, Any] = {}

    # Boolean flags - only include if True
    for flag in ["bold", "italic", "strikethrough", "underline"]:
        if text_format.get(flag):
            result[flag] = True

    # Font family - only if not default
    if "fontFamily" in text_format:
        font = text_format["fontFamily"]
        if font and font != "arial,sans,sans-serif":
            result["fontFamily"] = font

    # Font size - only if not default (10)
    if "fontSize" in text_format and text_format["fontSize"] != 10:
        result["fontSize"] = text_format["fontSize"]

    # Foreground color - prefer colorStyle
    if "foregroundColorStyle" in text_format:
        color = _compact_color_style(text_format["foregroundColorStyle"])
        if color and color != "#000000":
            result["foregroundColor"] = color
    elif "foregroundColor" in text_format:
        if not _is_empty_color(text_format["foregroundColor"]):
            result["foregroundColor"] = _rgb_to_hex(text_format["foregroundColor"])

    # Link
    if "link" in text_format:
        result["link"] = text_format["link"]

    return result if result else None


def optimize_format(fmt: dict[str, Any]) -> dict[str, Any]:
    """
    Optimize a cell format object:
    1. Remove deprecated fields when new versions exist
    2. Compact colors to hex strings
    3. Remove default/empty values
    """
    if not fmt:
        return {}

    result: dict[str, Any] = {}

    # Background color - prefer backgroundColorStyle over backgroundColor
    if "backgroundColorStyle" in fmt:
        color = _compact_color_style(fmt["backgroundColorStyle"])
        if color and color != "#FFFFFF":
            result["backgroundColor"] = color
    elif "backgroundColor" in fmt:
        if not _is_empty_color(fmt["backgroundColor"]):
            color = _rgb_to_hex(fmt["backgroundColor"])
            if color != "#FFFFFF":
                result["backgroundColor"] = color

    # Borders
    if "borders" in fmt:
        borders = _optimize_borders(fmt["borders"])
        if borders:
            result["borders"] = borders

    # Padding - only if non-default
    if "padding" in fmt:
        p = fmt["padding"]
        default_padding = {"top": 2, "right": 3, "bottom": 2, "left": 3}
        if p != default_padding:
            result["padding"] = p

    # Alignment
    if "horizontalAlignment" in fmt:
        result["horizontalAlignment"] = fmt["horizontalAlignment"]
    if "verticalAlignment" in fmt and fmt["verticalAlignment"] != "BOTTOM":
        result["verticalAlignment"] = fmt["verticalAlignment"]

    # Wrap strategy - only if not default
    if "wrapStrategy" in fmt and fmt["wrapStrategy"] != "OVERFLOW_CELL":
        result["wrapStrategy"] = fmt["wrapStrategy"]

    # Text format
    if "textFormat" in fmt:
        tf = _optimize_text_format(fmt["textFormat"])
        if tf:
            result["textFormat"] = tf

    # Number format
    if "numberFormat" in fmt:
        result["numberFormat"] = fmt["numberFormat"]

    # Text direction/rotation
    if "textDirection" in fmt:
        result["textDirection"] = fmt["textDirection"]
    if "textRotation" in fmt:
        result["textRotation"] = fmt["textRotation"]

    # Hyperlink display
    if "hyperlinkDisplayType" in fmt and fmt["hyperlinkDisplayType"] != "PLAIN_TEXT":
        result["hyperlinkDisplayType"] = fmt["hyperlinkDisplayType"]

    return result


def compute_delta(base_format: dict[str, Any], full_format: dict[str, Any]) -> dict[str, Any]:
    """
    Compute the delta between base format and full format.
    Returns only the properties that are different or new.
    """
    if not base_format:
        return full_format
    if not full_format:
        return {}

    delta: dict[str, Any] = {}

    for key, value in full_format.items():
        base_value = base_format.get(key)

        if base_value is None:
            # New property
            delta[key] = value
        elif isinstance(value, dict) and isinstance(base_value, dict):
            # Nested dict - recurse
            nested_delta = compute_delta(base_value, value)
            if nested_delta:
                delta[key] = nested_delta
        elif value != base_value:
            # Different value
            delta[key] = value

    return delta


# =============================================================================
# Main compression function
# =============================================================================

def compress_cell_formats(
    cell_formats: dict[str, dict[str, Any]],
    threshold: float = 0.6
) -> dict[str, Any]:
    """
    Compress cell formats into cascading rules.

    Args:
        cell_formats: Dict mapping A1 cell references to format dicts
        threshold: Minimum ratio for dominant format to use bounding box (0.0-1.0)

    Returns:
        {"formatRules": [{"range": "A1:Z100", "format": {...}}, ...]}
    """
    if not cell_formats:
        return {"formatRules": []}

    # Parse A1 references to coordinates and optimize formats
    import re

    cell_data: dict[tuple[int, int], dict[str, Any]] = {}
    for cell_a1, fmt in cell_formats.items():
        match = re.match(r"([A-Z]+)(\d+)", cell_a1)
        if not match:
            continue
        col_str, row_str = match.groups()
        col = 0
        for c in col_str:
            col = col * 26 + (ord(c) - ord('A') + 1)
        row = int(row_str) - 1
        col = col - 1

        optimized = optimize_format(fmt)
        if optimized:  # Skip empty formats
            cell_data[(row, col)] = optimized

    if not cell_data:
        return {"formatRules": []}

    # Group cells by format signature
    def format_signature(fmt: dict[str, Any]) -> str:
        return json.dumps(fmt, sort_keys=True)

    sig_to_format: dict[str, dict[str, Any]] = {}
    cell_sigs: dict[tuple[int, int], str] = {}

    for coord, fmt in cell_data.items():
        sig = format_signature(fmt)
        sig_to_format[sig] = fmt
        cell_sigs[coord] = sig

    rules: list[dict[str, Any]] = []
    remaining = dict(cell_sigs)
    all_cells = set(remaining.keys())

    base_format: dict[str, Any] | None = None

    # Check for dominant format
    sig_counts = Counter(remaining.values())
    total_cells = len(remaining)
    dominant_sig, dominant_count = sig_counts.most_common(1)[0]

    if dominant_count / total_cells >= threshold:
        # Use bounding box for dominant format
        bbox = Range.from_cells(all_cells)
        base_format = sig_to_format[dominant_sig]
        rules.append({
            "range": bbox.to_a1(),
            "format": base_format
        })

        # Remove dominant cells from remaining
        remaining = {c: s for c, s in remaining.items() if s != dominant_sig}

    # Process remaining cells with rectangle finding
    while remaining:
        sig_counts = Counter(remaining.values())

        best_rule: tuple[Range, str, set[tuple[int, int]]] | None = None
        best_cells_covered = 0

        for sig, _count in sig_counts.most_common():
            sig_cells = {c for c, s in remaining.items() if s == sig}
            rect = find_largest_rectangle(sig_cells)

            if rect:
                cells_covered = rect.cell_count()
                if cells_covered > best_cells_covered:
                    best_cells_covered = cells_covered
                    best_rule = (rect, sig, rect.cells() & sig_cells)

        if best_rule and best_cells_covered >= 1:
            rect, sig, covered_cells = best_rule
            full_format = sig_to_format[sig]

            # Compute delta from base format
            if base_format:
                delta = compute_delta(base_format, full_format)
                rule_format = delta if delta else full_format
            else:
                rule_format = full_format

            rules.append({
                "range": rect.to_a1(),
                "format": rule_format
            })

            for c in covered_cells:
                if c in remaining:
                    del remaining[c]
        else:
            # Output remaining as individual cells
            for coord, sig in list(remaining.items()):
                full_format = sig_to_format[sig]
                if base_format:
                    delta = compute_delta(base_format, full_format)
                    rule_format = delta if delta else full_format
                else:
                    rule_format = full_format

                rules.append({
                    "range": _coord_to_a1(coord[0], coord[1]),
                    "format": rule_format
                })
            break

    return {"formatRules": rules}
