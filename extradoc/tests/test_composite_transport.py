"""Tests for composite transport and recording mode."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from anyio import from_thread

from extradoc.composite_transport import (
    CompositeTransport,
    MismatchLogger,
    MockTransport,
)
from extradoc.mock_api import MockGoogleDocsAPI
from extradoc.transport import DocumentData


def create_minimal_document() -> dict:
    """Create a minimal valid Document."""
    return {
        "documentId": "test_doc",
        "title": "Test Document",
        "tabs": [
            {
                "tabProperties": {"tabId": "tab1", "index": 0, "title": "Tab 1"},
                "documentTab": {
                    "body": {
                        "content": [
                            {
                                "startIndex": 0,
                                "endIndex": 6,
                                "paragraph": {
                                    "elements": [
                                        {
                                            "startIndex": 0,
                                            "endIndex": 6,
                                            "textRun": {
                                                "content": "Hello\n",
                                                "textStyle": {},
                                            },
                                        }
                                    ],
                                    "paragraphStyle": {},
                                },
                            }
                        ]
                    }
                },
            }
        ],
    }


class MockRealTransport:
    """Mock implementation of a 'real' transport for testing."""

    def __init__(self, document: dict) -> None:
        self.mock_api = MockGoogleDocsAPI(document)
        self.document_id = document["documentId"]

    async def get_document(self, document_id: str) -> DocumentData:
        response = self.mock_api.get()
        return DocumentData(
            document_id=response["documentId"],
            title=response["title"],
            raw=response,
        )

    async def batch_update(
        self, document_id: str, requests: list[dict]
    ) -> dict:
        return self.mock_api.batch_update(requests)

    async def list_comments(self, file_id: str) -> list[dict]:
        return []

    async def create_reply(
        self, file_id: str, comment_id: str, content: str, action: str | None = None
    ) -> dict:
        return {"id": "reply1", "content": content}

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_mock_transport_basic():
    """Test MockTransport wraps MockGoogleDocsAPI correctly."""
    doc = create_minimal_document()
    transport = MockTransport(doc)

    # Test get_document
    data = await transport.get_document("test_doc")
    assert data.document_id == "test_doc"
    assert data.title == "Test Document"
    assert "tabs" in data.raw

    # Test batch_update
    requests = [
        {
            "insertText": {
                "location": {"index": 5},
                "text": " World",
            }
        }
    ]
    response = await transport.batch_update("test_doc", requests)
    assert "replies" in response

    # Verify the change was applied
    data_after = await transport.get_document("test_doc")
    content = data_after.raw["tabs"][0]["documentTab"]["body"]["content"][0][
        "paragraph"
    ]["elements"][0]["textRun"]["content"]
    assert content == "Hello World\n"

    await transport.close()


@pytest.mark.asyncio
async def test_composite_transport_matching_apis():
    """Test CompositeTransport when real and mock APIs match."""
    doc = create_minimal_document()

    # Create two identical mock transports to simulate matching behavior
    real_transport = MockRealTransport(doc)

    # Create composite transport with temp mismatch directory
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        mismatch_logger = MismatchLogger(Path(tmpdir))
        composite = CompositeTransport(real_transport, mismatch_logger)

        # Test get_document
        data = await composite.get_document("test_doc")
        assert data.document_id == "test_doc"
        assert data.title == "Test Document"

        # Test batch_update
        requests = [
            {
                "insertText": {
                    "location": {"index": 5},
                    "text": " World",
                }
            }
        ]
        response = await composite.batch_update("test_doc", requests)
        assert "replies" in response

        # No mismatches should be logged
        assert mismatch_logger.mismatch_count == 0
        summary = mismatch_logger.get_summary()
        assert "No mismatches" in summary

        await composite.close()


@pytest.mark.asyncio
async def test_composite_transport_mismatch_detection():
    """Test CompositeTransport detects mismatches between APIs."""
    doc = create_minimal_document()
    real_transport = MockRealTransport(doc)

    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        mismatch_logger = MismatchLogger(Path(tmpdir))
        composite = CompositeTransport(real_transport, mismatch_logger)

        # Get document (initializes mock)
        await composite.get_document("test_doc")

        # Manually corrupt the mock to create a mismatch
        # Insert different text in the mock vs real
        if composite.mock_transport:
            await composite.mock_transport.batch_update(
                "test_doc",
                [
                    {
                        "insertText": {
                            "location": {"index": 5},
                            "text": " CORRUPTED",
                        }
                    }
                ],
            )

        # Now apply different update to real
        requests = [
            {
                "insertText": {
                    "location": {"index": 5},
                    "text": " World",
                }
            }
        ]
        await composite.batch_update("test_doc", requests)

        # Mismatch should be detected
        assert mismatch_logger.mismatch_count > 0
        summary = mismatch_logger.get_summary()
        assert "mismatch" in summary.lower()

        # Verify mismatch files were created
        mismatch_dirs = list(Path(tmpdir).glob("batch_update_mismatch_*"))
        assert len(mismatch_dirs) > 0

        mismatch_dir = mismatch_dirs[0]
        assert (mismatch_dir / "metadata.json").exists()
        assert (mismatch_dir / "input_document.json").exists()
        assert (mismatch_dir / "requests.json").exists()
        assert (mismatch_dir / "real_response.json").exists()
        assert (mismatch_dir / "mock_response.json").exists()
        assert (mismatch_dir / "real_document_after.json").exists()
        assert (mismatch_dir / "mock_document_after.json").exists()

        # Verify metadata
        metadata = json.loads((mismatch_dir / "metadata.json").read_text())
        assert metadata["operation"] == "batch_update"
        assert metadata["document_id"] == "test_doc"

        await composite.close()


@pytest.mark.asyncio
async def test_mismatch_logger():
    """Test MismatchLogger creates proper log structure."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        logger = MismatchLogger(Path(tmpdir))

        # Log a batch update mismatch
        logger.log_batch_update_mismatch(
            document_id="doc1",
            requests=[{"insertText": {"location": {"index": 0}, "text": "Hi"}}],
            input_document={"documentId": "doc1", "content": "before"},
            real_response={"replies": [{"createHeader": {"headerId": "real123"}}]},
            mock_response={"replies": [{"createHeader": {"headerId": "mock456"}}]},
            real_document_after={"documentId": "doc1", "content": "after_real"},
            mock_document_after={"documentId": "doc1", "content": "after_mock"},
        )

        assert logger.mismatch_count == 1

        # Log a get mismatch
        logger.log_get_mismatch(
            document_id="doc2",
            real_response={"documentId": "doc2", "title": "Real"},
            mock_response={"documentId": "doc2", "title": "Mock"},
        )

        assert logger.mismatch_count == 2

        # Verify directory structure
        log_dirs = list(Path(tmpdir).glob("*_mismatch_*"))
        assert len(log_dirs) == 2

        # Verify summary
        summary = logger.get_summary()
        assert "2 mismatch" in summary


@pytest.mark.asyncio
async def test_composite_transport_mock_error():
    """Test CompositeTransport handles mock API errors gracefully."""
    doc = create_minimal_document()

    # Create a real transport that allows invalid operations
    # (for testing error handling)
    class PermissiveRealTransport:
        def __init__(self, document: dict) -> None:
            self.mock_api = MockGoogleDocsAPI(document)
            self.document_id = document["documentId"]

        async def get_document(self, document_id: str) -> DocumentData:
            response = self.mock_api.get()
            return DocumentData(
                document_id=response["documentId"],
                title=response["title"],
                raw=response,
            )

        async def batch_update(
            self, document_id: str, requests: list[dict]
        ) -> dict:
            # Simulate a "permissive" real API that accepts the request
            # but returns a different result than mock
            return {"replies": [{"insertText": {}}]}

        async def list_comments(self, file_id: str) -> list[dict]:
            return []

        async def create_reply(
            self, file_id: str, comment_id: str, content: str, action: str | None = None
        ) -> dict:
            return {"id": "reply1", "content": content}

        async def close(self) -> None:
            pass

    real_transport = PermissiveRealTransport(doc)

    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        mismatch_logger = MismatchLogger(Path(tmpdir))
        composite = CompositeTransport(real_transport, mismatch_logger)

        # Get document
        await composite.get_document("test_doc")

        # Try a request that makes mock fail but real succeeds
        # (inserting beyond document end)
        requests = [
            {
                "insertText": {
                    "location": {"index": 99999},  # Beyond document
                    "text": "Invalid",
                }
            }
        ]

        # This should log a mismatch because mock will error
        response = await composite.batch_update("test_doc", requests)
        assert response == {"replies": [{"insertText": {}}]}

        # Mismatch should be logged
        assert mismatch_logger.mismatch_count > 0

        # Verify error was captured
        mismatch_dirs = list(Path(tmpdir).glob("batch_update_mismatch_*"))
        assert len(mismatch_dirs) > 0

        mismatch_dir = mismatch_dirs[0]
        mock_response = json.loads(
            (mismatch_dir / "mock_response.json").read_text()
        )
        assert "error" in mock_response

        await composite.close()
