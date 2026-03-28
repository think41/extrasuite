from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from extradoc.api_types._generated import Document

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"


def load_fixture_pair(name: str) -> tuple[Document, Document]:
    fixture_dir = FIXTURES_ROOT / name
    base = Document.model_validate(json.loads((fixture_dir / "base.json").read_text()))
    desired = Document.model_validate(json.loads((fixture_dir / "desired.json").read_text()))
    return base, desired


def load_expected_lowered_requests(name: str) -> list[dict[str, Any]]:
    fixture_dir = FIXTURES_ROOT / name
    return json.loads((fixture_dir / "expected.lowered.json").read_text())


def load_expected_lowered_batches(name: str) -> list[list[dict[str, Any]]]:
    fixture_dir = FIXTURES_ROOT / name
    return json.loads((fixture_dir / "expected.lowered.batches.json").read_text())
