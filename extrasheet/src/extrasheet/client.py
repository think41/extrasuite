"""SheetsClient - Main API for extrasheet.

Provides the `pull`, `diff`, and `push` methods for the pull-edit-diff-push workflow.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from extrasheet.diff import DiffResult, diff
from extrasheet.request_generator import generate_requests
from extrasheet.structural_validation import (
    ValidationResult,
    validate_structural_changes,
)
from extrasheet.transformer import SpreadsheetTransformer
from extrasheet.transport import (
    APIError,
    AuthenticationError,
    NotFoundError,
    SpreadsheetData,
    SpreadsheetMetadata,
    Transport,
    TransportError,
)
from extrasheet.writer import FileWriter

# Re-export exceptions for backwards compatibility
__all__ = [
    "APIError",
    "AuthenticationError",
    "NotFoundError",
    "PushResult",
    "SheetsClient",
    "TransportError",
]


@dataclass
class PushResult:
    """Result of a push operation."""

    success: bool
    changes_applied: int
    message: str
    spreadsheet_id: str
    response: dict[str, Any] | None = None


class SheetsClient:
    """Client for transforming Google Sheets to file representation.

    This client pulls spreadsheet data via a Transport and transforms it
    into a file-based representation optimized for LLM agents.

    Example:
        >>> from extrasheet.transport import GoogleSheetsTransport
        >>> transport = GoogleSheetsTransport(access_token="ya29...")
        >>> client = SheetsClient(transport)
        >>> await client.pull("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", "./output")
    """

    def __init__(self, transport: Transport) -> None:
        """Initialize the client.

        Args:
            transport: Transport implementation for fetching spreadsheet data
        """
        self._transport = transport

    async def pull(
        self,
        spreadsheet_id: str,
        output_path: str | Path,
        *,
        max_rows: int = 100,
        save_raw: bool = True,
    ) -> list[Path]:
        """Pull a spreadsheet and write to file representation.

        This is the main entry point for transforming a Google Sheet
        into the extrasheet file format.

        Always performs two fetches:
        1. Metadata fetch - gets sheet names and dimensions
        2. Data fetch - gets cell contents with row limits applied

        Args:
            spreadsheet_id: The ID of the spreadsheet (from the URL)
            output_path: Directory to write files to
            max_rows: Maximum number of rows to fetch per sheet (default: 100)
            save_raw: If True, saves raw API responses to .raw/ folder (default: True)

        Returns:
            List of paths to written files

        Example:
            >>> files = await client.pull(
            ...     "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
            ...     "./output",
            ...     max_rows=500,
            ... )
            >>> print(f"Wrote {len(files)} files")
        """
        # Step 1: Fetch metadata
        metadata = await self._transport.get_metadata(spreadsheet_id)

        # Step 2: Fetch data with row limits
        spreadsheet_data = await self._transport.get_data(
            spreadsheet_id, metadata, max_rows
        )

        # Step 3: Transform to file representation
        truncation_dict = _truncation_info_to_dict(spreadsheet_data)
        # Cast to Spreadsheet TypedDict for transformer
        transformer = SpreadsheetTransformer(
            spreadsheet_data.data,  # type: ignore[arg-type]
            truncation_info=truncation_dict,
        )
        files = transformer.transform()

        # Step 4: Write to disk
        writer = FileWriter(output_path)
        written = writer.write_all(files)

        # Step 5: Save raw API responses
        if save_raw:
            raw_files = self._save_raw_responses(
                writer, spreadsheet_id, metadata, spreadsheet_data
            )
            written.extend(raw_files)

        # Step 6: Create pristine copy for diff/push workflow
        pristine_path = self._create_pristine_copy(output_path, spreadsheet_id, written)
        written.append(pristine_path)

        return written

    def _save_raw_responses(
        self,
        writer: FileWriter,
        spreadsheet_id: str,
        metadata: SpreadsheetMetadata,
        spreadsheet_data: SpreadsheetData,
    ) -> list[Path]:
        """Save raw API responses to .raw/ folder."""
        raw_paths: list[Path] = []

        # Save metadata response
        metadata_path = writer.write_json(
            f"{spreadsheet_id}/.raw/metadata.json", metadata.raw
        )
        raw_paths.append(metadata_path)

        # Save data response
        data_path = writer.write_json(
            f"{spreadsheet_id}/.raw/data.json", spreadsheet_data.data
        )
        raw_paths.append(data_path)

        return raw_paths

    def _create_pristine_copy(
        self,
        output_path: str | Path,
        spreadsheet_id: str,
        written_files: list[Path],
    ) -> Path:
        """Create a pristine copy of the pulled files for diff/push workflow.

        Creates a .pristine/ directory containing a spreadsheet.zip file
        with all the pulled files (excluding .raw/). This zip is used by
        diff/push to compare against the current state.
        """
        output_path = Path(output_path)
        spreadsheet_dir = output_path / spreadsheet_id
        pristine_dir = spreadsheet_dir / ".pristine"
        pristine_dir.mkdir(parents=True, exist_ok=True)

        zip_path = pristine_dir / "spreadsheet.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in written_files:
                # Skip .raw/ files - not part of canonical representation
                if ".raw" in file_path.parts:
                    continue
                # Store with path relative to spreadsheet directory
                arcname = file_path.relative_to(spreadsheet_dir)
                zf.write(file_path, arcname)

        return zip_path

    def diff(
        self, folder: str | Path
    ) -> tuple[DiffResult, list[dict[str, Any]], ValidationResult]:
        """Compare current files against pristine and generate batchUpdate requests.

        This is a dry-run operation that doesn't make any API calls.

        Args:
            folder: Path to the spreadsheet folder (containing spreadsheet.json)

        Returns:
            Tuple of (DiffResult, list of batchUpdate requests, ValidationResult)
            The ValidationResult contains blocks (hard errors) and warnings.

        Raises:
            MissingPristineError: If .pristine/spreadsheet.zip doesn't exist
            InvalidFileError: If files are corrupted

        Example:
            >>> diff_result, requests, validation = client.diff("./my_spreadsheet_id")
            >>> if not validation.can_push:
            ...     print("Blocked:", validation.blocks)
            >>> print(f"Found {len(requests)} changes")
        """
        folder = Path(folder)

        # Run structural validation first
        validation = validate_structural_changes(folder)

        # Generate diff and requests (even if blocked, for dry-run display)
        diff_result = diff(folder)
        requests = generate_requests(diff_result)

        return diff_result, requests, validation

    async def push(self, folder: str | Path, *, force: bool = False) -> PushResult:
        """Apply changes to Google Sheets.

        Compares current files against pristine, generates batchUpdate requests,
        and sends them to the Google Sheets API.

        Args:
            folder: Path to the spreadsheet folder (containing spreadsheet.json)
            force: If True, proceed despite warnings (blocks still stop push)

        Returns:
            PushResult with success status and details

        Raises:
            MissingPristineError: If .pristine/spreadsheet.zip doesn't exist
            InvalidFileError: If files are corrupted
            APIError: If the API call fails

        Example:
            >>> result = await client.push("./my_spreadsheet_id")
            >>> if result.success:
            ...     print(f"Applied {result.changes_applied} changes")
        """
        folder = Path(folder)

        # Generate diff, requests, and validation
        diff_result, requests, validation = self.diff(folder)

        # Check for blocking errors
        if not validation.can_push:
            return PushResult(
                success=False,
                changes_applied=0,
                message="Push blocked due to validation errors:\n"
                + "\n".join(f"  - {b}" for b in validation.blocks),
                spreadsheet_id=diff_result.spreadsheet_id,
            )

        # Check for warnings (unless force is True)
        if validation.has_warnings and not force:
            return PushResult(
                success=False,
                changes_applied=0,
                message="Push blocked due to warnings (use --force to override):\n"
                + "\n".join(f"  - {w}" for w in validation.warnings),
                spreadsheet_id=diff_result.spreadsheet_id,
            )

        if not requests:
            return PushResult(
                success=True,
                changes_applied=0,
                message="No changes to apply",
                spreadsheet_id=diff_result.spreadsheet_id,
            )

        # Send batchUpdate to API
        response = await self._transport.batch_update(
            diff_result.spreadsheet_id, requests
        )

        return PushResult(
            success=True,
            changes_applied=len(requests),
            message=f"Applied {len(requests)} changes",
            spreadsheet_id=diff_result.spreadsheet_id,
            response=response,
        )


def _truncation_info_to_dict(
    spreadsheet_data: SpreadsheetData,
) -> dict[int, dict[str, int | bool]]:
    """Convert SpreadsheetData truncation info to dict format for transformer."""
    result: dict[int, dict[str, int | bool]] = {}
    for sheet_id, info in spreadsheet_data.truncation_info.items():
        result[sheet_id] = {
            "totalRows": info.total_rows,
            "fetchedRows": info.fetched_rows,
            "truncated": True,
        }
    return result
