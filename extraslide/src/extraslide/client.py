"""SlidesClient - Main API for extraslide.

Provides the `pull`, `diff`, and `push` methods for the folder-based workflow.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

from extraslide.compression import (
    load_metadata,
    remove_ids,
    restore_ids,
    save_metadata,
)
from extraslide.diff import diff_sml
from extraslide.generator import json_to_sml
from extraslide.overview import generate_overview
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

# File names
METADATA_FILE = "presentation.json"  # Overview + metadata
SLIDES_FILE = "slides.sml"  # Slides only (IDs removed)
MASTERS_FILE = "masters.sml"  # Master slides
LAYOUTS_FILE = "layouts.sml"  # Layouts
IMAGES_FILE = "images.sml"  # Image definitions
RAW_DIR = ".raw"
META_DIR = ".meta"
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
        - slides.sml: Slides content (IDs removed for cleaner editing)
        - masters.sml: Master slide definitions
        - layouts.sml: Layout definitions
        - images.sml: Image URL mappings
        - presentation.json: Overview + metadata (slide summaries, title, ID)
        - .meta/id_mapping.json: ID mapping for diff/push
        - .raw/presentation.json: Raw API response (optional)
        - .pristine/presentation.zip: Zip of entire folder for diff comparison

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

        # Generate full SML
        full_sml = json_to_sml(presentation_data.data)

        # Split SML into separate files
        sml_parts = self._split_sml(full_sml)

        # Write images.sml
        if sml_parts["images"]:
            images_path = presentation_dir / IMAGES_FILE
            images_path.write_text(sml_parts["images"], encoding="utf-8")
            written_files.append(images_path)

        # Write masters.sml
        if sml_parts["masters"]:
            masters_path = presentation_dir / MASTERS_FILE
            masters_path.write_text(sml_parts["masters"], encoding="utf-8")
            written_files.append(masters_path)

        # Write layouts.sml
        if sml_parts["layouts"]:
            layouts_path = presentation_dir / LAYOUTS_FILE
            layouts_path.write_text(sml_parts["layouts"], encoding="utf-8")
            written_files.append(layouts_path)

        # Remove IDs and write slides.sml
        slides_sml = sml_parts["slides_wrapper"]
        slides_sml_no_ids, id_mapping = remove_ids(slides_sml)

        slides_path = presentation_dir / SLIDES_FILE
        slides_path.write_text(slides_sml_no_ids, encoding="utf-8")
        written_files.append(slides_path)

        # Save ID mapping for diff/push
        meta_dir = presentation_dir / META_DIR
        save_metadata({"id_mapping": id_mapping}, meta_dir)
        written_files.append(meta_dir / "id_mapping.json")

        # Generate presentation.json (overview + metadata)
        overview = generate_overview(presentation_data.data)
        overview["presentationId"] = presentation_data.presentation_id
        metadata_path = presentation_dir / METADATA_FILE
        metadata_path.write_text(
            json.dumps(overview, indent=2, ensure_ascii=False), encoding="utf-8"
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

        # Create pristine copy (zip of entire folder)
        pristine_path = self._create_pristine_copy(presentation_dir, written_files)
        written_files.append(pristine_path)

        return written_files

    def _split_sml(self, full_sml: str) -> dict[str, str]:
        """Split full SML into separate sections.

        Returns dict with keys: images, masters, layouts, slides, slides_wrapper
        - slides_wrapper includes the Presentation root with only Slides content
        """
        # Extract sections using regex
        images_match = re.search(r"(<Images>.*?</Images>)", full_sml, re.DOTALL)
        masters_match = re.search(r"(<Masters>.*?</Masters>)", full_sml, re.DOTALL)
        layouts_match = re.search(r"(<Layouts>.*?</Layouts>)", full_sml, re.DOTALL)
        slides_match = re.search(r"(<Slides>.*?</Slides>)", full_sml, re.DOTALL)

        # Extract Presentation attributes from opening tag
        pres_match = re.match(r"(<Presentation[^>]*>)", full_sml)
        pres_open = pres_match.group(1) if pres_match else "<Presentation>"

        # Build slides wrapper (Presentation with only Slides)
        slides_content = slides_match.group(1) if slides_match else "<Slides/>"
        slides_wrapper = f"{pres_open}\n\n  {slides_content}\n\n</Presentation>"

        return {
            "images": images_match.group(1) if images_match else "",
            "masters": masters_match.group(1) if masters_match else "",
            "layouts": layouts_match.group(1) if layouts_match else "",
            "slides": slides_match.group(1) if slides_match else "",
            "slides_wrapper": slides_wrapper,
        }

    def diff(self, folder_path: Path) -> list[dict[str, Any]]:
        """Compare current SML against pristine copy and generate update requests.

        This is a local-only operation that does not call any APIs.

        Reconstructs full SML from split files (slides.sml, masters.sml, etc.)
        and compares against the pristine copy.

        Args:
            folder_path: Path to the presentation folder

        Returns:
            List of Google Slides API batchUpdate request objects

        Example:
            >>> changes = client.diff(Path("./output/1abc..."))
            >>> print(f"Found {len(changes)} changes")
        """
        folder_path = Path(folder_path)

        # Reconstruct current full SML from split files
        current_sml = self._reconstruct_sml(folder_path)

        # Read pristine SML from zip
        pristine_sml = self._read_pristine_sml(folder_path)

        # Parse both
        original = parse_sml(pristine_sml)
        edited = parse_sml(current_sml)

        # Generate diff
        diff_result = diff_sml(original, edited)

        # Generate API requests
        return generate_requests(diff_result)

    def _reconstruct_sml(self, folder_path: Path) -> str:
        """Reconstruct full SML from split files.

        Reads slides.sml, masters.sml, layouts.sml, images.sml and combines
        them into a full Presentation SML. Restores IDs from mapping.
        """
        slides_path = folder_path / SLIDES_FILE
        if not slides_path.exists():
            raise FileNotFoundError(f"No slides.sml found at {slides_path}")

        # Read slides.sml and restore IDs
        slides_sml = slides_path.read_text(encoding="utf-8")
        meta_dir = folder_path / META_DIR
        if meta_dir.exists():
            metadata = load_metadata(meta_dir)
            if "id_mapping" in metadata:
                slides_sml = restore_ids(slides_sml, metadata["id_mapping"])

        # Extract Presentation opening tag and Slides content
        pres_match = re.match(r"(<Presentation[^>]*>)", slides_sml)
        pres_open = pres_match.group(1) if pres_match else "<Presentation>"

        slides_match = re.search(r"(<Slides>.*?</Slides>)", slides_sml, re.DOTALL)
        slides_content = slides_match.group(1) if slides_match else "<Slides/>"

        # Read other sections
        images_content = ""
        images_path = folder_path / IMAGES_FILE
        if images_path.exists():
            images_content = images_path.read_text(encoding="utf-8")

        masters_content = ""
        masters_path = folder_path / MASTERS_FILE
        if masters_path.exists():
            masters_content = masters_path.read_text(encoding="utf-8")

        layouts_content = ""
        layouts_path = folder_path / LAYOUTS_FILE
        if layouts_path.exists():
            layouts_content = layouts_path.read_text(encoding="utf-8")

        # Reconstruct full SML
        parts = [pres_open, ""]
        if images_content:
            parts.append(f"  {images_content}")
            parts.append("")
        if masters_content:
            parts.append(f"  {masters_content}")
            parts.append("")
        if layouts_content:
            parts.append(f"  {layouts_content}")
            parts.append("")
        parts.append(f"  {slides_content}")
        parts.append("")
        parts.append("</Presentation>")

        return "\n".join(parts)

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
        with all SML files and metadata. This zip is used by diff/push to
        compare against the current state.

        Includes: slides.sml, masters.sml, layouts.sml, images.sml,
                  presentation.json, .meta/id_mapping.json
        Excludes: .raw/, .pristine/
        """
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

    def _read_pristine_sml(self, folder_path: Path) -> str:
        """Reconstruct pristine SML from the zip file."""
        zip_path = folder_path / PRISTINE_DIR / PRISTINE_ZIP
        if not zip_path.exists():
            raise FileNotFoundError(f"Pristine zip not found: {zip_path}")

        with zipfile.ZipFile(zip_path, "r") as zf:
            # Read slides.sml and restore IDs
            slides_sml = zf.read(SLIDES_FILE).decode("utf-8")

            # Load ID mapping if present
            if f"{META_DIR}/id_mapping.json" in zf.namelist():
                id_mapping_data = zf.read(f"{META_DIR}/id_mapping.json").decode("utf-8")
                id_mapping = json.loads(id_mapping_data)
                slides_sml = restore_ids(slides_sml, id_mapping)

            # Extract Presentation opening tag and Slides content
            pres_match = re.match(r"(<Presentation[^>]*>)", slides_sml)
            pres_open = pres_match.group(1) if pres_match else "<Presentation>"

            slides_match = re.search(r"(<Slides>.*?</Slides>)", slides_sml, re.DOTALL)
            slides_content = slides_match.group(1) if slides_match else "<Slides/>"

            # Read other sections from zip
            images_content = ""
            if IMAGES_FILE in zf.namelist():
                images_content = zf.read(IMAGES_FILE).decode("utf-8")

            masters_content = ""
            if MASTERS_FILE in zf.namelist():
                masters_content = zf.read(MASTERS_FILE).decode("utf-8")

            layouts_content = ""
            if LAYOUTS_FILE in zf.namelist():
                layouts_content = zf.read(LAYOUTS_FILE).decode("utf-8")

            # Reconstruct full SML
            parts = [pres_open, ""]
            if images_content:
                parts.append(f"  {images_content}")
                parts.append("")
            if masters_content:
                parts.append(f"  {masters_content}")
                parts.append("")
            if layouts_content:
                parts.append(f"  {layouts_content}")
                parts.append("")
            parts.append(f"  {slides_content}")
            parts.append("")
            parts.append("</Presentation>")

            return "\n".join(parts)
