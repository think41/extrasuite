"""Extract and parse pristine copy from .pristine/spreadsheet.zip."""

from __future__ import annotations

import zipfile
from pathlib import Path  # noqa: TC003 - used at runtime

from extrasheet.exceptions import InvalidFileError, MissingPristineError


def extract_pristine(folder: Path) -> dict[str, str | bytes]:
    """Extract pristine files from .pristine/spreadsheet.zip.

    Args:
        folder: Path to the spreadsheet folder (containing .pristine/)

    Returns:
        Dictionary mapping relative paths to file contents.
        Text files (.tsv, .json) are returned as strings.
        Binary files are returned as bytes.

    Raises:
        MissingPristineError: If .pristine/spreadsheet.zip doesn't exist
        InvalidFileError: If the zip file is corrupted
    """
    pristine_zip = folder / ".pristine" / "spreadsheet.zip"

    if not pristine_zip.exists():
        raise MissingPristineError(str(folder))

    try:
        result: dict[str, str | bytes] = {}

        with zipfile.ZipFile(pristine_zip, "r") as zf:
            for name in zf.namelist():
                # Skip directories
                if name.endswith("/"):
                    continue

                content = zf.read(name)

                # Decode text files
                if name.endswith((".tsv", ".json")):
                    result[name] = content.decode("utf-8")
                else:
                    result[name] = content

        return result

    except zipfile.BadZipFile as e:
        raise InvalidFileError(str(pristine_zip), f"Corrupted zip file: {e}") from e
    except Exception as e:
        raise InvalidFileError(str(pristine_zip), str(e)) from e


def get_pristine_file(pristine_files: dict[str, str | bytes], path: str) -> str | None:
    """Get a text file from pristine files dict.

    Args:
        pristine_files: Dict from extract_pristine()
        path: Relative path to the file

    Returns:
        File contents as string, or None if not found
    """
    content = pristine_files.get(path)
    if content is None:
        return None
    if isinstance(content, bytes):
        return content.decode("utf-8")
    return content
