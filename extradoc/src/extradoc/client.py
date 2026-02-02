"""Main client for Google Docs operations.

Provides the DocsClient class with pull(), diff(), and push() methods
implementing the core workflow for Google Docs manipulation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from extradoc.transport import Transport


@dataclass
class DiffResult:
    """Result of comparing current files against pristine state."""

    document_id: str
    has_changes: bool
    # Additional fields will be added when diff is implemented


@dataclass
class ValidationResult:
    """Result of validating changes before push."""

    can_push: bool
    blocks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PushResult:
    """Result of pushing changes to Google Docs."""

    success: bool
    document_id: str
    changes_applied: int
    message: str = ""


class DocsClient:
    """Client for Google Docs pull/diff/push operations.

    This is the main interface for working with Google Docs in the
    extradoc workflow. It handles:
    - Pulling documents to local file representation
    - Diffing local changes against the pristine state
    - Pushing changes back to Google Docs

    Example:
        from extradoc import DocsClient, GoogleDocsTransport

        transport = GoogleDocsTransport(access_token="...")
        client = DocsClient(transport)

        # Pull a document
        files = await client.pull("document_id", Path("./output"))

        # Make local edits...

        # Preview changes
        diff_result, requests, validation = client.diff(Path("./output/document_id"))

        # Push changes
        result = await client.push(Path("./output/document_id"))
    """

    def __init__(self, transport: Transport) -> None:
        """Initialize the client.

        Args:
            transport: Transport implementation for API communication
        """
        self._transport = transport

    async def pull(
        self,
        document_id: str,
        output_path: str | Path,
        *,
        save_raw: bool = True,
    ) -> list[Path]:
        """Pull a Google Doc to local files.

        Downloads the document via the API, transforms it to the local
        file format, and writes it to disk.

        Args:
            document_id: The Google Docs document ID
            output_path: Directory to write files to
            save_raw: If True, save raw API response to .raw/ folder

        Returns:
            List of paths to created files

        Raises:
            NotFoundError: If document doesn't exist or isn't accessible
            AuthenticationError: If access token is invalid
        """
        # TODO: Implement pull workflow
        # 1. Fetch document data via transport
        # 2. Transform to local file format
        # 3. Write files to disk
        # 4. Create .pristine/ archive
        # 5. Optionally save .raw/ files
        raise NotImplementedError("pull() not yet implemented")

    def diff(
        self, folder: str | Path
    ) -> tuple[DiffResult, list[dict[str, Any]], ValidationResult]:
        """Compare current files against pristine state.

        This is a local-only operation that doesn't call any APIs.
        It extracts the pristine state, compares against current files,
        and generates batchUpdate requests.

        Args:
            folder: Path to document folder (containing document.json)

        Returns:
            Tuple of (DiffResult, requests, ValidationResult) where:
            - DiffResult contains document info and change summary
            - requests is a list of batchUpdate request objects
            - ValidationResult indicates if push is safe

        Raises:
            DiffError: If folder structure is invalid
        """
        # TODO: Implement diff workflow
        # 1. Extract .pristine/document.zip
        # 2. Read current files
        # 3. Compare and generate requests
        # 4. Validate changes
        raise NotImplementedError("diff() not yet implemented")

    async def push(
        self,
        folder: str | Path,
        *,
        force: bool = False,
    ) -> PushResult:
        """Push local changes to Google Docs.

        Runs diff internally, then sends batchUpdate requests to the API.

        Args:
            folder: Path to document folder (containing document.json)
            force: If True, push despite warnings (blocks still prevent push)

        Returns:
            PushResult with success status and change count

        Raises:
            DiffError: If folder structure is invalid
            ValidationError: If changes are blocked
        """
        # TODO: Implement push workflow
        # 1. Run diff to get requests and validation
        # 2. Check validation (blocks always stop, warnings need --force)
        # 3. Send batchUpdate via transport
        raise NotImplementedError("push() not yet implemented")
