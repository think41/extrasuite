"""
Formula compression for Google Sheets formulas.

Compresses per-cell formulas by grouping cells with equivalent relative reference
patterns. The output uses the actual formula from the first cell of a range,
which is more intuitive than pattern placeholders since readers familiar with
spreadsheets understand that formulas auto-fill with relative references.

Only contiguous ranges of 4+ cells are compressed. Smaller groups are stored
as individual formulas since listing them is clearer.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


def _col_letter_to_index(col: str) -> int:
    """Convert column letter to zero-based index."""
    result = 0
    for c in col.upper():
        result = result * 26 + (ord(c) - ord("A") + 1)
    return result - 1


def _index_to_col_letter(index: int) -> str:
    """Convert zero-based index to column letter."""
    result = ""
    index += 1
    while index > 0:
        index -= 1
        result = chr(ord("A") + (index % 26)) + result
        index //= 26
    return result


def _parse_cell_ref(ref: str) -> tuple[str, bool, str, bool]:
    """Parse a cell reference into components.

    Returns: (col_str, col_absolute, row_str, row_absolute)
    """
    match = re.match(r"(\$?)([A-Za-z]+)(\$?)(\d+)", ref)
    if not match:
        return ("", False, "", False)
    col_abs, col, row_abs, row = match.groups()
    return (col, bool(col_abs), row, bool(row_abs))


def _normalize_formula(formula: str, anchor_row: int, anchor_col: int) -> str | None:
    """Normalize a formula by converting relative references to offsets.

    Returns None if formula contains features that prevent pattern matching.
    """
    # Find all cell references (including absolute references)
    cell_ref_pattern = r"\$?[A-Za-z]+\$?\d+"

    def replace_ref(match: re.Match) -> str:
        ref = match.group(0)
        col_str, col_abs, row_str, row_abs = _parse_cell_ref(ref)
        if not col_str or not row_str:
            return ref

        col_idx = _col_letter_to_index(col_str)
        row_idx = int(row_str) - 1

        # For absolute references, keep as-is
        if col_abs and row_abs:
            return ref

        # Calculate relative offset
        col_offset = col_idx - anchor_col if not col_abs else None
        row_offset = row_idx - anchor_row if not row_abs else None

        # Create placeholder
        if col_abs:
            col_part = f"${col_str}"
        else:
            col_part = f"{{c{col_offset:+d}}}" if col_offset != 0 else "{c}"

        if row_abs:
            row_part = f"${row_str}"
        else:
            row_part = f"{{r{row_offset:+d}}}" if row_offset != 0 else "{r}"

        return col_part + row_part

    try:
        normalized = re.sub(cell_ref_pattern, replace_ref, formula)
        return normalized
    except Exception:
        return None


def _denormalize_formula(pattern: str, row: int, col: int) -> str:
    """Convert a normalized pattern back to a formula for a specific cell."""

    def replace_placeholder(match: re.Match) -> str:
        placeholder = match.group(0)

        # Handle column placeholder
        if placeholder == "{c}":
            return _index_to_col_letter(col)
        elif placeholder.startswith("{c"):
            offset = int(placeholder[2:-1])
            return _index_to_col_letter(col + offset)

        # Handle row placeholder
        if placeholder == "{r}":
            return str(row + 1)
        elif placeholder.startswith("{r"):
            offset = int(placeholder[2:-1])
            return str(row + 1 + offset)

        return placeholder

    return re.sub(r"\{[cr][+-]?\d*\}", replace_placeholder, pattern)


def _cells_form_contiguous_range(
    cells: list[tuple[int, int]],
) -> tuple[int, int, int, int] | None:
    """Check if cells form a contiguous rectangular range.

    Returns (start_row, end_row, start_col, end_col) if contiguous, None otherwise.
    """
    if not cells:
        return None

    rows = sorted({r for r, c in cells})
    cols = sorted({c for r, c in cells})

    # Check if it's a single column or single row range
    if len(cols) == 1 and rows == list(range(min(rows), max(rows) + 1)):
        # Single column - rows are contiguous
        return (min(rows), max(rows) + 1, cols[0], cols[0] + 1)
    elif len(rows) == 1 and cols == list(range(min(cols), max(cols) + 1)):
        # Single row - cols are contiguous
        return (rows[0], rows[0] + 1, min(cols), max(cols) + 1)

    # Check for full rectangular range
    expected_cells = {
        (r, c)
        for r in range(min(rows), max(rows) + 1)
        for c in range(min(cols), max(cols) + 1)
    }
    if set(cells) == expected_cells:
        return (min(rows), max(rows) + 1, min(cols), max(cols) + 1)

    return None


def _coord_to_a1(row: int, col: int) -> str:
    """Convert (row, col) to A1 notation."""
    return f"{_index_to_col_letter(col)}{row + 1}"


def _range_to_a1(start_row: int, end_row: int, start_col: int, end_col: int) -> str:
    """Convert range indices to A1 notation."""
    if end_row - start_row == 1 and end_col - start_col == 1:
        return _coord_to_a1(start_row, start_col)
    return (
        f"{_coord_to_a1(start_row, start_col)}:{_coord_to_a1(end_row - 1, end_col - 1)}"
    )


# Minimum number of cells required to compress a range.
# Smaller groups are stored as individual formulas for clarity.
MIN_CELLS_FOR_COMPRESSION = 4


def compress_formulas(formulas: dict[str, str]) -> dict[str, Any]:
    """Compress cell formulas by grouping equivalent relative patterns.

    Groups cells with the same relative reference pattern. For compressed ranges,
    stores the actual formula from the first cell (more intuitive than pattern
    placeholders). Only contiguous ranges with 4+ cells are compressed.

    Args:
        formulas: Dict mapping A1 cell references to formula strings

    Returns:
        {
            "formulaRanges": [
                {"formula": "=A2+B2", "range": "C2:C10"},
                ...
            ],
            "formulas": {"A1": "=UNIQUE(...)", ...}  # Non-compressible formulas
        }
    """
    if not formulas:
        return {}

    # Parse cell references and normalize formulas
    cell_data: dict[
        tuple[int, int], tuple[str, str]
    ] = {}  # (row, col) -> (formula, normalized)

    for cell_a1, formula in formulas.items():
        match = re.match(r"([A-Za-z]+)(\d+)", cell_a1)
        if not match:
            continue
        col_str, row_str = match.groups()
        col = _col_letter_to_index(col_str)
        row = int(row_str) - 1

        normalized = _normalize_formula(formula, row, col)
        if normalized:
            cell_data[(row, col)] = (formula, normalized)

    if not cell_data:
        # Nothing could be normalized, return original
        return {"formulas": formulas}

    # Group by normalized pattern
    pattern_cells: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for coord, (_formula, normalized) in cell_data.items():
        pattern_cells[normalized].append(coord)

    # Build output
    formula_ranges: list[dict[str, Any]] = []
    remaining_formulas: dict[str, str] = {}

    for _pattern, cells in pattern_cells.items():
        cells_sorted = sorted(cells)
        range_bounds = _cells_form_contiguous_range(cells_sorted)

        # Only compress contiguous ranges with MIN_CELLS_FOR_COMPRESSION+ cells
        if range_bounds and len(cells_sorted) >= MIN_CELLS_FOR_COMPRESSION:
            # Contiguous range - represent as formula + range
            start_row, end_row, start_col, end_col = range_bounds
            range_a1 = _range_to_a1(start_row, end_row, start_col, end_col)
            # Use the actual formula from the first cell (more intuitive than pattern)
            first_cell_formula = cell_data[(start_row, start_col)][0]
            formula_ranges.append(
                {
                    "formula": first_cell_formula,
                    "range": range_a1,
                }
            )
        else:
            # Not compressible: single cell, non-contiguous, or too few cells
            # Store as individual formulas
            for row, col in cells_sorted:
                remaining_formulas[_coord_to_a1(row, col)] = cell_data[(row, col)][0]

    result: dict[str, Any] = {}
    if formula_ranges:
        result["formulaRanges"] = formula_ranges
    if remaining_formulas:
        result["formulas"] = remaining_formulas

    return result


def expand_formulas(compressed: dict[str, Any]) -> dict[str, str]:
    """Expand compressed formulas back to per-cell representation.

    This is the inverse of compress_formulas.
    """
    result: dict[str, str] = {}

    # Expand formula ranges
    for range_rule in compressed.get("formulaRanges", []):
        formula = range_rule["formula"]
        range_str = range_rule["range"]

        if ":" in range_str:
            start, end = range_str.split(":")
            start_match = re.match(r"([A-Za-z]+)(\d+)", start)
            end_match = re.match(r"([A-Za-z]+)(\d+)", end)
            if start_match and end_match:
                start_col = _col_letter_to_index(start_match.group(1))
                start_row = int(start_match.group(2)) - 1
                end_col = _col_letter_to_index(end_match.group(1))
                end_row = int(end_match.group(2)) - 1

                # Normalize the formula from the first cell to get the pattern
                pattern = _normalize_formula(formula, start_row, start_col)
                if pattern:
                    for row in range(start_row, end_row + 1):
                        for col in range(start_col, end_col + 1):
                            expanded = _denormalize_formula(pattern, row, col)
                            result[_coord_to_a1(row, col)] = expanded
                else:
                    # Fallback: use formula as-is for all cells
                    for row in range(start_row, end_row + 1):
                        for col in range(start_col, end_col + 1):
                            result[_coord_to_a1(row, col)] = formula
        else:
            # Single cell in "range" format
            result[range_str] = formula

    # Add non-compressed formulas
    result.update(compressed.get("formulas", {}))

    return result
