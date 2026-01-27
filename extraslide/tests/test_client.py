"""Tests for the SlidesClient API."""

import pytest

from extraslide.client import SlidesClient


class TestExtractPresentationId:
    """Test URL parsing."""

    def test_extract_from_edit_url(self) -> None:
        """Extract ID from /edit URL."""
        client = SlidesClient(access_token="test_token")
        url = "https://docs.google.com/presentation/d/abc123xyz/edit"
        assert client._extract_presentation_id(url) == "abc123xyz"

    def test_extract_from_edit_url_with_slide(self) -> None:
        """Extract ID from /edit URL with slide fragment."""
        client = SlidesClient(access_token="test_token")
        url = "https://docs.google.com/presentation/d/abc123xyz/edit#slide=id.g123"
        assert client._extract_presentation_id(url) == "abc123xyz"

    def test_extract_from_trailing_slash(self) -> None:
        """Extract ID from URL with trailing slash."""
        client = SlidesClient(access_token="test_token")
        url = "https://docs.google.com/presentation/d/abc123xyz/"
        assert client._extract_presentation_id(url) == "abc123xyz"

    def test_extract_with_hyphens_and_underscores(self) -> None:
        """Extract ID containing hyphens and underscores."""
        client = SlidesClient(access_token="test_token")
        url = "https://docs.google.com/presentation/d/abc-123_xyz/edit"
        assert client._extract_presentation_id(url) == "abc-123_xyz"

    def test_invalid_url_raises(self) -> None:
        """Invalid URL raises ValueError."""
        client = SlidesClient(access_token="test_token")
        with pytest.raises(ValueError, match="Invalid Google Slides URL"):
            client._extract_presentation_id("https://example.com/not-a-slides-url")


class TestDiffS:
    """Test diff_s (dry run) functionality."""

    def test_diff_s_no_changes(self) -> None:
        """diff_s with identical SML returns empty list."""
        client = SlidesClient(access_token="test_token")
        sml = """<Presentation id="pres1">
            <Slide id="slide1"/>
        </Presentation>"""

        requests = client.diff_s(sml, sml)
        assert requests == []

    def test_diff_s_add_shape(self) -> None:
        """diff_s adding a shape returns createShape request."""
        client = SlidesClient(access_token="test_token")

        original = """<Presentation id="pres1">
            <Slide id="slide1"/>
        </Presentation>"""

        edited = """<Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100"/>
            </Slide>
        </Presentation>"""

        requests = client.diff_s(original, edited)

        create_requests = [r for r in requests if "createShape" in r]
        assert len(create_requests) == 1
        assert create_requests[0]["createShape"]["objectId"] == "rect1"

    def test_diff_s_delete_shape(self) -> None:
        """diff_s deleting a shape returns deleteObject request."""
        client = SlidesClient(access_token="test_token")

        original = """<Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100"/>
            </Slide>
        </Presentation>"""

        edited = """<Presentation id="pres1">
            <Slide id="slide1"/>
        </Presentation>"""

        requests = client.diff_s(original, edited)

        delete_requests = [r for r in requests if "deleteObject" in r]
        assert len(delete_requests) == 1
        assert delete_requests[0]["deleteObject"]["objectId"] == "rect1"

    def test_diff_s_modify_fill(self) -> None:
        """diff_s changing fill color returns updateShapeProperties."""
        client = SlidesClient(access_token="test_token")

        original = """<Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100 fill-#ffffff"/>
            </Slide>
        </Presentation>"""

        edited = """<Presentation id="pres1">
            <Slide id="slide1">
                <Rect id="rect1" class="x-100 y-100 w-200 h-100 fill-#3b82f6"/>
            </Slide>
        </Presentation>"""

        requests = client.diff_s(original, edited)

        update_requests = [r for r in requests if "updateShapeProperties" in r]
        assert len(update_requests) >= 1

    def test_diff_s_add_slide(self) -> None:
        """diff_s adding a slide returns createSlide request."""
        client = SlidesClient(access_token="test_token")

        original = """<Presentation id="pres1">
            <Slide id="slide1"/>
        </Presentation>"""

        edited = """<Presentation id="pres1">
            <Slide id="slide1"/>
            <Slide id="slide2"/>
        </Presentation>"""

        requests = client.diff_s(original, edited)

        create_requests = [r for r in requests if "createSlide" in r]
        assert len(create_requests) == 1
        assert create_requests[0]["createSlide"]["objectId"] == "slide2"


class TestClientInitialization:
    """Test client initialization."""

    def test_access_token_stored(self) -> None:
        """Access token is stored on client."""
        client = SlidesClient(access_token="test_token_123")
        assert client._access_token == "test_token_123"

    def test_credentials_manager_lazy_initialization(self) -> None:
        """CredentialsManager is not initialized until accessed."""
        client = SlidesClient(access_token="test_token")
        assert client._credentials_manager is None

    def test_no_args_creates_client(self) -> None:
        """Client can be created with no arguments (lazy initialization)."""
        client = SlidesClient()
        assert client._access_token is None
        assert client._credentials_manager is None
