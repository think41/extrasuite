"""Integration tests for the pull workflow using golden files.

These tests demonstrate the LocalFileTransport pattern for testing
without making actual Google API calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from extrasheet.client import SheetsClient
from extrasheet.transport import LocalFileTransport

GOLDEN_DIR = Path(__file__).parent / "golden"


@pytest.fixture
def local_transport() -> LocalFileTransport:
    """Create a transport that reads from golden files."""
    return LocalFileTransport(GOLDEN_DIR)


@pytest.fixture
def client(local_transport: LocalFileTransport) -> SheetsClient:
    """Create a SheetsClient with local file transport."""
    return SheetsClient(local_transport)


@pytest.mark.asyncio
async def test_pull_basic_spreadsheet(
    client: SheetsClient,
    local_transport: LocalFileTransport,
    tmp_path: Path,
) -> None:
    """Test pulling a basic spreadsheet from golden files."""
    files = await client.pull(
        "basic_spreadsheet",
        tmp_path,
        max_rows=100,
        save_raw=True,
    )
    await local_transport.close()

    # Verify files were created
    spreadsheet_dir = tmp_path / "basic_spreadsheet"
    assert spreadsheet_dir.exists()

    # Check spreadsheet.json
    spreadsheet_json = spreadsheet_dir / "spreadsheet.json"
    assert spreadsheet_json.exists()

    # Check sheet folder and data.tsv
    sheet_dir = spreadsheet_dir / "Sheet1"
    assert sheet_dir.exists()

    data_tsv = sheet_dir / "data.tsv"
    assert data_tsv.exists()

    # Verify TSV content
    content = data_tsv.read_text()
    lines = content.strip().split("\n")
    assert len(lines) == 3  # Header + 2 data rows
    assert "Name\tAge\tCity" in lines[0]
    assert "Alice\t30\tNYC" in lines[1]
    assert "Bob\t25\tLA" in lines[2]

    # Check .raw folder was created
    raw_dir = spreadsheet_dir / ".raw"
    assert raw_dir.exists()
    assert (raw_dir / "metadata.json").exists()
    assert (raw_dir / "data.json").exists()

    # Check .pristine folder was created
    pristine_dir = spreadsheet_dir / ".pristine"
    assert pristine_dir.exists()
    assert (pristine_dir / "spreadsheet.zip").exists()


@pytest.mark.asyncio
async def test_pull_without_raw(
    client: SheetsClient,
    local_transport: LocalFileTransport,
    tmp_path: Path,
) -> None:
    """Test pulling without saving raw API responses."""
    files = await client.pull(
        "basic_spreadsheet",
        tmp_path,
        max_rows=100,
        save_raw=False,
    )
    await local_transport.close()

    spreadsheet_dir = tmp_path / "basic_spreadsheet"

    # Check .raw folder was NOT created
    raw_dir = spreadsheet_dir / ".raw"
    assert not raw_dir.exists()

    # But data should still be pulled
    data_tsv = spreadsheet_dir / "Sheet1" / "data.tsv"
    assert data_tsv.exists()


@pytest.mark.asyncio
async def test_truncation_info(
    client: SheetsClient,
    local_transport: LocalFileTransport,
    tmp_path: Path,
) -> None:
    """Test that truncation info is included when max_rows < total rows."""
    # Golden file has 1000 rows, we fetch only 100
    files = await client.pull(
        "basic_spreadsheet",
        tmp_path,
        max_rows=100,
        save_raw=False,
    )
    await local_transport.close()

    # Check spreadsheet.json for truncation info
    import json

    spreadsheet_json = tmp_path / "basic_spreadsheet" / "spreadsheet.json"
    metadata = json.loads(spreadsheet_json.read_text())

    # Should have truncation info since sheet has 1000 rows but we fetched 100
    # Truncation is per-sheet in the sheets array
    sheet = metadata["sheets"][0]
    assert "truncation" in sheet
    assert sheet["truncation"]["totalRows"] == 1000
    assert sheet["truncation"]["fetchedRows"] == 100
