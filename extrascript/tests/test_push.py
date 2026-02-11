"""Tests for the push command."""

from __future__ import annotations

from pathlib import Path

import pytest

from extrascript.client import ScriptClient


@pytest.mark.asyncio
async def test_push_success(mock_client: ScriptClient, tmp_path: Path) -> None:
    """Push should succeed with valid project files."""
    await mock_client.pull("test_project", tmp_path)
    folder = tmp_path / "test_project"

    # Modify a file
    code_gs = folder / "Code.gs"
    code_gs.write_text(code_gs.read_text() + "\n// updated\n")

    result = await mock_client.push(folder)
    assert result.success
    assert result.files_pushed > 0
    assert result.script_id == "test_project"


@pytest.mark.asyncio
async def test_push_fails_without_manifest(
    mock_client: ScriptClient, tmp_path: Path
) -> None:
    """Push should fail if appsscript.json is missing."""
    await mock_client.pull("test_project", tmp_path)
    folder = tmp_path / "test_project"

    # Remove manifest
    (folder / "appsscript.json").unlink()

    result = await mock_client.push(folder)
    assert not result.success
    assert "appsscript.json" in result.message


@pytest.mark.asyncio
async def test_push_updates_pristine(mock_client: ScriptClient, tmp_path: Path) -> None:
    """Push should update .pristine to match current state."""
    await mock_client.pull("test_project", tmp_path)
    folder = tmp_path / "test_project"

    # Modify a file
    code_gs = folder / "Code.gs"
    code_gs.write_text(code_gs.read_text() + "\n// updated\n")

    await mock_client.push(folder)

    # After push, diff should show no changes
    diff_result = mock_client.diff(folder)
    assert not diff_result.has_changes


@pytest.mark.asyncio
async def test_push_no_files(mock_client: ScriptClient, tmp_path: Path) -> None:
    """Push should fail if no script files are found."""
    await mock_client.pull("test_project", tmp_path)
    folder = tmp_path / "test_project"

    # Remove all script files (but keep project.json and dirs)
    for f in folder.iterdir():
        if f.is_file() and f.name != "project.json":
            f.unlink()

    result = await mock_client.push(folder)
    assert not result.success
    assert "No script files" in result.message
