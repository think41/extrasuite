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
        "text_replace": [
            {
                "deleteContentRange": {
                    "range": {"startIndex": 1, "endIndex": 16, "tabId": "t.0"}
                }
            },
            {
                "insertText": {
                    "location": {"index": 1, "tabId": "t.0"},
                    "text": "omega paragraph",
                }
            },
        ],
        "paragraph_split": [
            {
                "deleteContentRange": {
                    "range": {"startIndex": 1, "endIndex": 11, "tabId": "t.0"}
                }
            },
            {
                "insertText": {
                    "location": {"index": 1, "tabId": "t.0"},
                    "text": "alpha\nbeta",
                }
            },
        ],
        "table_cell_text_replace": [
            {
                "deleteContentRange": {
                    "range": {"startIndex": 11, "endIndex": 16, "tabId": "t.0"}
                }
            },
            {
                "insertText": {
                    "location": {"index": 11, "tabId": "t.0"},
                    "text": "omega",
                }
            },
        ],
        "named_range_add": [
            {
                "createNamedRange": {
                    "name": "spike:bravo",
                    "range": {"startIndex": 7, "endIndex": 12, "tabId": "t.0"},
                }
            }
        ],
        "table_row_insert": [
            {
                "insertTableRow": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 1,
                        "columnIndex": 0,
                    },
                    "insertBelow": True,
                }
            }
        ],
        "table_row_delete": [
            {
                "deleteTableRow": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 2,
                        "columnIndex": 0,
                    }
                }
            }
        ],
        "table_column_insert": [
            {
                "insertTableColumn": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 0,
                        "columnIndex": 1,
                    },
                    "insertRight": True,
                }
            }
        ],
        "table_column_delete": [
            {
                "deleteTableColumn": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 0,
                        "columnIndex": 2,
                    }
                }
            }
        ],
        "table_merge_cells": [
            {
                "mergeTableCells": {
                    "tableRange": {
                        "tableCellLocation": {
                            "tableStartLocation": {"index": 2, "tabId": "t.0"},
                            "rowIndex": 0,
                            "columnIndex": 0,
                        },
                        "rowSpan": 1,
                        "columnSpan": 2,
                    }
                }
            }
        ],
        "table_unmerge_cells": [
            {
                "unmergeTableCells": {
                    "tableRange": {
                        "tableCellLocation": {
                            "tableStartLocation": {"index": 2, "tabId": "t.0"},
                            "rowIndex": 0,
                            "columnIndex": 0,
                        },
                        "rowSpan": 1,
                        "columnSpan": 2,
                    }
                }
            }
        ],
    }

    for name, expected in cases.items():
        base, desired = _load_fixture_pair(name)
        assert lower_semantic_diff(base, desired) == expected

    header_base, header_desired = _load_fixture_pair("header_text_replace")
    header_requests = lower_semantic_diff(header_base, header_desired)
    header_id = next(
        iter(header_base.tabs[0].document_tab.headers)
    )
    assert header_requests == [
        {
            "deleteContentRange": {
                "range": {
                    "startIndex": 0,
                    "endIndex": 12,
                    "tabId": "t.0",
                    "segmentId": header_id,
                }
            }
        },
        {
            "insertText": {
                "location": {
                    "index": 0,
                    "tabId": "t.0",
                    "segmentId": header_id,
                },
                "text": "Header Omega",
            }
        },
    ]


def _load_fixture_pair(name: str) -> tuple[Document, Document]:
    fixture_dir = FIXTURES_ROOT / name
    base = Document.model_validate(json.loads((fixture_dir / "base.json").read_text()))
    desired = Document.model_validate(
        json.loads((fixture_dir / "desired.json").read_text())
    )
    return base, desired
