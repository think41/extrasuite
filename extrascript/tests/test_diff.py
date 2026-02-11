"""Tests for the diff command."""

from __future__ import annotations

from pathlib import Path

import pytest

from extrascript.client import ScriptClient


@pytest.mark.asyncio
async def test_diff_no_changes(mock_client: ScriptClient, tmp_path: Path) -> None:
    """Diff should show no changes on a freshly pulled project."""
    await mock_client.pull("test_project", tmp_path)
    folder = tmp_path / "test_project"

    result = mock_client.diff(folder)
    assert not result.has_changes
    assert len(result.unchanged) > 0


@pytest.mark.asyncio
async def test_diff_modified_file(mock_client: ScriptClient, tmp_path: Path) -> None:
    """Diff should detect modified files."""
    await mock_client.pull("test_project", tmp_path)
    folder = tmp_path / "test_project"

    # Modify a file
    code_gs = folder / "Code.gs"
    code_gs.write_text(code_gs.read_text() + "\n// modified\n")

    result = mock_client.diff(folder)
    assert result.has_changes
    assert "Code.gs" in result.modified


@pytest.mark.asyncio
async def test_diff_added_file(mock_client: ScriptClient, tmp_path: Path) -> None:
    """Diff should detect newly added files."""
    await mock_client.pull("test_project", tmp_path)
    folder = tmp_path / "test_project"

    # Add a new file
    new_file = folder / "NewModule.gs"
    new_file.write_text("function newFunc() { return 42; }\n")

    result = mock_client.diff(folder)
    assert result.has_changes
    assert "NewModule.gs" in result.added


@pytest.mark.asyncio
async def test_diff_removed_file(mock_client: ScriptClient, tmp_path: Path) -> None:
    """Diff should detect removed files."""
    await mock_client.pull("test_project", tmp_path)
    folder = tmp_path / "test_project"

    # Remove Utils.gs
    (folder / "Utils.gs").unlink()

    result = mock_client.diff(folder)
    assert result.has_changes
    assert "Utils.gs" in result.removed


@pytest.mark.asyncio
async def test_diff_script_id(mock_client: ScriptClient, tmp_path: Path) -> None:
    """Diff result should include the script ID."""
    await mock_client.pull("test_project", tmp_path)
    folder = tmp_path / "test_project"

    result = mock_client.diff(folder)
    assert result.script_id == "test_project"
