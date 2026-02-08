"""Shared test fixtures for extrascripts."""

from __future__ import annotations

from pathlib import Path

import pytest

from extrascripts.client import ScriptsClient
from extrascripts.transport import LocalFileTransport

GOLDEN_DIR = Path(__file__).parent / "golden"


@pytest.fixture
def golden_dir() -> Path:
    return GOLDEN_DIR


@pytest.fixture
def local_transport() -> LocalFileTransport:
    return LocalFileTransport(GOLDEN_DIR)


@pytest.fixture
def client(local_transport: LocalFileTransport) -> ScriptsClient:
    return ScriptsClient(local_transport)
