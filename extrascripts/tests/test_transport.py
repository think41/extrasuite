"""Tests for the transport layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from extrascripts.transport import LocalFileTransport


@pytest.fixture
def transport(golden_dir: Path) -> LocalFileTransport:
    return LocalFileTransport(golden_dir)


@pytest.mark.asyncio
async def test_get_project(transport: LocalFileTransport) -> None:
    """get_project should return metadata from golden file."""
    meta = await transport.get_project("test_project")
    assert meta.script_id == "test_project"
    assert meta.title == "My Test Script"
    assert meta.parent_id == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"


@pytest.mark.asyncio
async def test_get_content(transport: LocalFileTransport) -> None:
    """get_content should return all project files."""
    content = await transport.get_content("test_project")
    assert content.script_id == "test_project"
    assert len(content.files) == 4

    names = {f.name for f in content.files}
    assert names == {"Code", "Utils", "Sidebar", "appsscript"}


@pytest.mark.asyncio
async def test_get_content_file_types(transport: LocalFileTransport) -> None:
    """Files should have correct types."""
    content = await transport.get_content("test_project")
    type_map = {f.name: f.type for f in content.files}
    assert type_map["Code"] == "SERVER_JS"
    assert type_map["Utils"] == "SERVER_JS"
    assert type_map["Sidebar"] == "HTML"
    assert type_map["appsscript"] == "JSON"


@pytest.mark.asyncio
async def test_create_project(transport: LocalFileTransport) -> None:
    """create_project should return mock metadata."""
    meta = await transport.create_project("New Script", parent_id="file123")
    assert meta.title == "New Script"
    assert meta.parent_id == "file123"


@pytest.mark.asyncio
async def test_run_function(transport: LocalFileTransport) -> None:
    """run_function should return mock result."""
    result = await transport.run_function("test_project", "myFunc")
    assert result.done is True
