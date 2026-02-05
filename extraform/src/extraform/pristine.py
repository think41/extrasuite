"""Pristine copy handling for ExtraForm."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from extraform.exceptions import InvalidFileError, MissingPristineError

PRISTINE_FILENAME = "form.zip"


def create_pristine(folder: Path, files: dict[str, Any]) -> Path:
    """Create a pristine copy of the form files.

    Args:
        folder: The form folder.
        files: Dictionary of files to include (path -> content).

    Returns:
        Path to the created pristine zip file.
    """
    pristine_dir = folder / ".pristine"
    pristine_dir.mkdir(parents=True, exist_ok=True)

    zip_path = pristine_dir / PRISTINE_FILENAME

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path, content in files.items():
            # Skip .raw files from pristine
            if rel_path.startswith(".raw/"):
                continue

            # Convert content to string if needed
            if isinstance(content, dict):
                content_str = json.dumps(content, indent=2, ensure_ascii=False) + "\n"
            else:
                content_str = str(content)

            zf.writestr(rel_path, content_str)

    return zip_path


def extract_pristine(folder: Path) -> dict[str, str | bytes]:
    """Extract pristine copy from zip file.

    Args:
        folder: The form folder containing .pristine/form.zip.

    Returns:
        Dictionary mapping file paths to their contents.
        Text files (.json, .tsv) are decoded to strings.

    Raises:
        MissingPristineError: If pristine zip doesn't exist.
        InvalidFileError: If pristine zip is corrupted.
    """
    zip_path = folder / ".pristine" / PRISTINE_FILENAME

    if not zip_path.exists():
        raise MissingPristineError(str(folder))

    try:
        files: dict[str, str | bytes] = {}
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                content = zf.read(name)
                # Decode text files
                if name.endswith((".json", ".tsv")):
                    files[name] = content.decode("utf-8")
                else:
                    files[name] = content
        return files
    except zipfile.BadZipFile as e:
        raise InvalidFileError(str(zip_path), f"Corrupted zip file: {e}") from e


def get_pristine_form(folder: Path) -> dict[str, Any]:
    """Get the pristine form.json as a parsed dictionary.

    Args:
        folder: The form folder.

    Returns:
        The parsed pristine form data.

    Raises:
        MissingPristineError: If pristine doesn't exist.
        InvalidFileError: If form.json is invalid.
    """
    pristine_files = extract_pristine(folder)

    form_content = pristine_files.get("form.json")
    if form_content is None:
        raise InvalidFileError(
            str(folder / ".pristine" / PRISTINE_FILENAME),
            "Missing form.json in pristine archive",
        )

    if isinstance(form_content, bytes):
        form_content = form_content.decode("utf-8")

    try:
        return json.loads(form_content)  # type: ignore[no-any-return]
    except json.JSONDecodeError as e:
        raise InvalidFileError(
            str(folder / ".pristine" / PRISTINE_FILENAME),
            f"Invalid JSON in form.json: {e}",
        ) from e


def update_pristine(folder: Path, files: dict[str, Any]) -> Path:
    """Update the pristine copy with new files.

    This is used after a successful push to update the pristine
    copy to match the current state.

    Args:
        folder: The form folder.
        files: New files to store in pristine.

    Returns:
        Path to the updated pristine zip file.
    """
    return create_pristine(folder, files)
