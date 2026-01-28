"""Tests for the SlidesClient API."""

from pathlib import Path

import pytest

from extraslide import LocalFileTransport, SlidesClient
from extraslide.diff import diff_sml
from extraslide.parser import parse_sml
from extraslide.requests import generate_requests

GOLDEN_DIR = Path(__file__).parent / "golden"


@pytest.fixture
def transport() -> LocalFileTransport:
    """Create a LocalFileTransport for testing."""
    return LocalFileTransport(GOLDEN_DIR)


@pytest.fixture
def client(transport: LocalFileTransport) -> SlidesClient:
    """Create a SlidesClient for testing."""
    return SlidesClient(transport)


class TestClientInitialization:
    """Test client initialization."""

    def test_client_with_transport(self, transport: LocalFileTransport) -> None:
        """Client can be created with a transport."""
        client = SlidesClient(transport)
        assert client._transport is transport


class TestDiff:
    """Test diff functionality using SML strings directly.

    These tests verify the underlying diff logic without needing
    the full folder workflow.
    """

    def test_diff_no_changes(self) -> None:
        """Identical SML returns empty request list."""
        sml = """<Presentation id="pres1">
            <Slides>
                <Slide id="slide1"/>
            </Slides>
        </Presentation>"""

        original = parse_sml(sml)
        edited = parse_sml(sml)
        diff_result = diff_sml(original, edited)
        requests = generate_requests(diff_result)

        assert requests == []

    def test_diff_add_shape(self) -> None:
        """Adding a shape returns createShape request."""
        original_sml = """<Presentation id="pres1">
            <Slides>
                <Slide id="slide1"/>
            </Slides>
        </Presentation>"""

        edited_sml = """<Presentation id="pres1">
            <Slides>
                <Slide id="slide1">
                    <Rect id="rect1" class="x-100 y-100 w-200 h-100"/>
                </Slide>
            </Slides>
        </Presentation>"""

        original = parse_sml(original_sml)
        edited = parse_sml(edited_sml)
        diff_result = diff_sml(original, edited)
        requests = generate_requests(diff_result)

        create_requests = [r for r in requests if "createShape" in r]
        assert len(create_requests) == 1
        assert create_requests[0]["createShape"]["objectId"] == "rect1"

    def test_diff_delete_shape(self) -> None:
        """Deleting a shape returns deleteObject request."""
        original_sml = """<Presentation id="pres1">
            <Slides>
                <Slide id="slide1">
                    <Rect id="rect1" class="x-100 y-100 w-200 h-100"/>
                </Slide>
            </Slides>
        </Presentation>"""

        edited_sml = """<Presentation id="pres1">
            <Slides>
                <Slide id="slide1"/>
            </Slides>
        </Presentation>"""

        original = parse_sml(original_sml)
        edited = parse_sml(edited_sml)
        diff_result = diff_sml(original, edited)
        requests = generate_requests(diff_result)

        delete_requests = [r for r in requests if "deleteObject" in r]
        assert len(delete_requests) == 1
        assert delete_requests[0]["deleteObject"]["objectId"] == "rect1"

    def test_diff_modify_fill(self) -> None:
        """Changing fill color returns updateShapeProperties."""
        original_sml = """<Presentation id="pres1">
            <Slides>
                <Slide id="slide1">
                    <Rect id="rect1" class="x-100 y-100 w-200 h-100 fill-#ffffff"/>
                </Slide>
            </Slides>
        </Presentation>"""

        edited_sml = """<Presentation id="pres1">
            <Slides>
                <Slide id="slide1">
                    <Rect id="rect1" class="x-100 y-100 w-200 h-100 fill-#3b82f6"/>
                </Slide>
            </Slides>
        </Presentation>"""

        original = parse_sml(original_sml)
        edited = parse_sml(edited_sml)
        diff_result = diff_sml(original, edited)
        requests = generate_requests(diff_result)

        update_requests = [r for r in requests if "updateShapeProperties" in r]
        assert len(update_requests) >= 1

    def test_diff_add_slide(self) -> None:
        """Adding a slide returns createSlide request."""
        original_sml = """<Presentation id="pres1">
            <Slides>
                <Slide id="slide1"/>
            </Slides>
        </Presentation>"""

        edited_sml = """<Presentation id="pres1">
            <Slides>
                <Slide id="slide1"/>
                <Slide id="slide2"/>
            </Slides>
        </Presentation>"""

        original = parse_sml(original_sml)
        edited = parse_sml(edited_sml)
        diff_result = diff_sml(original, edited)
        requests = generate_requests(diff_result)

        create_requests = [r for r in requests if "createSlide" in r]
        assert len(create_requests) == 1
        assert create_requests[0]["createSlide"]["objectId"] == "slide2"


class TestFolderDiff:
    """Test diff with the folder-based workflow."""

    async def test_diff_folder_no_changes(
        self, client: SlidesClient, tmp_path: Path
    ) -> None:
        """Diff on unchanged folder returns empty list."""
        await client.pull("simple_presentation", tmp_path)
        pres_dir = tmp_path / "simple_presentation"

        requests = client.diff(pres_dir)

        assert requests == []

    async def test_diff_folder_missing_sml_raises(
        self, client: SlidesClient, tmp_path: Path
    ) -> None:
        """Diff raises FileNotFoundError if SML file is missing."""
        await client.pull("simple_presentation", tmp_path)
        pres_dir = tmp_path / "simple_presentation"

        # Delete slides.sml
        (pres_dir / "slides.sml").unlink()

        with pytest.raises(FileNotFoundError, match=r"No slides\.sml found"):
            client.diff(pres_dir)

    async def test_diff_folder_missing_pristine_raises(
        self, client: SlidesClient, tmp_path: Path
    ) -> None:
        """Diff raises FileNotFoundError if pristine zip is missing."""
        await client.pull("simple_presentation", tmp_path)
        pres_dir = tmp_path / "simple_presentation"

        # Delete the pristine zip
        (pres_dir / ".pristine" / "presentation.zip").unlink()

        with pytest.raises(FileNotFoundError, match="Pristine zip not found"):
            client.diff(pres_dir)
