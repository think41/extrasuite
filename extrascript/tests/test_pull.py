"""Tests for the pull command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from extrascript.client import ScriptClient


@pytest.mark.asyncio
async def test_pull_creates_project_folder(
    mock_client: ScriptClient, tmp_path: Path
) -> None:
    """Pull should create a folder named after the script ID."""
    await mock_client.pull("test_project", tmp_path)
    project_dir = tmp_path / "test_project"
    assert project_dir.is_dir()


@pytest.mark.asyncio
async def test_pull_writes_project_json(
    mock_client: ScriptClient, tmp_path: Path
) -> None:
    """Pull should write project.json with metadata."""
    await mock_client.pull("test_project", tmp_path)
    project_json = tmp_path / "test_project" / "project.json"
    assert project_json.exists()

    data = json.loads(project_json.read_text())
    assert data["scriptId"] == "test_project"
    assert data["title"] == "My Test Script"
    assert data["parentId"] == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"


@pytest.mark.asyncio
async def test_pull_writes_gs_files(mock_client: ScriptClient, tmp_path: Path) -> None:
    """Pull should write SERVER_JS files with .gs extension."""
    await mock_client.pull("test_project", tmp_path)
    code_gs = tmp_path / "test_project" / "Code.gs"
    utils_gs = tmp_path / "test_project" / "Utils.gs"

    assert code_gs.exists()
    assert utils_gs.exists()
    assert "function onOpen" in code_gs.read_text()
    assert "function formatDate" in utils_gs.read_text()


@pytest.mark.asyncio
async def test_pull_writes_html_files(
    mock_client: ScriptClient, tmp_path: Path
) -> None:
    """Pull should write HTML files with .html extension."""
    await mock_client.pull("test_project", tmp_path)
    sidebar = tmp_path / "test_project" / "Sidebar.html"
    assert sidebar.exists()
    assert "Report Generator" in sidebar.read_text()


@pytest.mark.asyncio
async def test_pull_writes_manifest(mock_client: ScriptClient, tmp_path: Path) -> None:
    """Pull should write the appsscript.json manifest."""
    await mock_client.pull("test_project", tmp_path)
    manifest = tmp_path / "test_project" / "appsscript.json"
    assert manifest.exists()

    data = json.loads(manifest.read_text())
    assert data["runtimeVersion"] == "V8"
    assert data["timeZone"] == "America/New_York"


@pytest.mark.asyncio
async def test_pull_creates_pristine(mock_client: ScriptClient, tmp_path: Path) -> None:
    """Pull should create .pristine/project.zip."""
    await mock_client.pull("test_project", tmp_path)
    pristine = tmp_path / "test_project" / ".pristine" / "project.zip"
    assert pristine.exists()


@pytest.mark.asyncio
async def test_pull_saves_raw(mock_client: ScriptClient, tmp_path: Path) -> None:
    """Pull should save raw API responses when save_raw=True."""
    await mock_client.pull("test_project", tmp_path, save_raw=True)
    raw_content = tmp_path / "test_project" / ".raw" / "content.json"
    raw_project = tmp_path / "test_project" / ".raw" / "project.json"
    assert raw_content.exists()
    assert raw_project.exists()


@pytest.mark.asyncio
async def test_pull_no_raw(mock_client: ScriptClient, tmp_path: Path) -> None:
    """Pull should skip raw files when save_raw=False."""
    await mock_client.pull("test_project", tmp_path, save_raw=False)
    raw_dir = tmp_path / "test_project" / ".raw"
    assert not raw_dir.exists()


@pytest.mark.asyncio
async def test_pull_returns_file_list(
    mock_client: ScriptClient, tmp_path: Path
) -> None:
    """Pull should return list of all written paths."""
    files = await mock_client.pull("test_project", tmp_path)
    # project.json + 4 script files + 2 raw + 1 pristine = 8
    assert len(files) == 8
    filenames = [f.name for f in files]
    assert "project.json" in filenames
    assert "Code.gs" in filenames
    assert "Utils.gs" in filenames
    assert "Sidebar.html" in filenames
    assert "appsscript.json" in filenames
