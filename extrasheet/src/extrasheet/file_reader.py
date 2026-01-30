"""Read current files from disk for diff comparison."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - used at runtime

from extrasheet.exceptions import InvalidFileError


def read_current_files(folder: Path) -> dict[str, str]:
    """Read all relevant files from the current folder.

    Args:
        folder: Path to the spreadsheet folder

    Returns:
        Dictionary mapping relative paths to file contents as strings.
        Only includes files relevant for diffing (.tsv, .json).

    Raises:
        InvalidFileError: If a required file is missing or invalid
    """
    result: dict[str, str] = {}

    # Read spreadsheet.json (required)
    spreadsheet_json = folder / "spreadsheet.json"
    if not spreadsheet_json.exists():
        raise InvalidFileError(str(spreadsheet_json), "File not found")
    result["spreadsheet.json"] = spreadsheet_json.read_text(encoding="utf-8")

    # Read optional root-level files
    for filename in ["theme.json", "named_ranges.json"]:
        file_path = folder / filename
        if file_path.exists():
            result[filename] = file_path.read_text(encoding="utf-8")

    # Read sheet folders
    try:
        spreadsheet_meta = json.loads(result["spreadsheet.json"])
    except json.JSONDecodeError as e:
        raise InvalidFileError(str(spreadsheet_json), f"Invalid JSON: {e}") from e

    for sheet in spreadsheet_meta.get("sheets", []):
        sheet_folder_name = sheet.get("folder")
        if not sheet_folder_name:
            continue

        sheet_dir = folder / sheet_folder_name
        if not sheet_dir.exists():
            continue

        # Read all files in sheet folder
        # Include both legacy feature.json and new split feature files
        for filename in [
            "data.tsv",
            "formula.json",
            "format.json",
            "feature.json",  # Legacy format, kept for backward compatibility
            "dimension.json",
            # New split feature files
            "charts.json",
            "pivot-tables.json",
            "tables.json",
            "filters.json",
            "banded-ranges.json",
            "data-validation.json",
            "slicers.json",
            "data-source-tables.json",
        ]:
            file_path = sheet_dir / filename
            if file_path.exists():
                relative_path = f"{sheet_folder_name}/{filename}"
                result[relative_path] = file_path.read_text(encoding="utf-8")

    return result


def get_current_file(current_files: dict[str, str], path: str) -> str | None:
    """Get a file from current files dict.

    Args:
        current_files: Dict from read_current_files()
        path: Relative path to the file

    Returns:
        File contents as string, or None if not found
    """
    return current_files.get(path)


def parse_tsv(content: str) -> list[list[str]]:
    """Parse TSV content into a 2D grid.

    Handles escaped characters (\\t, \\n, \\r, \\\\).

    Args:
        content: TSV file content

    Returns:
        2D list of cell values
    """
    if not content or not content.strip():
        return []

    lines = content.rstrip("\n").split("\n")
    grid: list[list[str]] = []

    for line in lines:
        cells = line.split("\t")
        # Unescape values
        unescaped = [_unescape_tsv_value(cell) for cell in cells]
        grid.append(unescaped)

    return grid


def _unescape_tsv_value(value: str) -> str:
    """Unescape a TSV value."""
    result: list[str] = []
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
