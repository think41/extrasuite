"""
File writer utilities for extrasheet.

Handles writing the transformed representation to disk.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FileWriter:
    """Writes extrasheet file representation to disk."""

    def __init__(self, base_path: str | Path) -> None:
        """Initialize the writer with a base output path.

        Args:
            base_path: Directory to write files to
        """
        self.base_path = Path(base_path)

    def write_all(self, files: dict[str, Any]) -> list[Path]:
        """Write all files to disk.

        Args:
            files: Dictionary mapping relative paths to content.
                   String content is written as-is (TSV).
                   Dict content is written as JSON.

        Returns:
            List of paths that were written
        """
        written: list[Path] = []

        for rel_path, content in files.items():
            full_path = self.base_path / rel_path

            # Ensure parent directory exists
            full_path.parent.mkdir(parents=True, exist_ok=True)

            if isinstance(content, str):
                # Write as plain text (TSV)
                full_path.write_text(content, encoding="utf-8")
            else:
                # Write as JSON
                json_str = json.dumps(content, indent=2, ensure_ascii=False)
                full_path.write_text(json_str, encoding="utf-8")

            written.append(full_path)

        return written

    def write_tsv(self, rel_path: str, content: str) -> Path:
        """Write a TSV file.

        Args:
            rel_path: Relative path within base_path
            content: TSV content string

        Returns:
            Path to written file
        """
        full_path = self.base_path / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        return full_path

    def write_json(self, rel_path: str, content: dict[str, Any]) -> Path:
        """Write a JSON file.

        Args:
            rel_path: Relative path within base_path
            content: Dictionary to serialize as JSON

        Returns:
            Path to written file
        """
        full_path = self.base_path / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        json_str = json.dumps(content, indent=2, ensure_ascii=False)
        full_path.write_text(json_str, encoding="utf-8")
        return full_path
