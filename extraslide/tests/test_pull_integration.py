"""Integration tests for the pull/diff/push workflow.

Uses golden files to test without making real API calls.
"""

import json
from pathlib import Path

import pytest

from extraslide import LocalFileTransport, SlidesClient

GOLDEN_DIR = Path(__file__).parent / "golden"


@pytest.fixture
def transport() -> LocalFileTransport:
    """Create a LocalFileTransport pointing to golden files."""
    return LocalFileTransport(GOLDEN_DIR)


@pytest.fixture
def client(transport: LocalFileTransport) -> SlidesClient:
    """Create a SlidesClient with LocalFileTransport."""
    return SlidesClient(transport)


class TestPull:
    """Tests for the pull command."""

    async def test_pull_creates_folder_structure(
        self, client: SlidesClient, tmp_path: Path
    ) -> None:
        """Pull creates the expected folder structure."""
        presentation_id = "simple_presentation"

        files = await client.pull(presentation_id, tmp_path)

        # Check folder structure
        pres_dir = tmp_path / presentation_id
        assert pres_dir.exists()
        assert (pres_dir / "presentation.sml").exists()
        assert (pres_dir / "presentation.json").exists()
        assert (pres_dir / ".raw" / "presentation.json").exists()
        assert (pres_dir / ".pristine" / "presentation.zip").exists()

        # Check we got all expected files
        assert len(files) == 4

    async def test_pull_without_raw(self, client: SlidesClient, tmp_path: Path) -> None:
        """Pull with save_raw=False skips the .raw/ folder."""
        presentation_id = "simple_presentation"

        files = await client.pull(presentation_id, tmp_path, save_raw=False)

        pres_dir = tmp_path / presentation_id
        assert (pres_dir / "presentation.sml").exists()
        assert (pres_dir / "presentation.json").exists()
        assert not (pres_dir / ".raw").exists()
        assert (pres_dir / ".pristine" / "presentation.zip").exists()

        # Only 3 files (no raw)
        assert len(files) == 3

    async def test_pull_sml_contains_presentation(
        self, client: SlidesClient, tmp_path: Path
    ) -> None:
        """Pull generates valid SML with Presentation element."""
        presentation_id = "simple_presentation"

        await client.pull(presentation_id, tmp_path)

        sml_path = tmp_path / presentation_id / "presentation.sml"
        content = sml_path.read_text(encoding="utf-8")

        assert "<Presentation" in content
        assert "</Presentation>" in content

    async def test_pull_metadata_contains_id(
        self, client: SlidesClient, tmp_path: Path
    ) -> None:
        """Pull writes metadata with presentation ID."""
        folder_name = "simple_presentation"

        await client.pull(folder_name, tmp_path)

        metadata_path = tmp_path / folder_name / "presentation.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        # Presentation ID comes from the API response, not the folder name
        assert "presentationId" in metadata
        assert len(metadata["presentationId"]) > 0


class TestDiff:
    """Tests for the diff command."""

    async def test_diff_no_changes(self, client: SlidesClient, tmp_path: Path) -> None:
        """Diff returns empty list when no changes made."""
        presentation_id = "simple_presentation"

        await client.pull(presentation_id, tmp_path)
        pres_dir = tmp_path / presentation_id

        requests = client.diff(pres_dir)

        assert requests == []

    async def test_diff_with_text_change(
        self, client: SlidesClient, tmp_path: Path
    ) -> None:
        """Diff detects text changes in SML."""
        presentation_id = "simple_presentation"

        await client.pull(presentation_id, tmp_path)
        pres_dir = tmp_path / presentation_id

        # Modify the SML file - add a new slide
        sml_path = pres_dir / "presentation.sml"
        content = sml_path.read_text(encoding="utf-8")

        # Add a new slide before </Slides>
        new_slide = '    <Slide id="new_slide_1"/>\n  '
        modified = content.replace("</Slides>", f"{new_slide}</Slides>")
        sml_path.write_text(modified, encoding="utf-8")

        requests = client.diff(pres_dir)

        # Should have at least one createSlide request
        create_requests = [r for r in requests if "createSlide" in r]
        assert len(create_requests) >= 1


class TestPush:
    """Tests for the push command."""

    async def test_push_no_changes(
        self, client: SlidesClient, transport: LocalFileTransport, tmp_path: Path
    ) -> None:
        """Push with no changes returns appropriate message."""
        presentation_id = "simple_presentation"

        await client.pull(presentation_id, tmp_path)
        pres_dir = tmp_path / presentation_id

        response = await client.push(pres_dir)

        assert response.get("message") == "No changes detected"
        assert transport.batch_updates == []

    async def test_push_with_changes(
        self, client: SlidesClient, transport: LocalFileTransport, tmp_path: Path
    ) -> None:
        """Push with changes sends batch update request."""
        folder_name = "simple_presentation"

        await client.pull(folder_name, tmp_path)
        pres_dir = tmp_path / folder_name

        # Modify the SML file
        sml_path = pres_dir / "presentation.sml"
        content = sml_path.read_text(encoding="utf-8")
        new_slide = '    <Slide id="new_slide_for_push"/>\n  '
        modified = content.replace("</Slides>", f"{new_slide}</Slides>")
        sml_path.write_text(modified, encoding="utf-8")

        await client.push(pres_dir)

        # Should have called batch_update
        assert len(transport.batch_updates) == 1
        # Presentation ID comes from the metadata file, not the folder name
        assert len(transport.batch_updates[0]["presentation_id"]) > 0
        assert len(transport.batch_updates[0]["requests"]) > 0
