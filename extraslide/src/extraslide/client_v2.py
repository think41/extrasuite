"""SlidesClient V2 - New ID-based format.

Provides the `pull`, `diff`, and `push` methods using the new format:
- id_mapping.json: clean_id -> google_object_id
- styles.json: clean_id -> styles (relative positions for children)
- slides/NN/content.sml: minimal XML with IDs, positions, text, pattern hints
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from extraslide.content_diff import diff_presentation
from extraslide.content_parser import parse_slide_content
from extraslide.content_requests import generate_batch_requests
from extraslide.slide_processor import process_presentation, write_new_format
from extraslide.transport import Transport

# File and directory names
PRESENTATION_FILE = "presentation.json"
ID_MAPPING_FILE = "id_mapping.json"
STYLES_FILE = "styles.json"
SLIDES_DIR = "slides"
RAW_DIR = ".raw"
PRISTINE_DIR = ".pristine"
PRISTINE_ZIP = "presentation.zip"


class SlidesClientV2:
    """Client for transforming Google Slides using the new ID-based format.

    This client uses a folder-based workflow with the new format:
    1. pull() - Fetch presentation and save in new format
    2. diff() - Compare current content against pristine copy
    3. push() - Apply changes to Google Slides

    Example:
        >>> from extraslide.transport import GoogleSlidesTransport
        >>> transport = GoogleSlidesTransport(access_token="ya29...")
        >>> client = SlidesClientV2(transport)
        >>> await client.pull("1abc...", "./output")
        >>> # Edit slides/01/content.sml, slides/02/content.sml, etc.
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
        """Pull a presentation and write to the new folder format.

        Creates a folder with:
        - presentation.json: Metadata (title, page size, slide count)
        - id_mapping.json: clean_id -> google_object_id
        - styles.json: clean_id -> styles (with relative positions)
        - slides/01/content.sml, slides/02/content.sml, ...
        - .raw/presentation.json: Raw API response (optional)
        - .pristine/presentation.zip: Zip for diff comparison

        Args:
            presentation_id: The ID of the presentation (from the URL)
            output_path: Directory to write files to
            save_raw: If True, saves raw API response to .raw/ folder

        Returns:
            List of paths to written files
        """
        # Fetch presentation data
        presentation_data = await self._transport.get_presentation(presentation_id)

        # Create output directory
        output_path = Path(output_path)
        presentation_dir = output_path / presentation_id
        presentation_dir.mkdir(parents=True, exist_ok=True)

        written_files: list[Path] = []

        # Process the presentation into the new format
        result = process_presentation(presentation_data.data)

        # Write the new format files
        written_files.extend(write_new_format(result, presentation_dir))

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

        # Create pristine copy
        pristine_path = self._create_pristine_copy(presentation_dir, written_files)
        written_files.append(pristine_path)

        return written_files

    def diff(self, folder_path: Path) -> list[dict[str, Any]]:
        """Compare current content against pristine copy and generate update requests.

        This is a local-only operation that does not call any APIs.

        Args:
            folder_path: Path to the presentation folder

        Returns:
            List of Google Slides API batchUpdate request objects
        """
        folder_path = Path(folder_path)

        # Read current state
        current_slides = self._read_current_slides(folder_path)
        id_mapping = self._read_json(folder_path / ID_MAPPING_FILE)

        # Read pristine state
        pristine_slides, pristine_styles = self._read_pristine(folder_path)

        # Generate diff
        diff_result = diff_presentation(
            pristine_slides,
            current_slides,
            pristine_styles,
            id_mapping,
        )

        # Build slide ID mapping (slide_index -> google_slide_id)
        slide_id_mapping = self._build_slide_id_mapping(id_mapping)

        # Generate API requests
        return generate_batch_requests(diff_result, id_mapping, slide_id_mapping)

    async def push(self, folder_path: Path) -> dict[str, Any]:
        """Apply content changes to the presentation.

        Args:
            folder_path: Path to the presentation folder

        Returns:
            API response from batchUpdate
        """
        folder_path = Path(folder_path)

        # Get presentation ID from metadata
        metadata = self._read_json(folder_path / PRESENTATION_FILE)
        presentation_id = metadata.get("presentationId")
        if not presentation_id:
            raise ValueError("Presentation ID not found in presentation.json")

        # Generate diff
        requests = self.diff(folder_path)

        if not requests:
            return {"replies": [], "message": "No changes detected"}

        # Send batch update
        return await self._transport.batch_update(presentation_id, requests)

    def _read_current_slides(self, folder_path: Path) -> dict[str, list[Any]]:
        """Read current slide content files."""
        slides_dir = folder_path / SLIDES_DIR
        result: dict[str, list[Any]] = {}

        if not slides_dir.exists():
            return result

        for slide_folder in sorted(slides_dir.iterdir()):
            if slide_folder.is_dir():
                content_file = slide_folder / "content.sml"
                if content_file.exists():
                    content = content_file.read_text(encoding="utf-8")
                    result[slide_folder.name] = parse_slide_content(content)

        return result

    def _read_pristine(
        self,
        folder_path: Path,
    ) -> tuple[dict[str, list[Any]], dict[str, dict[str, Any]]]:
        """Read pristine slides and styles from zip."""
        zip_path = folder_path / PRISTINE_DIR / PRISTINE_ZIP
        if not zip_path.exists():
            raise FileNotFoundError(f"Pristine zip not found: {zip_path}")

        slides: dict[str, list[Any]] = {}
        styles: dict[str, dict[str, Any]] = {}

        with zipfile.ZipFile(zip_path, "r") as zf:
            # Read styles.json
            if STYLES_FILE in zf.namelist():
                styles = json.loads(zf.read(STYLES_FILE).decode("utf-8"))

            # Read slide content files
            for name in zf.namelist():
                if name.startswith(f"{SLIDES_DIR}/") and name.endswith("/content.sml"):
                    # Extract slide index from path like "slides/01/content.sml"
                    parts = name.split("/")
                    if len(parts) >= 2:
                        slide_index = parts[1]
                        content = zf.read(name).decode("utf-8")
                        slides[slide_index] = parse_slide_content(content)

        return slides, styles

    def _read_json(self, path: Path) -> dict[str, Any]:
        """Read a JSON file."""
        if not path.exists():
            return {}
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data

    def _build_slide_id_mapping(self, id_mapping: dict[str, str]) -> dict[str, str]:
        """Build mapping from slide index to Google slide ID.

        Slide clean IDs are like "s1", "s2", etc.
        Slide indices are like "01", "02", etc.
        """
        result: dict[str, str] = {}

        for clean_id, google_id in id_mapping.items():
            if clean_id.startswith("s"):
                try:
                    # Extract number from "s1", "s2", etc.
                    num = int(clean_id[1:])
                    # Convert to zero-padded index
                    slide_index = f"{num:02d}"
                    result[slide_index] = google_id
                except ValueError:
                    continue

        return result

    def _create_pristine_copy(
        self,
        presentation_dir: Path,
        written_files: list[Path],
    ) -> Path:
        """Create a pristine copy of the pulled files for diff/push workflow."""
        pristine_dir = presentation_dir / PRISTINE_DIR
        pristine_dir.mkdir(parents=True, exist_ok=True)

        zip_path = pristine_dir / PRISTINE_ZIP

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in written_files:
                # Skip raw and pristine directories
                if any(d in file_path.parts for d in [RAW_DIR, PRISTINE_DIR]):
                    continue

                # Store with path relative to presentation directory
                arcname = file_path.relative_to(presentation_dir)
                zf.write(file_path, arcname)

        return zip_path


async def pull_v2(
    transport: Transport,
    presentation_id: str,
    output_path: str | Path,
    *,
    save_raw: bool = True,
) -> list[Path]:
    """Convenience function to pull a presentation using the new format.

    Args:
        transport: Transport implementation
        presentation_id: The ID of the presentation
        output_path: Directory to write files to
        save_raw: If True, saves raw API response

    Returns:
        List of paths to written files
    """
    client = SlidesClientV2(transport)
    return await client.pull(presentation_id, output_path, save_raw=save_raw)


def diff_v2(folder_path: str | Path) -> list[dict[str, Any]]:
    """Convenience function to diff a presentation folder.

    Note: This creates a client with a dummy transport since diff doesn't need it.

    Args:
        folder_path: Path to the presentation folder

    Returns:
        List of batchUpdate request objects
    """

    # Create a minimal transport for diff (not used)
    class DummyTransport(Transport):
        async def get_presentation(self, _: str) -> Any:
            raise NotImplementedError("Diff doesn't need transport")

        async def batch_update(self, _id: str, _reqs: list[Any]) -> Any:
            raise NotImplementedError("Diff doesn't need transport")

        async def close(self) -> None:
            pass

    client = SlidesClientV2(DummyTransport())
    return client.diff(Path(folder_path))
