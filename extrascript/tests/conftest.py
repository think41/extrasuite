"""Shared test fixtures for extrascript."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from extrascript.client import (
    ScriptClient,
    _parse_project_content,
    _parse_project_metadata,
)

GOLDEN_DIR = Path(__file__).parent / "golden"


@pytest.fixture
def golden_dir() -> Path:
    return GOLDEN_DIR


@pytest.fixture
def mock_client(tmp_path: Path) -> ScriptClient:
    """Create a ScriptClient that uses golden files for API responses.

    This patches the private API methods to read from golden files
    instead of making real HTTP requests.
    """
    client = ScriptClient.__new__(ScriptClient)

    golden_project = GOLDEN_DIR / "test_project"

    async def mock_get_project(script_id: str) -> Any:
        path = golden_project / "project.json"
        data: dict[str, Any] = json.loads(path.read_text())
        return _parse_project_metadata(data)

    async def mock_get_content(script_id: str) -> Any:
        path = golden_project / "content.json"
        data: dict[str, Any] = json.loads(path.read_text())
        return _parse_project_content(script_id, data)

    async def mock_update_content(script_id: str, files: Any) -> Any:
        from extrascript.client import ProjectContent

        return ProjectContent(
            script_id=script_id,
            files=tuple(files),
            raw={"scriptId": script_id, "files": []},
        )

    async def mock_create_project(title: str, parent_id: str | None = None) -> Any:
        from extrascript.client import ProjectMetadata

        return ProjectMetadata(
            script_id="mock_script_id",
            title=title,
            parent_id=parent_id or "",
            raw={"scriptId": "mock_script_id", "title": title},
        )

    client._get_project = mock_get_project  # type: ignore[assignment]
    client._get_content = mock_get_content  # type: ignore[assignment]
    client._update_content = mock_update_content  # type: ignore[assignment]
    client._create_project = mock_create_project  # type: ignore[assignment]

    return client
