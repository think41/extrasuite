"""
Formula compression for Google Sheets formulas.

Compresses per-cell formulas by grouping cells with equivalent relative reference
patterns. The output uses a unified format where keys are either cell references
(e.g., "A1") or ranges (e.g., "B2:K2"), and values are the formulas.

For ranges, the stored formula is from the first cell. Readers familiar with
spreadsheets understand that formulas auto-fill with relative references.

Non-contiguous cells with the same pattern are split into maximal contiguous
sub-ranges (e.g., A1, C1, D1, E1 becomes {"A1": "=...", "C1:E1": "=..."}).
"""

from __future__ import annotations

import re
from collections import defaultdict


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
    # - (?<![A-Za-z']) ensures we don't match mid-identifier or inside quoted sheet names
    #   (e.g., "ble1" in "Table1" or "R41" in "'R41 Shortlisted'!A:A")
    # - Use {1,3} for column letters since Google Sheets max column is XFD (3 letters)
    # - (?![_\[]) ensures we don't match structured refs (e.g., "Table1_2[#ALL]")
    cell_ref_pattern = r"(?<![A-Za-z'])\$?[A-Za-z]{1,3}\$?\d+(?![_\[])"

    def replace_ref(match: re.Match[str]) -> str:
        ref: str = match.group(0)
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

    def replace_placeholder(match: re.Match[str]) -> str:
        placeholder: str = match.group(0)

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


def _find_contiguous_ranges(
    cells: list[tuple[int, int]],
) -> list[tuple[int, int, int, int]]:
    """Find all maximal contiguous rectangular ranges from a list of cells.

    Given a list of cells that may not all be contiguous, find the maximal
    contiguous sub-ranges. For example, cells A1, C1, D1, E1 would return
    two ranges: A1 (single cell) and C1:E1.

    Returns list of (start_row, end_row, start_col, end_col) tuples.
    """
    if not cells:
        return []

    cells_set = set(cells)
    used = set()
    ranges = []

    # Sort cells by row, then column for consistent processing
    cells_sorted = sorted(cells)

    for cell in cells_sorted:
        if cell in used:
            continue

        row, col = cell

        # Try to extend horizontally first (single row range)
        end_col = col
        while (row, end_col + 1) in cells_set and (row, end_col + 1) not in used:
            end_col += 1

        # Try to extend vertically (single column range)
        end_row = row
        while (end_row + 1, col) in cells_set and (end_row + 1, col) not in used:
            end_row += 1

        # Decide: prefer horizontal if it captures more cells, else vertical
        horizontal_count = end_col - col + 1
        vertical_count = end_row - row + 1

        if horizontal_count >= vertical_count and horizontal_count > 1:
            # Use horizontal range
            for c in range(col, end_col + 1):
                used.add((row, c))
            ranges.append((row, row + 1, col, end_col + 1))
        elif vertical_count > 1:
            # Use vertical range
            for r in range(row, end_row + 1):
                used.add((r, col))
            ranges.append((row, end_row + 1, col, col + 1))
        else:
            # Single cell
            used.add(cell)
            ranges.append((row, row + 1, col, col + 1))

    return ranges


def compress_formulas(formulas: dict[str, str]) -> dict[str, str]:
    """Compress cell formulas by grouping equivalent relative patterns.

    Groups cells with the same relative reference pattern. Returns a unified
    dictionary where keys are either cell references (e.g., "A1") or ranges
    (e.g., "B2:K2"), and values are the formulas.

    For ranges, the stored formula is from the first cell. Non-contiguous cells
    with the same pattern are split into maximal contiguous sub-ranges.

    Args:
        formulas: Dict mapping A1 cell references to formula strings

    Returns:
        {"A1": "=UNIQUE(...)", "B2:K2": "=A2+B2", ...}
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
        return formulas.copy()

    # Group by normalized pattern
    pattern_cells: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for coord, (_formula, normalized) in cell_data.items():
        pattern_cells[normalized].append(coord)

    # Build output - unified format
    result: dict[str, str] = {}

    for _pattern, cells in pattern_cells.items():
        cells_sorted = sorted(cells)

        # Find all maximal contiguous ranges
        contiguous_ranges = _find_contiguous_ranges(cells_sorted)

        for start_row, end_row, start_col, end_col in contiguous_ranges:
            range_a1 = _range_to_a1(start_row, end_row, start_col, end_col)
            # Use the actual formula from the first cell of this range
            first_cell_formula = cell_data[(start_row, start_col)][0]
            result[range_a1] = first_cell_formula

    return result


def expand_formulas(compressed: dict[str, str]) -> dict[str, str]:
    """Expand compressed formulas back to per-cell representation.

    This is the inverse of compress_formulas. Accepts the unified format
    where keys are either cell references or ranges.

    Args:
        compressed: Dict with cell/range keys and formula values

    Returns:
        Dict mapping individual cell references to formulas
    """
    result: dict[str, str] = {}

    for key, formula in compressed.items():
        if ":" in key:
            # It's a range - expand it
            start, end = key.split(":")
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
            # Single cell reference
            result[key] = formula

    return result
