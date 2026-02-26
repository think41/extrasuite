"""SheetsClient - Main API for extrasheet.

Provides the `pull`, `diff`, and `push` methods for the pull-edit-diff-push workflow.
"""

from __future__ import annotations

import json
import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from extrasheet.comments import (
    CommentOperations,
    diff_comments,
    group_comments_by_sheet,
)
from extrasheet.diff import DiffResult, diff
from extrasheet.pristine import extract_pristine, get_pristine_file
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

logger = logging.getLogger(__name__)

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

        # Step 6: Fetch and write per-sheet comments (via Drive API)
        comment_files = await self._fetch_and_write_comments(
            writer, spreadsheet_id, files
        )
        written.extend(comment_files)

        # Step 7: Create pristine copy for diff/push workflow
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

    async def _fetch_and_write_comments(
        self,
        writer: FileWriter,
        spreadsheet_id: str,
        files: dict[str, Any],
    ) -> list[Path]:
        """Fetch comments from Drive API and write per-sheet comments.json files.

        Groups comments by sheet using the anchor's sheet ID, then writes
        a comments.json file for each sheet that has at least one comment.
        Sheets without comments get no file (not even an empty one).

        Args:
            writer: FileWriter for writing files to disk
            spreadsheet_id: The spreadsheet identifier
            files: Transformed files dict (contains spreadsheet.json for sheet mapping)
            output_path: Base output path

        Returns:
            List of paths to written comments.json files
        """
        try:
            comments_raw = await self._transport.list_comments(spreadsheet_id)
        except Exception as e:
            logger.warning("Failed to fetch comments: %s", e)
            return []

        if not comments_raw:
            return []

        # Build sheet_id → folder mapping from spreadsheet.json
        spreadsheet_json = files.get(f"{spreadsheet_id}/spreadsheet.json", {})
        if not isinstance(spreadsheet_json, dict):
            return []

        sheet_id_to_folder: dict[int, str] = {
            s["sheetId"]: s["folder"]
            for s in spreadsheet_json.get("sheets", [])
            if "sheetId" in s and "folder" in s
        }

        if not sheet_id_to_folder:
            return []

        # Group comments by sheet and convert to comments.json format
        per_sheet = group_comments_by_sheet(
            comments_raw, spreadsheet_id, sheet_id_to_folder
        )

        written: list[Path] = []
        for sheet_folder, comments_data in per_sheet.items():
            rel_path = f"{spreadsheet_id}/{sheet_folder}/comments.json"
            path = writer.write_json(rel_path, comments_data)
            written.append(path)

        return written

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
    ) -> tuple[DiffResult, list[dict[str, Any]], ValidationResult, dict[str, CommentOperations]]:
        """Compare current files against pristine and generate batchUpdate requests.

        This is a dry-run operation that doesn't make any API calls.

        Args:
            folder: Path to the spreadsheet folder (containing spreadsheet.json)

        Returns:
            Tuple of:
            - DiffResult: Detected changes by sheet
            - list[dict]: batchUpdate requests for sheet data changes
            - ValidationResult: Blocks (hard errors) and warnings
            - dict[str, CommentOperations]: Per-sheet comment operations
              (keyed by sheet folder name)

        Raises:
            MissingPristineError: If .pristine/spreadsheet.zip doesn't exist
            InvalidFileError: If files are corrupted

        Example:
            >>> diff_result, requests, validation, comment_ops = client.diff("./id")
            >>> if not validation.can_push:
            ...     print("Blocked:", validation.blocks)
            >>> print(f"Found {len(requests)} data changes")
        """
        folder = Path(folder)

        # Run structural validation first
        validation = validate_structural_changes(folder)

        # Generate diff and requests (even if blocked, for dry-run display)
        diff_result = diff(folder)
        requests = generate_requests(diff_result)

        # Compute per-sheet comment operations
        per_sheet_comment_ops = _diff_all_comments(folder)

        return diff_result, requests, validation, per_sheet_comment_ops

    async def push(self, folder: str | Path, *, force: bool = False) -> PushResult:
        """Apply changes to Google Sheets.

        Compares current files against pristine, generates batchUpdate requests,
        and sends them to the Google Sheets API.

        For new sheets, uses two-phase push:
        1. Execute addSheet requests first
        2. Update local files with Google-assigned sheetIds
        3. Execute remaining requests with correct sheetIds

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
        diff_result, requests, validation, per_sheet_comment_ops = self.diff(folder)

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

        has_comment_ops = any(
            ops.has_operations for ops in per_sheet_comment_ops.values()
        )

        if not requests and not has_comment_ops:
            return PushResult(
                success=True,
                changes_applied=0,
                message="No changes to apply",
                spreadsheet_id=diff_result.spreadsheet_id,
            )

        # Separate structural requests (addSheet/deleteSheet) from content requests
        structural_requests, content_requests = _separate_structural_requests(requests)

        total_applied = 0
        final_response: dict[str, Any] | None = None

        # Phase 1: Execute structural requests if any
        if structural_requests:
            response = await self._transport.batch_update(
                diff_result.spreadsheet_id, structural_requests
            )
            total_applied += len(structural_requests)
            final_response = response

            # Check if we created new sheets - need to update local sheetIds
            sheet_id_mapping = _extract_sheet_id_mapping(
                structural_requests, response.get("replies", [])
            )

            if sheet_id_mapping:
                # Update local spreadsheet.json with actual sheetIds
                _update_local_sheet_ids(folder, sheet_id_mapping)

                # Remap sheetIds in content requests
                content_requests = _remap_sheet_ids(content_requests, sheet_id_mapping)

        # Phase 2: Execute content requests if any
        if content_requests:
            response = await self._transport.batch_update(
                diff_result.spreadsheet_id, content_requests
            )
            total_applied += len(content_requests)
            final_response = response

        # Phase 3: Execute comment operations via Drive API
        replies_created = 0
        comments_resolved = 0

        for sheet_folder, ops in per_sheet_comment_ops.items():  # noqa: B007
            if not ops.has_operations:
                continue

            for new_reply in ops.new_replies:
                await self._transport.create_reply(
                    diff_result.spreadsheet_id,
                    new_reply.comment_id,
                    new_reply.content,
                )
                replies_created += 1

            for resolve in ops.resolves:
                await self._transport.create_reply(
                    diff_result.spreadsheet_id,
                    resolve.comment_id,
                    "",
                    action="resolve",
                )
                comments_resolved += 1

        comment_summary_parts: list[str] = []
        if replies_created:
            comment_summary_parts.append(f"{replies_created} reply/replies created")
        if comments_resolved:
            comment_summary_parts.append(f"{comments_resolved} comment(s) resolved")

        parts: list[str] = []
        if total_applied:
            parts.append(f"Applied {total_applied} changes")
        if comment_summary_parts:
            parts.extend(comment_summary_parts)

        message = ", ".join(parts) if parts else "No changes to apply"

        return PushResult(
            success=True,
            changes_applied=total_applied,
            message=message,
            spreadsheet_id=diff_result.spreadsheet_id,
            response=final_response,
        )


def _diff_all_comments(folder: Path) -> dict[str, CommentOperations]:
    """Compute per-sheet comment operations by comparing pristine vs current comments.json.

    Args:
        folder: Path to the spreadsheet folder

    Returns:
        Dict mapping sheet_folder -> CommentOperations.
        Only includes sheets where changes were detected.
    """
    # Load spreadsheet.json to get sheet info (id → folder mapping)
    spreadsheet_json_path = folder / "spreadsheet.json"
    if not spreadsheet_json_path.exists():
        return {}

    with spreadsheet_json_path.open() as f:
        spreadsheet_data = json.load(f)

    folder_to_sheet_id: dict[str, int] = {}
    for sheet in spreadsheet_data.get("sheets", []):
        sheet_folder = sheet.get("folder", "")
        sheet_id = sheet.get("sheetId")
        if sheet_folder and sheet_id is not None:
            folder_to_sheet_id[sheet_folder] = sheet_id

    if not folder_to_sheet_id:
        return {}

    # Extract pristine files to compare against
    try:
        pristine_files = extract_pristine(folder)
    except Exception:
        return {}

    result: dict[str, CommentOperations] = {}

    for sheet_folder in folder_to_sheet_id:
        current_path = folder / sheet_folder / "comments.json"
        pristine_key = f"{sheet_folder}/comments.json"

        current_json: str | None = None
        if current_path.exists():
            current_json = current_path.read_text(encoding="utf-8")

        pristine_json = get_pristine_file(pristine_files, pristine_key)

        if pristine_json is None and current_json is None:
            continue

        if current_json is not None:
            ops = diff_comments(pristine_json, current_json)
            if ops.has_operations:
                result[sheet_folder] = ops

    return result


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


def _separate_structural_requests(
    requests: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate structural requests (addSheet/deleteSheet) from content requests.

    Structural requests must execute first to ensure sheetIds are available
    for content requests.

    Returns:
        Tuple of (structural_requests, content_requests)
    """
    structural_requests: list[dict[str, Any]] = []
    content_requests: list[dict[str, Any]] = []

    for request in requests:
        if "addSheet" in request or "deleteSheet" in request:
            structural_requests.append(request)
        else:
            content_requests.append(request)

    return structural_requests, content_requests


def _extract_sheet_id_mapping(
    structural_requests: list[dict[str, Any]],
    replies: list[dict[str, Any]],
) -> dict[int, int]:
    """Extract mapping from local sheetIds to Google-assigned sheetIds.

    Args:
        structural_requests: The addSheet/deleteSheet requests that were sent
        replies: The API replies (one per request)

    Returns:
        Dict mapping local sheetId -> actual sheetId (only for new sheets)
    """
    mapping: dict[int, int] = {}

    for i, request in enumerate(structural_requests):
        if "addSheet" in request and i < len(replies):
            reply = replies[i]
            if "addSheet" in reply:
                # Get the local sheetId from the request
                local_sheet_id = request["addSheet"]["properties"].get("sheetId")
                # Get the actual sheetId from the reply
                actual_sheet_id = reply["addSheet"].get("properties", {}).get("sheetId")

                if (
                    local_sheet_id is not None
                    and actual_sheet_id is not None
                    and local_sheet_id != actual_sheet_id
                ):
                    mapping[local_sheet_id] = actual_sheet_id

    return mapping


def _update_local_sheet_ids(folder: Path, sheet_id_mapping: dict[int, int]) -> None:
    """Update local spreadsheet.json with Google-assigned sheetIds.

    Args:
        folder: Path to the spreadsheet folder
        sheet_id_mapping: Dict mapping local sheetId -> actual sheetId
    """
    spreadsheet_json_path = folder / "spreadsheet.json"

    if not spreadsheet_json_path.exists():
        return

    with spreadsheet_json_path.open() as f:
        spreadsheet_data = json.load(f)

    # Update sheetIds in the sheets list
    for sheet in spreadsheet_data.get("sheets", []):
        old_id = sheet.get("sheetId")
        if old_id in sheet_id_mapping:
            sheet["sheetId"] = sheet_id_mapping[old_id]

    # Write back
    with spreadsheet_json_path.open("w") as f:
        json.dump(spreadsheet_data, f, indent=2)

    # Also update the pristine copy to keep it in sync
    _update_pristine_sheet_ids(folder, sheet_id_mapping)


def _update_pristine_sheet_ids(folder: Path, sheet_id_mapping: dict[int, int]) -> None:
    """Update the pristine spreadsheet.zip with Google-assigned sheetIds.

    This keeps the pristine copy in sync after structural changes (addSheet)
    so that subsequent diffs don't see a mismatch between pristine and current.

    Args:
        folder: Path to the spreadsheet folder
        sheet_id_mapping: Dict mapping local sheetId -> actual sheetId
    """
    pristine_zip_path = folder / ".pristine" / "spreadsheet.zip"

    if not pristine_zip_path.exists():
        return

    # Read the existing zip contents
    with zipfile.ZipFile(pristine_zip_path, "r") as zf:
        # Extract all files to memory
        files_content: dict[str, bytes] = {}
        for name in zf.namelist():
            if not name.endswith("/"):  # Skip directories
                files_content[name] = zf.read(name)

    # Update spreadsheet.json in the extracted contents
    if "spreadsheet.json" in files_content:
        spreadsheet_data = json.loads(files_content["spreadsheet.json"].decode("utf-8"))

        # Update sheetIds in the sheets list
        for sheet in spreadsheet_data.get("sheets", []):
            old_id = sheet.get("sheetId")
            if old_id in sheet_id_mapping:
                sheet["sheetId"] = sheet_id_mapping[old_id]

        files_content["spreadsheet.json"] = json.dumps(
            spreadsheet_data, indent=2
        ).encode("utf-8")

    # Write the updated zip
    with zipfile.ZipFile(pristine_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files_content.items():
            zf.writestr(name, content)


def _remap_sheet_ids(
    requests: list[dict[str, Any]], sheet_id_mapping: dict[int, int]
) -> list[dict[str, Any]]:
    """Recursively remap sheetIds in requests using the mapping.

    Args:
        requests: List of batchUpdate requests
        sheet_id_mapping: Dict mapping local sheetId -> actual sheetId

    Returns:
        New list of requests with sheetIds remapped
    """
    return [_remap_sheet_ids_in_obj(req, sheet_id_mapping) for req in requests]


def _remap_sheet_ids_in_obj(obj: Any, mapping: dict[int, int]) -> Any:
    """Recursively remap sheetId values in an object."""
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key == "sheetId" and isinstance(value, int) and value in mapping:
                result[key] = mapping[value]
            else:
                result[key] = _remap_sheet_ids_in_obj(value, mapping)
        return result
    elif isinstance(obj, list):
        return [_remap_sheet_ids_in_obj(item, mapping) for item in obj]
    else:
        return obj
