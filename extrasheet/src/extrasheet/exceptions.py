"""Custom exceptions for extrasheet diff/push workflow."""

from __future__ import annotations


class DiffError(Exception):
    """Base exception for diff-related errors."""

    pass


class GridDimensionChangedError(DiffError):
    """Raised when grid dimensions differ between pristine and current.

    This occurs when rows or columns have been added or removed from data.tsv.
    Use the imperative workflow (extrasheet batchUpdate) for structural changes.
    """

    def __init__(
        self,
        sheet_name: str,
        pristine_rows: int,
        pristine_cols: int,
        current_rows: int,
        current_cols: int,
    ) -> None:
        self.sheet_name = sheet_name
        self.pristine_rows = pristine_rows
        self.pristine_cols = pristine_cols
        self.current_rows = current_rows
        self.current_cols = current_cols
        super().__init__(
            f"Grid dimensions changed in sheet '{sheet_name}': "
            f"{pristine_rows}x{pristine_cols} -> {current_rows}x{current_cols}. "
            "Use 'extrasheet batchUpdate' for structural changes (insert/delete rows/columns)."
        )


class MissingPristineError(DiffError):
    """Raised when .pristine/spreadsheet.zip is missing.

    The pristine copy is required for diff/push. Re-run 'extrasheet pull' to create it.
    """

    def __init__(self, folder: str) -> None:
        self.folder = folder
        super().__init__(
            f"Missing .pristine/spreadsheet.zip in '{folder}'. "
            "Run 'extrasheet pull' first to create the pristine copy."
        )


class InvalidFileError(DiffError):
    """Raised when a file is corrupted or has invalid format."""

    def __init__(self, file_path: str, reason: str) -> None:
        self.file_path = file_path
        self.reason = reason
        super().__init__(f"Invalid file '{file_path}': {reason}")


class MissingSpreadsheetIdError(DiffError):
    """Raised when spreadsheet ID cannot be determined."""

    def __init__(self, folder: str) -> None:
        self.folder = folder
        super().__init__(
            f"Cannot determine spreadsheet ID from folder '{folder}'. "
            "Ensure spreadsheet.json exists and contains spreadsheetId."
        )
