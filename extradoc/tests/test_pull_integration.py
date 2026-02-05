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

# Golden file document ID - ExtraDoc Showcase document
SHOWCASE_DOC_ID = "15dNMijQYl3juFdu8LqLvJoh3K10DREbtUm82489hgAs"


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
        SHOWCASE_DOC_ID,
        tmp_path,
        save_raw=True,
    )
    await local_transport.close()

    # Verify files were created
    document_dir = tmp_path / SHOWCASE_DOC_ID
    assert document_dir.exists()

    # Check document.xml was created
    document_xml = document_dir / "document.xml"
    assert document_xml.exists()

    # Verify XML has expected structure
    xml_content = document_xml.read_text()
    assert '<?xml version="1.0"' in xml_content
    assert "<doc " in xml_content
    assert SHOWCASE_DOC_ID in xml_content  # Document ID in doc element

    # Check styles.xml was created
    styles_xml = document_dir / "styles.xml"
    assert styles_xml.exists()

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
    )  # document.xml, styles.xml, raw/document.json, pristine/document.zip
    file_names = {f.name for f in files}
    assert "document.xml" in file_names
    assert "styles.xml" in file_names
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
        SHOWCASE_DOC_ID,
        tmp_path,
        save_raw=False,
    )
    await local_transport.close()

    document_dir = tmp_path / SHOWCASE_DOC_ID

    # Check .raw folder was NOT created
    raw_dir = document_dir / ".raw"
    assert not raw_dir.exists()

    # But document.xml and styles.xml should still be pulled
    assert (document_dir / "document.xml").exists()
    assert (document_dir / "styles.xml").exists()

    # Pristine should still exist
    assert (document_dir / ".pristine" / "document.zip").exists()

    # Only 3 files (no raw)
    assert len(files) == 3


@pytest.mark.asyncio
async def test_pull_preserves_xml_content(
    client: DocsClient,
    local_transport: LocalFileTransport,
    tmp_path: Path,
) -> None:
    """Test that pulled XML contains expected content elements."""
    await client.pull(
        SHOWCASE_DOC_ID,
        tmp_path,
        save_raw=False,
    )
    await local_transport.close()

    document_dir = tmp_path / SHOWCASE_DOC_ID
    xml_content = (document_dir / "document.xml").read_text()

    # Check for basic XML structure
    assert "<meta>" in xml_content
    assert "<body" in xml_content

    # Check for common elements (at least paragraphs should exist)
    assert "<p>" in xml_content or "<h1>" in xml_content or "<title>" in xml_content


@pytest.mark.asyncio
async def test_diff_no_changes(
    client: DocsClient,
    local_transport: LocalFileTransport,
    tmp_path: Path,
) -> None:
    """Test diff shows no changes immediately after pull."""
    await client.pull(
        SHOWCASE_DOC_ID,
        tmp_path,
        save_raw=True,
    )
    await local_transport.close()

    document_dir = tmp_path / SHOWCASE_DOC_ID

    # Run diff on the freshly pulled document
    diff_result, requests, validation = client.diff(document_dir)

    # Should have no changes
    assert diff_result.document_id == SHOWCASE_DOC_ID
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
        SHOWCASE_DOC_ID,
        tmp_path,
        save_raw=True,
    )

    document_dir = tmp_path / SHOWCASE_DOC_ID

    # Push without changes
    result = await client.push(document_dir)
    await local_transport.close()

    # Should succeed with 0 changes
    assert result.success
    assert result.document_id == SHOWCASE_DOC_ID
    assert result.changes_applied == 0
    assert "No changes" in result.message


@pytest.mark.asyncio
async def test_diff_detects_text_change(
    client: DocsClient,
    local_transport: LocalFileTransport,
    tmp_path: Path,
) -> None:
    """Test diff detects changes when document.xml is modified."""
    await client.pull(
        SHOWCASE_DOC_ID,
        tmp_path,
        save_raw=True,
    )
    await local_transport.close()

    document_dir = tmp_path / SHOWCASE_DOC_ID
    document_xml = document_dir / "document.xml"

    # Modify the document
    content = document_xml.read_text()
    modified = content.replace(
        "</body>", "<p>New paragraph added by test.</p>\n</body>"
    )
    document_xml.write_text(modified)

    # Run diff
    diff_result, requests, validation = client.diff(document_dir)

    # Should detect changes at block level
    assert diff_result.has_changes
    # Note: requests may be empty until ContentBlock request generation is implemented (Phase 3)
    # For now, we only verify that changes are detected, not that requests are generated
    # assert len(requests) > 0  # Uncomment when Phase 3 is complete
    assert validation.can_push
