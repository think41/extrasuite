"""
Utility functions for extrasheet.

Provides coordinate conversion, filename sanitization, and other helpers.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from extrasheet.api_types import GridRange


def column_index_to_letter(index: int) -> str:
    """Convert a zero-based column index to A1 notation letter(s).

    Examples:
        0 -> A, 1 -> B, 25 -> Z, 26 -> AA, 27 -> AB, 702 -> AAA
    """
    result = ""
    while True:
        result = chr(ord("A") + (index % 26)) + result
        index = index // 26 - 1
        if index < 0:
            break
    return result


def letter_to_column_index(letter: str) -> int:
    """Convert A1 notation letter(s) to a zero-based column index.

    Examples:
        A -> 0, B -> 1, Z -> 25, AA -> 26, AB -> 27, AAA -> 702
    """
    result = 0
    for char in letter.upper():
        result = result * 26 + (ord(char) - ord("A") + 1)
    return result - 1


def cell_to_a1(row_index: int, col_index: int) -> str:
    """Convert zero-based row and column indices to A1 notation.

    Examples:
        (0, 0) -> A1, (0, 1) -> B1, (9, 2) -> C10
    """
    return f"{column_index_to_letter(col_index)}{row_index + 1}"


def a1_to_cell(a1: str) -> tuple[int, int]:
    """Convert A1 notation to zero-based (row_index, col_index).

    Examples:
        A1 -> (0, 0), B1 -> (0, 1), C10 -> (9, 2)
    """
    match = re.match(r"^([A-Za-z]+)(\d+)$", a1)
    if not match:
        raise ValueError(f"Invalid A1 notation: {a1}")
    col_letter, row_str = match.groups()
    return int(row_str) - 1, letter_to_column_index(col_letter)


def range_to_a1(
    start_row: int | None,
    end_row: int | None,
    start_col: int | None,
    end_col: int | None,
) -> str:
    """Convert zero-based range indices to A1 notation.

    Handles unbounded ranges (None values).

    Examples:
        (0, 10, 0, 5) -> A1:E10
        (0, None, 0, 1) -> A:A (full column)
        (0, 1, None, None) -> 1:1 (full row)
    """
    # Full column(s)
    if (
        start_row is None
        and end_row is None
        and start_col is not None
        and end_col is not None
    ):
        if end_col - start_col == 1:
            return f"{column_index_to_letter(start_col)}:{column_index_to_letter(start_col)}"
        return (
            f"{column_index_to_letter(start_col)}:{column_index_to_letter(end_col - 1)}"
        )

    # Full row(s)
    if (
        start_col is None
        and end_col is None
        and start_row is not None
        and end_row is not None
    ):
        if end_row - start_row == 1:
            return f"{start_row + 1}:{start_row + 1}"
        return f"{start_row + 1}:{end_row}"

    # Standard range
    if start_row is not None and start_col is not None:
        start_a1 = cell_to_a1(start_row, start_col)
        if end_row is not None and end_col is not None:
            # Single cell
            if end_row - start_row == 1 and end_col - start_col == 1:
                return start_a1
            end_a1 = cell_to_a1(end_row - 1, end_col - 1)
            return f"{start_a1}:{end_a1}"
        return start_a1

    return ""


def grid_range_to_a1(grid_range: GridRange) -> str:
    """Convert a GridRange object to A1 notation."""
    return range_to_a1(
        grid_range.get("startRowIndex"),
        grid_range.get("endRowIndex"),
        grid_range.get("startColumnIndex"),
        grid_range.get("endColumnIndex"),
    )


def a1_range_to_grid_range(a1_range: str, sheet_id: int = 0) -> dict[str, int]:
    """Convert A1 notation range to GridRange dict.

    Args:
        a1_range: A1 notation range like "A1:B5" or single cell "C3"
        sheet_id: The sheet ID to include in the result

    Returns:
        GridRange dict with sheetId, startRowIndex, endRowIndex,
        startColumnIndex, endColumnIndex
    """
    if ":" in a1_range:
        start, end = a1_range.split(":")
        start_row, start_col = a1_to_cell(start)
        end_row, end_col = a1_to_cell(end)
    else:
        start_row, start_col = a1_to_cell(a1_range)
        end_row, end_col = start_row, start_col

    return {
        "sheetId": sheet_id,
        "startRowIndex": start_row,
        "endRowIndex": end_row + 1,  # endRowIndex is exclusive
        "startColumnIndex": start_col,
        "endColumnIndex": end_col + 1,  # endColumnIndex is exclusive
    }


def sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename.

    Replaces invalid characters with underscores and trims whitespace.
    """
    # Characters invalid in Windows/Unix filenames
    invalid_chars = r'[/\\:*?"<>|]'
    sanitized = re.sub(invalid_chars, "_", name)
    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip(" .")
    # Collapse multiple underscores
    sanitized = re.sub(r"_+", "_", sanitized)
    return sanitized or "unnamed"


def escape_tsv_value(value: str) -> str:
    """Escape a value for TSV format.

    Escapes tabs, newlines, and backslashes.
    """
    return (
        value.replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def unescape_tsv_value(value: str) -> str:
    """Unescape a TSV value."""
    result = []
    i = 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            next_char = value[i + 1]
            if next_char == "t":
                result.append("\t")
            elif next_char == "n":
                result.append("\n")
            elif next_char == "r":
                result.append("\r")
            elif next_char == "\\":
                result.append("\\")
            else:
                result.append(value[i : i + 2])
            i += 2
        else:
            result.append(value[i])
            i += 1
    return "".join(result)


def format_json_number(value: float) -> str | float | int:
    """Format a number for JSON, converting integers to int type.

    This prevents numbers like 1.0 from appearing in JSON output.
    """
    if value == int(value):
        return int(value)
    return value


def get_effective_value_string(
    cell_data: dict,
    formatted_value: str | None = None,
) -> str:
    """Extract the display value from a CellData object.

    Prefers formattedValue, falls back to effectiveValue.

    Args:
        cell_data: CellData dictionary from Google Sheets API
        formatted_value: Pre-extracted formatted value (optimization)

    Returns:
        String representation of the cell value
    """
    # Prefer formatted value (human-readable)
    if formatted_value is not None:
        return formatted_value

    fv = cell_data.get("formattedValue")
    if fv is not None:
        return str(fv)

    # Fall back to effective value
    ev = cell_data.get("effectiveValue", {})
    if not ev:
        return ""

    if "stringValue" in ev:
        return ev["stringValue"]
    elif "numberValue" in ev:
        return str(ev["numberValue"])
    elif "boolValue" in ev:
        return "TRUE" if ev["boolValue"] else "FALSE"
    elif "errorValue" in ev:
        error = ev["errorValue"]
        return error.get("message", "#ERROR!")
    elif "formulaValue" in ev:
        # Should not happen (formulas have effectiveValue)
        return ev["formulaValue"]

    return ""


def is_default_cell_format(
    cell_format: dict, default_format: dict | None = None
) -> bool:
    """Check if a cell format is the default (no customization).

    Args:
        cell_format: CellFormat dictionary
        default_format: Default format to compare against

    Returns:
        True if the format matches the default or is empty
    """
    if not cell_format:
        return True

    # If we have a default to compare against
    if default_format:
        return cell_format == default_format

    # Common default values - if only these are present, consider it default
    default_keys = {"wrapStrategy", "verticalAlignment", "horizontalAlignment"}
    non_default_keys = set(cell_format.keys()) - default_keys

    return len(non_default_keys) == 0


def is_default_dimension(dimension: dict, is_row: bool = True) -> bool:
    """Check if a dimension (row/column) has default properties.

    Args:
        dimension: DimensionProperties dictionary
        is_row: True if this is a row, False for column

    Returns:
        True if the dimension matches defaults
    """
    if not dimension:
        return True

    # Default sizes
    default_row_size = 21
    default_col_size = 100

    pixel_size = dimension.get("pixelSize")
    expected_default = default_row_size if is_row else default_col_size

    # Hidden rows/columns are never default
    if dimension.get("hidden"):
        return False

    # Check if size matches default (or is close enough)
    if pixel_size is not None and abs(pixel_size - expected_default) > 1:
        return False

    # Check for developer metadata
    return not dimension.get("developerMetadata")
