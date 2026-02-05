"""File reader for ExtraForm."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from extraform.exceptions import InvalidFileError


def read_current_files(folder: Path) -> dict[str, Any]:
    """Read current form files from a folder.

    Args:
        folder: The form folder to read from.

    Returns:
        Dictionary mapping file paths to their contents.
        - "form.json": The form structure as a dict.
        - "responses.tsv": Optional responses as string (if exists).

    Raises:
        InvalidFileError: If required files are missing or invalid.
    """
    files: dict[str, Any] = {}

    # Read form.json (required)
    form_path = folder / "form.json"
    if not form_path.exists():
        raise InvalidFileError(str(form_path), "form.json not found")

    try:
        files["form.json"] = json.loads(form_path.read_text())
    except json.JSONDecodeError as e:
        raise InvalidFileError(str(form_path), f"Invalid JSON: {e}") from e

    # Read responses.tsv (optional)
    responses_path = folder / "responses.tsv"
    if responses_path.exists():
        files["responses.tsv"] = responses_path.read_text()

    return files


def read_form_json(folder: Path) -> dict[str, Any]:
    """Read and parse form.json from a folder.

    Args:
        folder: The form folder.

    Returns:
        The parsed form data.

    Raises:
        InvalidFileError: If form.json is missing or invalid.
    """
    form_path = folder / "form.json"
    if not form_path.exists():
        raise InvalidFileError(str(form_path), "form.json not found")

    try:
        return json.loads(form_path.read_text())  # type: ignore[no-any-return]
    except json.JSONDecodeError as e:
        raise InvalidFileError(str(form_path), f"Invalid JSON: {e}") from e
