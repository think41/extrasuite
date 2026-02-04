"""Main client for Google Docs operations.

Provides the DocsClient class with pull(), diff(), and push() methods
implementing the core workflow for Google Docs manipulation.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from extradoc.diff_engine import diff_documents as diff_xml_documents
from extradoc.xml_converter import convert_document_to_xml

if TYPE_CHECKING:
    from extradoc.transport import Transport

# File and directory names
DOCUMENT_XML = "document.xml"
STYLES_XML = "styles.xml"
RAW_DIR = ".raw"
PRISTINE_DIR = ".pristine"
PRISTINE_ZIP = "document.zip"


class DiffError(Exception):
    """Raised when diff operation fails due to invalid folder structure."""


class ValidationError(Exception):
    """Raised when push validation fails."""


@dataclass
class DiffResult:
    """Result of comparing current files against pristine state."""

    document_id: str
    has_changes: bool


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

        # Make local edits to document.xml...

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
        XML format, and writes it to disk.

        Creates a folder with:
        - document.xml: Main document content in ExtraDoc XML format
        - styles.xml: Factorized style definitions
        - .raw/document.json: Raw API response (optional)
        - .pristine/document.zip: Original state for diff comparison

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
        # Fetch document data via transport
        document_data = await self._transport.get_document(document_id)

        # Create output directory
        output_path = Path(output_path)
        document_dir = output_path / document_id
        document_dir.mkdir(parents=True, exist_ok=True)

        written_files: list[Path] = []

        # Convert to XML format
        document_xml, styles_xml = convert_document_to_xml(document_data.raw)

        # Write document.xml
        xml_path = document_dir / DOCUMENT_XML
        xml_path.write_text(document_xml, encoding="utf-8")
        written_files.append(xml_path)

        # Write styles.xml
        styles_path = document_dir / STYLES_XML
        styles_path.write_text(styles_xml, encoding="utf-8")
        written_files.append(styles_path)

        # Save raw API response
        if save_raw:
            raw_dir = document_dir / RAW_DIR
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_path = raw_dir / "document.json"
            raw_path.write_text(
                json.dumps(document_data.raw, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            written_files.append(raw_path)

        # Create pristine copy for diff/push workflow
        pristine_path = self._create_pristine_copy(document_dir, written_files)
        written_files.append(pristine_path)

        return written_files

    def _create_pristine_copy(
        self,
        document_dir: Path,
        written_files: list[Path],
    ) -> Path:
        """Create a pristine copy of the pulled files for diff/push workflow.

        Args:
            document_dir: Path to the document folder
            written_files: List of written file paths to include

        Returns:
            Path to the created zip file
        """
        pristine_dir = document_dir / PRISTINE_DIR
        pristine_dir.mkdir(parents=True, exist_ok=True)

        zip_path = pristine_dir / PRISTINE_ZIP

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in written_files:
                # Skip raw and pristine directories
                if any(d in file_path.parts for d in [RAW_DIR, PRISTINE_DIR]):
                    continue

                # Store with path relative to document directory
                arcname = file_path.relative_to(document_dir)
                zf.write(file_path, arcname)

        return zip_path

    def diff(
        self, folder: str | Path
    ) -> tuple[DiffResult, list[dict[str, Any]], ValidationResult]:
        """Compare current files against pristine state.

        This is a local-only operation that doesn't call any APIs.
        It extracts the pristine state, compares against current files,
        and generates batchUpdate requests.

        Args:
            folder: Path to document folder (containing document.xml)

        Returns:
            Tuple of (DiffResult, requests, ValidationResult) where:
            - DiffResult contains document info and change summary
            - requests is a list of batchUpdate request objects
            - ValidationResult indicates if push is safe

        Raises:
            DiffError: If folder structure is invalid
        """
        folder = Path(folder)

        # Read current XML files
        current_xml_path = folder / DOCUMENT_XML
        if not current_xml_path.exists():
            raise DiffError(f"document.xml not found in {folder}")
        current_xml = current_xml_path.read_text(encoding="utf-8")

        current_styles_path = folder / STYLES_XML
        current_styles = None
        if current_styles_path.exists():
            current_styles = current_styles_path.read_text(encoding="utf-8")

        # Read pristine XML from zip
        pristine_xml, pristine_styles, document_id = self._read_pristine(folder)

        # Generate batchUpdate requests using the diff engine
        requests = diff_xml_documents(
            pristine_xml, current_xml, pristine_styles, current_styles
        )

        # Check if there are changes
        has_changes = len(requests) > 0

        # Create results
        diff_result = DiffResult(
            document_id=document_id,
            has_changes=has_changes,
        )

        # Validation (for now, always valid - can add checks later)
        validation = ValidationResult(can_push=True)

        return diff_result, requests, validation

    def _read_pristine(self, folder: Path) -> tuple[str, str | None, str]:
        """Read pristine XML files from zip.

        Args:
            folder: Path to document folder

        Returns:
            Tuple of (pristine_xml, pristine_styles, document_id)

        Raises:
            DiffError: If pristine zip is missing or invalid
        """
        zip_path = folder / PRISTINE_DIR / PRISTINE_ZIP
        if not zip_path.exists():
            raise DiffError(f"Pristine zip not found: {zip_path}")

        pristine_xml = ""
        pristine_styles: str | None = None

        with zipfile.ZipFile(zip_path, "r") as zf:
            # Read document.xml
            if DOCUMENT_XML in zf.namelist():
                pristine_xml = zf.read(DOCUMENT_XML).decode("utf-8")
            else:
                raise DiffError(f"{DOCUMENT_XML} not found in pristine zip")

            # Read styles.xml if present
            if STYLES_XML in zf.namelist():
                pristine_styles = zf.read(STYLES_XML).decode("utf-8")

        # Extract document ID from XML
        document_id = folder.name
        import re

        match = re.search(r'<doc\s+id="([^"]+)"', pristine_xml)
        if match:
            document_id = match.group(1)

        return pristine_xml, pristine_styles, document_id

    async def push(
        self,
        folder: str | Path,
        *,
        force: bool = False,
    ) -> PushResult:
        """Push local changes to Google Docs.

        Runs diff internally, then sends batchUpdate requests to the API.

        Args:
            folder: Path to document folder (containing document.xml)
            force: If True, push despite warnings (blocks still prevent push)

        Returns:
            PushResult with success status and change count

        Raises:
            DiffError: If folder structure is invalid
            ValidationError: If changes are blocked
        """
        folder = Path(folder)

        # Run diff to get requests and validation
        diff_result, requests, validation = self.diff(folder)

        # Check validation
        if not validation.can_push:
            raise ValidationError(f"Cannot push: {'; '.join(validation.blocks)}")

        if validation.warnings and not force:
            raise ValidationError(
                f"Push has warnings (use --force to override): "
                f"{'; '.join(validation.warnings)}"
            )

        # No changes to push
        if not requests:
            return PushResult(
                success=True,
                document_id=diff_result.document_id,
                changes_applied=0,
                message="No changes to apply",
            )

        # Send batchUpdate via transport
        await self._transport.batch_update(diff_result.document_id, requests)

        return PushResult(
            success=True,
            document_id=diff_result.document_id,
            changes_applied=len(requests),
            message=f"Applied {len(requests)} changes",
        )
