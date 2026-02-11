"""Shared test fixtures for extrascript."""

from __future__ import annotations

from pathlib import Path

import pytest

from extrascript.client import ScriptClient
from extrascript.transport import LocalFileTransport

GOLDEN_DIR = Path(__file__).parent / "golden"


@pytest.fixture
def golden_dir() -> Path:
    return GOLDEN_DIR


@pytest.fixture
def mock_client(tmp_path: Path) -> ScriptClient:
    """Create a ScriptClient that uses golden files for API responses.

    Uses LocalFileTransport to read from golden files instead of
    making real HTTP requests.
    """
    transport = LocalFileTransport(GOLDEN_DIR / "test_project")
    return ScriptClient(transport)
