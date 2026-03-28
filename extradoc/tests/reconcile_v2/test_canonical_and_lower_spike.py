from __future__ import annotations

import json
from pathlib import Path

from extradoc.api_types._generated import Document
from extradoc.reconcile_v2.api import (
    canonical_document_signature,
    canonicalize_transport_document,
    lower_semantic_diff,
)

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"


def test_section_delete_matches_section_split_base_after_canonicalization() -> None:
    section_split_base, _ = _load_fixture_pair("section_split")
    _, section_delete_desired = _load_fixture_pair("section_delete")

    assert canonical_document_signature(section_split_base) == canonical_document_signature(
        section_delete_desired
    )


def test_section_split_canonicalization_removes_carrier_paragraph_noise() -> None:
    _, desired = _load_fixture_pair("section_split")

    canonical = canonicalize_transport_document(desired)
    body = canonical.tabs[0].body

    assert len(body.sections) == 2
    assert [len(section.blocks) for section in body.sections] == [1, 1]


def test_lower_semantic_diff_for_current_fixture_slice() -> None:
    cases = {
        "paragraph_to_heading": [
            {
                "updateParagraphStyle": {
                    "range": {"startIndex": 1, "endIndex": 17, "tabId": "t.0"},
                    "paragraphStyle": {"namedStyleType": "HEADING_1"},
                    "fields": "namedStyleType",
                }
            }
        ],
        "list_append": [
            {
                "insertText": {
                    "location": {"index": 9, "tabId": "t.0"},
                    "text": "three\n",
                }
            },
            {
                "createParagraphBullets": {
                    "range": {"startIndex": 9, "endIndex": 15, "tabId": "t.0"},
                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                }
            },
        ],
        "section_split": [
            {
                "insertSectionBreak": {
                    "location": {"index": 18, "tabId": "t.0"},
                    "sectionType": "NEXT_PAGE",
                }
            }
        ],
        "section_delete": [
            {
                "deleteContentRange": {
                    "range": {"startIndex": 18, "endIndex": 20, "tabId": "t.0"}
                }
            }
        ],
        "list_kind_change": [
            {
                "deleteParagraphBullets": {
                    "range": {"startIndex": 1, "endIndex": 15, "tabId": "t.0"}
                }
            },
            {
                "createParagraphBullets": {
                    "range": {"startIndex": 1, "endIndex": 15, "tabId": "t.0"},
                    "bulletPreset": "NUMBERED_DECIMAL_ALPHA_ROMAN",
                }
            },
        ],
    }

    for name, expected in cases.items():
        base, desired = _load_fixture_pair(name)
        assert lower_semantic_diff(base, desired) == expected


def _load_fixture_pair(name: str) -> tuple[Document, Document]:
    fixture_dir = FIXTURES_ROOT / name
    base = Document.model_validate(json.loads((fixture_dir / "base.json").read_text()))
    desired = Document.model_validate(
        json.loads((fixture_dir / "desired.json").read_text())
    )
    return base, desired
