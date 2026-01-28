"""SlidesClient - Main API for extraslide.

Provides the `pull`, `diff`, and `push` methods for the folder-based workflow.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from extraslide.diff import diff_sml
from extraslide.generator import json_to_sml
from extraslide.parser import parse_sml
from extraslide.requests import generate_requests
from extraslide.transport import (
    APIError,
    AuthenticationError,
    NotFoundError,
    Transport,
    TransportError,
)

# Re-export exceptions for backwards compatibility
__all__ = [
    "APIError",
    "AuthenticationError",
    "NotFoundError",
    "SlidesClient",
    "TransportError",
]

# Metadata filename
METADATA_FILE = "presentation.json"
SML_FILE = "presentation.sml"
RAW_DIR = ".raw"
PRISTINE_DIR = ".pristine"
PRISTINE_ZIP = "presentation.zip"


class SlidesClient:
    """Client for transforming Google Slides to/from SML representation.

    This client uses a folder-based workflow:
    1. pull() - Fetch presentation and save as SML in a folder
    2. diff() - Compare current SML against pristine copy
    3. push() - Apply changes to Google Slides

    Example:
        >>> from extraslide.transport import GoogleSlidesTransport
        >>> transport = GoogleSlidesTransport(access_token="ya29...")
        >>> client = SlidesClient(transport)
        >>> await client.pull("1abc...", "./output")
        >>> # Edit ./output/1abc.../presentation.sml
        >>> changes = client.diff(Path("./output/1abc..."))
        >>> await client.push(Path("./output/1abc..."))
    """

    def __init__(self, transport: Transport) -> None:
        """Initialize the client.

        Args:
            transport: Transport implementation for fetching/updating presentations
        """
        self._transport = transport

    async def pull(
        self,
        presentation_id: str,
        output_path: str | Path,
        *,
        save_raw: bool = True,
    ) -> list[Path]:
        """Pull a presentation and write to folder structure.

        Creates a folder with:
        - presentation.sml: The editable SML file
        - presentation.json: Metadata (title, presentation ID)
        - .raw/presentation.json: Raw API response (optional)
        - .pristine/presentation.zip: Original state for diff comparison

        Args:
            presentation_id: The ID of the presentation (from the URL)
            output_path: Directory to write files to
            save_raw: If True, saves raw API response to .raw/ folder (default: True)

        Returns:
            List of paths to written files

        Example:
            >>> files = await client.pull("1abc...", "./output")
            >>> print(f"Wrote {len(files)} files")
        """
        # Fetch presentation data
        presentation_data = await self._transport.get_presentation(presentation_id)

        # Create output directory
        output_path = Path(output_path)
        presentation_dir = output_path / presentation_id
        presentation_dir.mkdir(parents=True, exist_ok=True)

        written_files: list[Path] = []

        # Generate SML
        sml_content = json_to_sml(presentation_data.data)
        sml_path = presentation_dir / SML_FILE
        sml_path.write_text(sml_content, encoding="utf-8")
        written_files.append(sml_path)

        # Write metadata
        metadata = {
            "presentationId": presentation_data.presentation_id,
            "title": presentation_data.data.get("title", ""),
        }
        metadata_path = presentation_dir / METADATA_FILE
        metadata_path.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        written_files.append(metadata_path)

        # Save raw API response
        if save_raw:
            raw_dir = presentation_dir / RAW_DIR
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_path = raw_dir / "presentation.json"
            raw_path.write_text(
                json.dumps(presentation_data.data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            written_files.append(raw_path)

        # Create pristine copy for diff/push workflow
        pristine_path = self._create_pristine_copy(presentation_dir, written_files)
        written_files.append(pristine_path)

        return written_files

    def diff(self, folder_path: Path) -> list[dict[str, Any]]:
        """Compare current SML against pristine copy and generate update requests.

        This is a local-only operation that does not call any APIs.

        Args:
            folder_path: Path to the presentation folder

        Returns:
            List of Google Slides API batchUpdate request objects

        Example:
            >>> changes = client.diff(Path("./output/1abc..."))
            >>> print(f"Found {len(changes)} changes")
        """
        folder_path = Path(folder_path)

        # Read current SML
        current_sml_path = folder_path / SML_FILE
        if not current_sml_path.exists():
            raise FileNotFoundError(f"SML file not found: {current_sml_path}")
        current_sml = current_sml_path.read_text(encoding="utf-8")

        # Read pristine SML from zip
        pristine_sml = self._read_pristine_sml(folder_path)

        # Parse both
        original = parse_sml(pristine_sml)
        edited = parse_sml(current_sml)

        # Generate diff
        diff_result = diff_sml(original, edited)

        # Generate API requests
        return generate_requests(diff_result)

    async def push(self, folder_path: Path) -> dict[str, Any]:
        """Apply SML changes to the presentation.

        Compares current SML against pristine copy, generates batchUpdate
        requests, and sends them to the Google Slides API.

        Args:
            folder_path: Path to the presentation folder

        Returns:
            API response from batchUpdate

        Example:
            >>> response = await client.push(Path("./output/1abc..."))
            >>> print(f"Applied {len(response.get('replies', []))} changes")
        """
        folder_path = Path(folder_path)

        # Get presentation ID from metadata
        metadata_path = folder_path / METADATA_FILE
        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata file not found: {metadata_path}")

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        presentation_id = metadata.get("presentationId")
        if not presentation_id:
            raise ValueError("Presentation ID not found in metadata")

        # Generate diff
        requests = self.diff(folder_path)

        if not requests:
            return {"replies": [], "message": "No changes detected"}

        # Send batch update
        return await self._transport.batch_update(presentation_id, requests)

    def _create_pristine_copy(
        self,
        presentation_dir: Path,
        written_files: list[Path],
    ) -> Path:
        """Create a pristine copy of the pulled files for diff/push workflow.

        Creates a .pristine/ directory containing a presentation.zip file
        with all the pulled files (excluding .raw/). This zip is used by
        diff/push to compare against the current state.
        """
        pristine_dir = presentation_dir / PRISTINE_DIR
        pristine_dir.mkdir(parents=True, exist_ok=True)

        zip_path = pristine_dir / PRISTINE_ZIP

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in written_files:
                # Skip .raw/ files - not part of canonical representation
                if RAW_DIR in file_path.parts:
                    continue
                # Store with path relative to presentation directory
                arcname = file_path.relative_to(presentation_dir)
                zf.write(file_path, arcname)

        return zip_path

    def _read_pristine_sml(self, folder_path: Path) -> str:
        """Read the pristine SML from the zip file."""
        zip_path = folder_path / PRISTINE_DIR / PRISTINE_ZIP
        if not zip_path.exists():
            raise FileNotFoundError(f"Pristine zip not found: {zip_path}")

        with zipfile.ZipFile(zip_path, "r") as zf:
            return zf.read(SML_FILE).decode("utf-8")
