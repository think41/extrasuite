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

# Actual golden file document IDs
R41_DOC_ID = "1tlHGpgjoibP0eVXRvCGSmkqrLATrXYTo7dUnmV7x01o"
SRI_DOC_ID = "1arcBS-A_LqbvrstLAADAjCZj4kvTlqmQ0ztFNfyAEyc"


@pytest.fixture
def local_transport() -> LocalFileTransport:
    """Create a transport that reads from golden files."""
    return LocalFileTransport(GOLDEN_DIR)


@pytest.fixture
def client(local_transport: LocalFileTransport) -> DocsClient:
    """Create a DocsClient with local file transport."""
    return DocsClient(local_transport)


@pytest.mark.asyncio
async def test_pull_basic_document(
    client: DocsClient,
    local_transport: LocalFileTransport,
    tmp_path: Path,
) -> None:
    """Test pulling a basic document from golden files."""
    files = await client.pull(
        R41_DOC_ID,
        tmp_path,
        save_raw=True,
    )
    await local_transport.close()

    # Verify files were created
    document_dir = tmp_path / R41_DOC_ID
    assert document_dir.exists()

    # Check document.html was created
    document_html = document_dir / "document.html"
    assert document_html.exists()

    # Verify HTML has expected structure
    html_content = document_html.read_text()
    assert "<!DOCTYPE html>" in html_content
    assert "<html>" in html_content
    assert "doc-metadata" in html_content
    assert R41_DOC_ID in html_content  # Document ID in metadata

    # Check styles.json was created
    styles_json = document_dir / "styles.json"
    assert styles_json.exists()

    # Check .raw folder was created
    raw_dir = document_dir / ".raw"
    assert raw_dir.exists()
    assert (raw_dir / "document.json").exists()

    # Check .pristine folder was created
    pristine_dir = document_dir / ".pristine"
    assert pristine_dir.exists()
    assert (pristine_dir / "document.zip").exists()

    # Verify files list includes all created files
    assert (
        len(files) == 4
    )  # document.html, styles.json, raw/document.json, pristine/document.zip
    file_names = {f.name for f in files}
    assert "document.html" in file_names
    assert "styles.json" in file_names
    assert "document.json" in file_names  # raw file
    assert "document.zip" in file_names  # pristine file


@pytest.mark.asyncio
async def test_pull_without_raw(
    client: DocsClient,
    local_transport: LocalFileTransport,
    tmp_path: Path,
) -> None:
    """Test pulling without saving raw API responses."""
    files = await client.pull(
        R41_DOC_ID,
        tmp_path,
        save_raw=False,
    )
    await local_transport.close()

    document_dir = tmp_path / R41_DOC_ID

    # Check .raw folder was NOT created
    raw_dir = document_dir / ".raw"
    assert not raw_dir.exists()

    # But document.html and styles.json should still be pulled
    assert (document_dir / "document.html").exists()
    assert (document_dir / "styles.json").exists()

    # Pristine should still exist
    assert (document_dir / ".pristine" / "document.zip").exists()

    # Only 3 files (no raw)
    assert len(files) == 3


@pytest.mark.asyncio
async def test_pull_preserves_html_content(
    client: DocsClient,
    local_transport: LocalFileTransport,
    tmp_path: Path,
) -> None:
    """Test that pulled HTML contains expected content elements."""
    await client.pull(
        R41_DOC_ID,
        tmp_path,
        save_raw=False,
    )
    await local_transport.close()

    document_dir = tmp_path / R41_DOC_ID
    html_content = (document_dir / "document.html").read_text()

    # Check for basic HTML structure
    assert "<head>" in html_content
    assert "<body>" in html_content
    assert "<main>" in html_content

    # Check for common elements
    # hr is common in documents
    assert "<hr/>" in html_content or "<p>" in html_content


@pytest.mark.asyncio
async def test_diff_no_changes(
    client: DocsClient,
    local_transport: LocalFileTransport,
    tmp_path: Path,
) -> None:
    """Test diff shows no changes immediately after pull."""
    await client.pull(
        R41_DOC_ID,
        tmp_path,
        save_raw=True,
    )
    await local_transport.close()

    document_dir = tmp_path / R41_DOC_ID

    # Run diff on the freshly pulled document
    diff_result, requests, validation = client.diff(document_dir)

    # Should have no changes
    assert diff_result.document_id == R41_DOC_ID
    assert not diff_result.has_changes
    assert len(requests) == 0
    assert validation.can_push


@pytest.mark.asyncio
async def test_push_no_changes(
    client: DocsClient,
    local_transport: LocalFileTransport,
    tmp_path: Path,
) -> None:
    """Test push works with no changes (noop)."""
    await client.pull(
        R41_DOC_ID,
        tmp_path,
        save_raw=True,
    )

    document_dir = tmp_path / R41_DOC_ID

    # Push without changes
    result = await client.push(document_dir)
    await local_transport.close()

    # Should succeed with 0 changes
    assert result.success
    assert result.document_id == R41_DOC_ID
    assert result.changes_applied == 0
    assert "No changes" in result.message
