from __future__ import annotations

import json
from pathlib import Path

from extradoc.api_types._generated import Document
from extradoc.reconcile import reindex_document
from extradoc.reconcile_v2.api import (
    canonicalize_transport_document,
    inspect_document,
    summarize_document,
)
from extradoc.reconcile_v2.ir import ListIR, ParagraphIR
from extradoc.serde._from_markdown import markdown_to_document


def test_parse_golden_document_into_sectioned_story_ir() -> None:
    golden_path = (
        Path(__file__).resolve().parents[1]
        / "golden"
        / "14nMj7vggV3XR3WQtYcgrABRABjKk-fqw0UQUCP25rhQ.json"
    )
    document = Document.model_validate(json.loads(golden_path.read_text()))

    parsed = inspect_document(document)

    assert len(parsed.tabs) == 3
    assert all(tab.body.sections for tab in parsed.tabs)

    summary = summarize_document(document)
    assert "tabs=3" in summary
    assert "body sections=" in summary


def test_parse_sections_attachments_and_semantic_lists() -> None:
    document = Document.model_validate(
        {
            "documentId": "doc-1",
            "revisionId": "rev-1",
            "tabs": [
                {
                    "tabProperties": {
                        "tabId": "tab-1",
                        "title": "Main",
                        "index": 0,
                    },
                    "documentTab": {
                        "lists": {
                            "list-1": {
                                "listProperties": {
                                    "nestingLevels": [{"glyphSymbol": "•"}]
                                }
                            }
                        },
                        "headers": {
                            "h-default": {
                                "headerId": "h-default",
                                "content": [
                                    {
                                        "startIndex": 0,
                                        "endIndex": 7,
                                        "paragraph": {
                                            "elements": [
                                                {
                                                    "startIndex": 0,
                                                    "endIndex": 7,
                                                    "textRun": {"content": "Head\n"},
                                                }
                                            ]
                                        },
                                    }
                                ],
                            }
                        },
                        "body": {
                            "content": [
                                {
                                    "endIndex": 1,
                                    "sectionBreak": {
                                        "sectionStyle": {
                                            "defaultHeaderId": "h-default",
                                        }
                                    },
                                },
                                {
                                    "startIndex": 1,
                                    "endIndex": 7,
                                    "paragraph": {
                                        "bullet": {"listId": "list-1", "nestingLevel": 0},
                                        "elements": [
                                            {
                                                "startIndex": 1,
                                                "endIndex": 7,
                                                "textRun": {"content": "One\n"},
                                            }
                                        ],
                                    },
                                },
                                {
                                    "startIndex": 7,
                                    "endIndex": 13,
                                    "paragraph": {
                                        "bullet": {"listId": "list-1", "nestingLevel": 1},
                                        "elements": [
                                            {
                                                "startIndex": 7,
                                                "endIndex": 13,
                                                "textRun": {"content": "Two\n"},
                                            }
                                        ],
                                    },
                                },
                                {
                                    "startIndex": 13,
                                    "endIndex": 14,
                                    "sectionBreak": {
                                        "sectionStyle": {"sectionType": "NEXT_PAGE"}
                                    },
                                },
                                {
                                    "startIndex": 14,
                                    "endIndex": 20,
                                    "paragraph": {
                                        "paragraphStyle": {"namedStyleType": "HEADING_1"},
                                        "elements": [
                                            {
                                                "startIndex": 14,
                                                "endIndex": 20,
                                                "textRun": {"content": "Tail\n"},
                                            }
                                        ],
                                    },
                                },
                            ]
                        },
                    },
                }
            ],
        }
    )

    parsed = inspect_document(document)
    tab = parsed.tabs[0]

    assert len(tab.body.sections) == 2
    assert tab.body.sections[0].attachments.headers["DEFAULT"] == "h-default"
    assert isinstance(tab.body.sections[0].blocks[0], ListIR)
    assert len(tab.body.sections[0].blocks[0].items) == 2
    assert isinstance(tab.body.sections[1].blocks[0], ParagraphIR)
    assert tab.body.sections[1].blocks[0].role == "HEADING_1"


def test_parse_named_range_into_logical_text_positions() -> None:
    document = Document.model_validate(
        {
            "documentId": "doc-2",
            "revisionId": "rev-2",
            "tabs": [
                {
                    "tabProperties": {"tabId": "tab-1", "title": "Main", "index": 0},
                    "documentTab": {
                        "namedRanges": {
                            "greeting": {
                                "name": "greeting",
                                "namedRanges": [
                                    {
                                        "name": "greeting",
                                        "namedRangeId": "nr-1",
                                        "ranges": [
                                            {"startIndex": 1, "endIndex": 6, "tabId": "tab-1"}
                                        ],
                                    }
                                ],
                            }
                        },
                        "body": {
                            "content": [
                                {"endIndex": 1, "sectionBreak": {}},
                                {
                                    "startIndex": 1,
                                    "endIndex": 13,
                                    "paragraph": {
                                        "elements": [
                                            {
                                                "startIndex": 1,
                                                "endIndex": 13,
                                                "textRun": {"content": "Hello world\n"},
                                            }
                                        ]
                                    },
                                },
                            ]
                        },
                    },
                }
            ],
        }
    )

    parsed = inspect_document(document)
    anchors = parsed.tabs[0].annotations.named_ranges["greeting"]
    assert len(anchors) == 1

    anchor = anchors[0]
    assert anchor.start.story_id == "tab-1:body"
    assert anchor.start.path.section_index == 0


def test_parse_named_range_inside_table_wrapper_resolves_to_table_boundary() -> None:
    document = reindex_document(
        markdown_to_document(
            {
                "Tab_1": (
                    "```python\n"
                    "print('hi')\n"
                    "```\n\n"
                    "```json\n"
                    "{\"ok\": true}\n"
                    "```\n"
                )
            },
            document_id="doc-3",
            title="Named Range Table Wrapper",
            tab_ids={"Tab_1": "tab-1"},
        )
    )
    raw = document.model_dump(by_alias=True, exclude_none=True)
    content = raw["tabs"][0]["documentTab"]["body"]["content"]
    tables = [element for element in content if element.get("table") is not None]
    assert len(tables) == 2

    raw["tabs"][0]["documentTab"]["namedRanges"] = {
        "extradoc:codeblock:python": {
            "name": "extradoc:codeblock:python",
            "namedRanges": [
                {
                    "name": "extradoc:codeblock:python",
                    "namedRangeId": "nr-python",
                    "ranges": [
                        {
                            "startIndex": tables[0]["startIndex"] + 2,
                            "endIndex": tables[1]["startIndex"] + 3,
                            "tabId": "tab-1",
                        }
                    ],
                }
            ],
        }
    }

    parsed = canonicalize_transport_document(Document.model_validate(raw))
    anchors = parsed.tabs[0].annotations.named_ranges["extradoc:codeblock:python"]

    assert len(anchors) == 1
    assert anchors[0].start.path.block_index == 0
    assert anchors[0].start.path.edge.value == "BEFORE"
    assert anchors[0].end.path.block_index == 1
    assert anchors[0].end.path.edge.value == "BEFORE"
