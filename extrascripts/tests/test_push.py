"""Tests for the push command."""

from __future__ import annotations

from pathlib import Path

import pytest

from extrascripts.client import ScriptsClient


@pytest.mark.asyncio
async def test_push_success(client: ScriptsClient, tmp_path: Path) -> None:
    """Push should succeed with valid project files."""
    await client.pull("test_project", tmp_path)
    folder = tmp_path / "test_project"

    # Modify a file
    code_gs = folder / "Code.gs"
    code_gs.write_text(code_gs.read_text() + "\n// updated\n")

    result = await client.push(folder)
    assert result.success
    assert result.files_pushed > 0
    assert result.script_id == "test_project"


@pytest.mark.asyncio
async def test_push_fails_without_manifest(
    client: ScriptsClient, tmp_path: Path
) -> None:
    """Push should fail if appsscript.json is missing."""
    await client.pull("test_project", tmp_path)
    folder = tmp_path / "test_project"

    # Remove manifest
    (folder / "appsscript.json").unlink()

    result = await client.push(folder)
    assert not result.success
    assert "appsscript.json" in result.message


@pytest.mark.asyncio
async def test_push_updates_pristine(client: ScriptsClient, tmp_path: Path) -> None:
    """Push should update .pristine to match current state."""
    await client.pull("test_project", tmp_path)
    folder = tmp_path / "test_project"

    # Modify a file
    code_gs = folder / "Code.gs"
    code_gs.write_text(code_gs.read_text() + "\n// updated\n")

    await client.push(folder)

    # After push, diff should show no changes
    diff_result = client.diff(folder)
    assert not diff_result.has_changes


@pytest.mark.asyncio
async def test_push_no_files(client: ScriptsClient, tmp_path: Path) -> None:
    """Push should fail if no script files are found."""
    await client.pull("test_project", tmp_path)
    folder = tmp_path / "test_project"

    # Remove all script files (but keep project.json and dirs)
    for f in folder.iterdir():
        if f.is_file() and f.name != "project.json":
            f.unlink()

    result = await client.push(folder)
    assert not result.success
    assert "No script files" in result.message
