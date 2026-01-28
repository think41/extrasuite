"""Tests for the transport layer."""

import json
from pathlib import Path

import pytest

from extraslide import (
    LocalFileTransport,
    NotFoundError,
    PresentationData,
)

GOLDEN_DIR = Path(__file__).parent / "golden"


class TestLocalFileTransport:
    """Tests for LocalFileTransport."""

    @pytest.fixture
    def transport(self) -> LocalFileTransport:
        """Create a LocalFileTransport for testing."""
        return LocalFileTransport(GOLDEN_DIR)

    async def test_get_presentation_returns_data(
        self, transport: LocalFileTransport
    ) -> None:
        """get_presentation returns PresentationData."""
        result = await transport.get_presentation("simple_presentation")

        assert isinstance(result, PresentationData)
        assert result.presentation_id is not None
        assert result.data is not None
        assert "slides" in result.data

    async def test_get_presentation_not_found(
        self, transport: LocalFileTransport
    ) -> None:
        """get_presentation raises NotFoundError for missing file."""
        with pytest.raises(NotFoundError, match="Golden file not found"):
            await transport.get_presentation("nonexistent_presentation")

    async def test_batch_update_records_requests(
        self, transport: LocalFileTransport
    ) -> None:
        """batch_update records requests for later inspection."""
        requests = [{"createSlide": {"objectId": "slide1"}}]

        result = await transport.batch_update("test_id", requests)

        assert "replies" in result
        assert len(transport.batch_updates) == 1
        assert transport.batch_updates[0]["presentation_id"] == "test_id"
        assert transport.batch_updates[0]["requests"] == requests

    async def test_batch_update_multiple_calls(
        self, transport: LocalFileTransport
    ) -> None:
        """Multiple batch_update calls are all recorded."""
        await transport.batch_update("id1", [{"deleteObject": {"objectId": "obj1"}}])
        await transport.batch_update("id2", [{"createShape": {"objectId": "shape1"}}])

        assert len(transport.batch_updates) == 2
        assert transport.batch_updates[0]["presentation_id"] == "id1"
        assert transport.batch_updates[1]["presentation_id"] == "id2"

    async def test_close_is_noop(self, transport: LocalFileTransport) -> None:
        """close() doesn't raise."""
        await transport.close()  # Should not raise


class TestPresentationData:
    """Tests for PresentationData dataclass."""

    def test_is_frozen(self) -> None:
        """PresentationData is immutable."""
        data = PresentationData(
            presentation_id="test123",
            data={"slides": []},
        )

        with pytest.raises(AttributeError):
            data.presentation_id = "changed"  # type: ignore[misc]

    def test_fields(self) -> None:
        """PresentationData has expected fields."""
        data = PresentationData(
            presentation_id="test123",
            data={"slides": [{"objectId": "s1"}]},
        )

        assert data.presentation_id == "test123"
        assert data.data == {"slides": [{"objectId": "s1"}]}


class TestGoldenFile:
    """Tests that verify golden file structure."""

    def test_golden_file_exists(self) -> None:
        """Golden file for simple_presentation exists."""
        golden_path = GOLDEN_DIR / "simple_presentation" / "presentation.json"
        assert golden_path.exists(), f"Golden file not found: {golden_path}"

    def test_golden_file_is_valid_json(self) -> None:
        """Golden file contains valid JSON."""
        golden_path = GOLDEN_DIR / "simple_presentation" / "presentation.json"
        content = golden_path.read_text()
        data = json.loads(content)

        assert "presentationId" in data
        assert "slides" in data

    def test_golden_file_has_slides(self) -> None:
        """Golden file contains at least one slide."""
        golden_path = GOLDEN_DIR / "simple_presentation" / "presentation.json"
        data = json.loads(golden_path.read_text())

        assert len(data["slides"]) > 0
