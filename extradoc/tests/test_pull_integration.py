"""Integration tests for the pull workflow using golden files.

These tests demonstrate the LocalFileTransport pattern for testing
without making actual Google API calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from extradoc.client import DocsClient
from extradoc.transport import LocalFileTransport

GOLDEN_DIR = Path(__file__).parent / "golden"


@pytest.fixture
def local_transport() -> LocalFileTransport:
    """Create a transport that reads from golden files."""
    return LocalFileTransport(GOLDEN_DIR)


@pytest.fixture
def client(local_transport: LocalFileTransport) -> DocsClient:
    """Create a DocsClient with local file transport."""
    return DocsClient(local_transport)


@pytest.mark.skip(reason="Pull not yet implemented - waiting for implementation")
@pytest.mark.asyncio
async def test_pull_basic_document(
    client: DocsClient,
    local_transport: LocalFileTransport,
    tmp_path: Path,
) -> None:
    """Test pulling a basic document from golden files."""
    await client.pull(
        "basic_document",
        tmp_path,
        save_raw=True,
    )
    await local_transport.close()

    # Verify files were created
    document_dir = tmp_path / "basic_document"
    assert document_dir.exists()

    # Check document.json
    document_json = document_dir / "document.json"
    assert document_json.exists()

    # Check .raw folder was created
    raw_dir = document_dir / ".raw"
    assert raw_dir.exists()
    assert (raw_dir / "document.json").exists()

    # Check .pristine folder was created
    pristine_dir = document_dir / ".pristine"
    assert pristine_dir.exists()
    assert (pristine_dir / "document.zip").exists()


@pytest.mark.skip(reason="Pull not yet implemented - waiting for implementation")
@pytest.mark.asyncio
async def test_pull_without_raw(
    client: DocsClient,
    local_transport: LocalFileTransport,
    tmp_path: Path,
) -> None:
    """Test pulling without saving raw API responses."""
    await client.pull(
        "basic_document",
        tmp_path,
        save_raw=False,
    )
    await local_transport.close()

    document_dir = tmp_path / "basic_document"

    # Check .raw folder was NOT created
    raw_dir = document_dir / ".raw"
    assert not raw_dir.exists()

    # But document data should still be pulled
    document_json = document_dir / "document.json"
    assert document_json.exists()
