"""Tests for the diff command."""

from __future__ import annotations

from pathlib import Path

import pytest

from extrascripts.client import ScriptsClient


@pytest.mark.asyncio
async def test_diff_no_changes(client: ScriptsClient, tmp_path: Path) -> None:
    """Diff should report no changes when files are unmodified."""
    await client.pull("test_project", tmp_path)
    folder = tmp_path / "test_project"

    result = client.diff(folder)
    assert not result.has_changes
    assert result.added == []
    assert result.removed == []
    assert result.modified == []
    assert len(result.unchanged) > 0


@pytest.mark.asyncio
async def test_diff_modified_file(client: ScriptsClient, tmp_path: Path) -> None:
    """Diff should detect modified files."""
    await client.pull("test_project", tmp_path)
    folder = tmp_path / "test_project"

    # Modify Code.gs
    code_gs = folder / "Code.gs"
    code_gs.write_text(code_gs.read_text() + "\n// new comment\n")

    result = client.diff(folder)
    assert result.has_changes
    assert "Code.gs" in result.modified


@pytest.mark.asyncio
async def test_diff_added_file(client: ScriptsClient, tmp_path: Path) -> None:
    """Diff should detect newly added files."""
    await client.pull("test_project", tmp_path)
    folder = tmp_path / "test_project"

    # Add a new file
    new_file = folder / "NewModule.gs"
    new_file.write_text("function newFunc() { return 42; }\n")

    result = client.diff(folder)
    assert result.has_changes
    assert "NewModule.gs" in result.added


@pytest.mark.asyncio
async def test_diff_removed_file(client: ScriptsClient, tmp_path: Path) -> None:
    """Diff should detect removed files."""
    await client.pull("test_project", tmp_path)
    folder = tmp_path / "test_project"

    # Remove Utils.gs
    (folder / "Utils.gs").unlink()

    result = client.diff(folder)
    assert result.has_changes
    assert "Utils.gs" in result.removed


@pytest.mark.asyncio
async def test_diff_script_id(client: ScriptsClient, tmp_path: Path) -> None:
    """Diff result should include the script ID."""
    await client.pull("test_project", tmp_path)
    folder = tmp_path / "test_project"

    result = client.diff(folder)
    assert result.script_id == "test_project"
