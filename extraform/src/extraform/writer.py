"""File writer for ExtraForm."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FileWriter:
    """Writes form files to disk."""

    def __init__(self, output_dir: Path) -> None:
        """Initialize the file writer.

        Args:
            output_dir: The directory to write files to.
        """
        self._output_dir = output_dir

    def write_all(self, files: dict[str, Any]) -> list[Path]:
        """Write all files to disk.

        Args:
            files: Dictionary mapping relative paths to file contents.
                   Contents can be strings (written as-is) or dicts (written as JSON).

        Returns:
            List of absolute paths to written files.
        """
        written: list[Path] = []

        for rel_path, content in files.items():
            path = self._output_dir / rel_path

            # Create parent directories
            path.parent.mkdir(parents=True, exist_ok=True)

            # Write content based on type
            if isinstance(content, dict):
                self._write_json(path, content)
            else:
                self._write_text(path, str(content))

            written.append(path)

        return written

    def _write_json(self, path: Path, content: dict[str, Any]) -> None:
        """Write JSON content to a file.

        Args:
            path: The file path.
            content: The JSON-serializable content.
        """
        path.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n")

    def _write_text(self, path: Path, content: str) -> None:
        """Write text content to a file.

        Args:
            path: The file path.
            content: The text content.
        """
        path.write_text(content)

    def write_raw(self, filename: str, content: dict[str, Any]) -> Path:
        """Write a raw API response to the .raw directory.

        Args:
            filename: The filename (e.g., "form.json").
            content: The raw API response.

        Returns:
            The absolute path to the written file.
        """
        raw_dir = self._output_dir / ".raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        path = raw_dir / filename
        self._write_json(path, content)

        return path
