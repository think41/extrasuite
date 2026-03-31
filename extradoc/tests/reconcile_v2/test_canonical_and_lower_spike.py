from __future__ import annotations

import json
from pathlib import Path

import pytest

import extradoc.serde as serde
from extradoc.api_types._generated import Document
from extradoc.client import _normalize_raw_base_para_styles
from extradoc.mock.api import MockGoogleDocsAPI
from extradoc.reconcile import reindex_document
from extradoc.reconcile_v2.api import (
    canonical_document_signature,
    canonicalize_transport_document,
    lower_semantic_diff,
    lower_semantic_diff_batches,
)
from extradoc.reconcile_v2.canonical import _transport_block_keep_mask
from extradoc.reconcile_v2.errors import UnsupportedSpikeError
from extradoc.reconcile_v2.executor import resolve_deferred_placeholders
from extradoc.reconcile_v2.ir import (
    BODY_CAPABILITIES,
    CellIR,
    PageBreakIR,
    ParagraphIR,
    RowIR,
    StoryIR,
    StoryKind,
    TableIR,
    TextSpanIR,
)
from extradoc.reconcile_v2.layout import build_body_layout
from extradoc.reconcile_v2.lower import _lower_blocks_into_fresh_story
from extradoc.serde._from_markdown import markdown_to_document

from .helpers import load_expected_lowered_requests

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"


def test_lower_blocks_into_fresh_story_supports_mixed_paragraph_and_nested_table() -> None:
    nested_table = TableIR(
        style={},
        pinned_header_rows=0,
        column_properties=[{}],
        merge_regions=[],
        rows=[
            RowIR(
                style={},
                cells=[
                    CellIR(
                        style={},
                        row_span=1,
                        column_span=1,
                        merge_head=None,
                        content=StoryIR(
                            id="nested-cell",
                            kind=StoryKind.TABLE_CELL,
                            capabilities=BODY_CAPABILITIES,
                            blocks=[
                                ParagraphIR(
                                    role="NORMAL_TEXT",
                                    explicit_style={},
                                    inlines=[TextSpanIR(text="Inner", explicit_text_style={})],
                                )
                            ],
                        ),
                    )
                ],
            )
        ],
    )
    blocks = [
        ParagraphIR(
            role="NORMAL_TEXT",
            explicit_style={},
            inlines=[TextSpanIR(text="Lead", explicit_text_style={})],
        ),
        nested_table,
    ]

    requests = _lower_blocks_into_fresh_story(
        blocks,
        story_start_index=1,
        tab_id="t.0",
        segment_id="seg.1",
    )

    assert requests[0]["insertTable"]["rows"] == 1
    assert requests[-1]["insertText"]["text"] == "Lead"


def _make_doc_with_toc(*, include_toc: bool) -> Document:
    content: list[dict[str, object]] = [
        {
            "startIndex": 0,
            "endIndex": 1,
            "sectionBreak": {"sectionStyle": {"columnSeparatorStyle": "NONE"}},
        },
        {
            "startIndex": 1,
            "endIndex": 7,
            "paragraph": {
                "elements": [
                    {
                        "startIndex": 1,
                        "endIndex": 7,
                        "textRun": {"content": "Title\n"},
                    }
                ],
                "paragraphStyle": {"namedStyleType": "HEADING_1"},
            },
        },
    ]
    if include_toc:
        content.append(
            {
                "startIndex": 7,
                "endIndex": 10,
                "tableOfContents": {
                    "content": [
                        {
                            "startIndex": 8,
                            "endIndex": 10,
                            "paragraph": {
                                "elements": [
                                    {
                                        "startIndex": 8,
                                        "endIndex": 10,
                                        "textRun": {"content": "\n"},
                                    }
                                ]
                            },
                        }
                    ]
                },
            }
        )
        body_start = 10
    else:
        body_start = 7
    content.append(
        {
            "startIndex": body_start,
            "endIndex": body_start + 8,
            "paragraph": {
                "elements": [
                    {
                        "startIndex": body_start,
                        "endIndex": body_start + 8,
                        "textRun": {"content": "Body...\n"},
                    }
                ]
            },
        }
    )
    return Document.model_validate(
        {
            "documentId": "toc-test",
            "tabs": [
                {
                    "tabProperties": {"tabId": "t.0", "title": "Tab 1", "index": 0},
                    "documentTab": {"body": {"content": content}},
                }
            ],
        }
    )


def _make_doc_with_toc_and_table(
    *,
    intro_text: str | None = None,
    include_table: bool = True,
    tail_text: str = "Tail",
) -> Document:
    content: list[dict[str, object]] = [
        {
            "endIndex": 1,
            "sectionBreak": {"sectionStyle": {"columnSeparatorStyle": "NONE"}},
        }
    ]
    cursor = 1
    if intro_text is not None:
        intro = f"{intro_text}\n"
        content.append(
            {
                "startIndex": cursor,
                "endIndex": cursor + len(intro),
                "paragraph": {
                    "elements": [
                        {
                            "startIndex": cursor,
                            "endIndex": cursor + len(intro),
                            "textRun": {"content": intro},
                        }
                    ]
                },
            }
        )
        cursor += len(intro)
    content.append(
        {
            "startIndex": cursor,
            "endIndex": cursor + 3,
            "tableOfContents": {
                "content": [
                    {
                        "startIndex": cursor + 1,
                        "endIndex": cursor + 3,
                        "paragraph": {
                            "elements": [
                                {
                                    "startIndex": cursor + 1,
                                    "endIndex": cursor + 3,
                                    "textRun": {"content": "\n"},
                                }
                            ]
                        },
                    }
                ]
            },
        }
    )
    cursor += 3
    if include_table:
        content.append(
            {
                "startIndex": cursor,
                "endIndex": cursor + 10,
                "table": {
                    "rows": 1,
                    "columns": 1,
                    "tableRows": [
                        {
                            "startIndex": cursor + 1,
                            "endIndex": cursor + 9,
                            "tableCells": [
                                {
                                    "startIndex": cursor + 2,
                                    "endIndex": cursor + 9,
                                    "content": [
                                        {
                                            "startIndex": cursor + 3,
                                            "endIndex": cursor + 8,
                                            "paragraph": {
                                                "elements": [
                                                    {
                                                        "startIndex": cursor + 3,
                                                        "endIndex": cursor + 7,
                                                        "textRun": {"content": "code"},
                                                    },
                                                    {
                                                        "startIndex": cursor + 7,
                                                        "endIndex": cursor + 8,
                                                        "textRun": {"content": "\n"},
                                                    },
                                                ]
                                            },
                                        },
                                        {
                                            "startIndex": cursor + 8,
                                            "endIndex": cursor + 9,
                                            "paragraph": {
                                                "elements": [
                                                    {
                                                        "startIndex": cursor + 8,
                                                        "endIndex": cursor + 9,
                                                        "textRun": {"content": "\n"},
                                                    }
                                                ]
                                            },
                                        },
                                    ],
                                    "tableCellStyle": {},
                                }
                            ],
                        }
                    ],
                },
            }
        )
        cursor += 10
    tail = f"{tail_text}\n"
    content.append(
        {
            "startIndex": cursor,
            "endIndex": cursor + len(tail),
            "paragraph": {
                "elements": [
                    {
                        "startIndex": cursor,
                        "endIndex": cursor + len(tail),
                        "textRun": {"content": tail},
                    }
                ]
            },
        }
    )
    return Document.model_validate(
        {
            "documentId": "toc-table-test",
            "tabs": [
                {
                    "tabProperties": {"tabId": "t.0", "title": "Tab 1", "index": 0},
                    "documentTab": {"body": {"content": content}},
                }
            ],
        }
    )


def _make_doc_with_named_range(
    *,
    text: str,
    range_name: str | None = None,
    target_text: str = "bravo",
) -> Document:
    text_with_newline = text if text.endswith("\n") else f"{text}\n"
    raw: dict[str, object] = {
        "documentId": "named-range-test",
        "tabs": [
            {
                "tabProperties": {"tabId": "t.0", "title": "Tab 1", "index": 0},
                "documentTab": {
                    "body": {
                        "content": [
                            {
                                "endIndex": 1,
                                "sectionBreak": {
                                    "sectionStyle": {"columnSeparatorStyle": "NONE"}
                                },
                            },
                            {
                                "startIndex": 1,
                                "endIndex": 1 + len(text_with_newline),
                                "paragraph": {
                                    "elements": [
                                        {
                                            "startIndex": 1,
                                            "endIndex": 1 + len(text_with_newline),
                                            "textRun": {"content": text_with_newline},
                                        }
                                    ]
                                },
                            },
                        ]
                    }
                },
            }
        ],
    }
    if range_name is not None:
        start_index = text.index(target_text) + 1
        end_index = start_index + len(target_text)
        raw["tabs"][0]["documentTab"]["namedRanges"] = {
            range_name: {
                "namedRanges": [
                    {
                        "namedRangeId": "nr.synthetic",
                        "name": range_name,
                        "ranges": [
                            {"startIndex": start_index, "endIndex": end_index}
                        ],
                    }
                ]
            }
        }
    return Document.model_validate(raw)


def _make_single_tab_doc(*, paragraphs: list[str]) -> Document:
    content: list[dict[str, object]] = [
        {
            "endIndex": 1,
            "sectionBreak": {"sectionStyle": {"columnSeparatorStyle": "NONE"}},
        }
    ]
    cursor = 1
    for paragraph_text in paragraphs or [""]:
        text = f"{paragraph_text}\n"
        content.append(
            {
                "startIndex": cursor,
                "endIndex": cursor + len(text),
                "paragraph": {
                    "elements": [
                        {
                            "startIndex": cursor,
                            "endIndex": cursor + len(text),
                            "textRun": {"content": text},
                        }
                    ]
                },
            }
        )
        cursor += len(text)
    return Document.model_validate(
        {
            "documentId": "paragraph-doc",
            "tabs": [
                {
                    "tabProperties": {"tabId": "t.0", "title": "Tab 1", "index": 0},
                    "documentTab": {"body": {"content": content}},
                }
            ],
        }
    )


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


def test_canonicalization_strips_styled_empty_table_carrier_paragraph() -> None:
    transport = Document.model_validate(
        {
            "documentId": "styled-carrier",
            "title": "Styled Carrier",
            "tabs": [
                {
                    "tabProperties": {"tabId": "t.0", "title": "Tab 1", "index": 0},
                    "documentTab": {
                        "body": {
                            "content": [
                                {
                                    "startIndex": 0,
                                    "endIndex": 1,
                                    "sectionBreak": {"sectionStyle": {"columnSeparatorStyle": "NONE"}},
                                },
                                {
                                    "startIndex": 1,
                                    "endIndex": 8,
                                    "paragraph": {
                                        "elements": [
                                            {
                                                "startIndex": 1,
                                                "endIndex": 8,
                                                "textRun": {"content": "Title\n"},
                                            }
                                        ],
                                        "paragraphStyle": {"namedStyleType": "HEADING_1"},
                                    },
                                },
                                {
                                    "startIndex": 8,
                                    "endIndex": 9,
                                    "paragraph": {
                                        "elements": [
                                            {
                                                "startIndex": 8,
                                                "endIndex": 9,
                                                "textRun": {"content": "\n"},
                                            }
                                        ],
                                        "paragraphStyle": {"namedStyleType": "HEADING_2"},
                                    },
                                },
                                {
                                    "startIndex": 9,
                                    "endIndex": 13,
                                    "table": {
                                        "rows": 1,
                                        "columns": 1,
                                        "tableRows": [
                                            {
                                                "tableCells": [
                                                    {
                                                        "content": [
                                                            {
                                                                "startIndex": 10,
                                                                "endIndex": 12,
                                                                "paragraph": {
                                                                    "elements": [
                                                                        {
                                                                            "startIndex": 10,
                                                                            "endIndex": 12,
                                                                            "textRun": {"content": "x\n"},
                                                                        }
                                                                    ]
                                                                },
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ],
                                    },
                                },
                            ]
                        }
                    },
                }
            ],
        }
    )

    canonical = canonicalize_transport_document(transport)

    assert [type(block).__name__ for block in canonical.tabs[0].body.sections[0].blocks] == [
        "ParagraphIR",
        "TableIR",
    ]


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
        "list_relevel": load_expected_lowered_requests("list_relevel"),
        "multitab_text_replace": load_expected_lowered_requests("multitab_text_replace"),
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
        "named_range_delete": [
            {
                "deleteNamedRange": {"name": "spike:bravo"}
            }
        ],
        "named_range_move_with_text_edit": [
            {
                "deleteContentRange": {
                    "range": {"startIndex": 1, "endIndex": 20, "tabId": "t.0"}
                }
            },
            {
                "insertText": {
                    "location": {"index": 1, "tabId": "t.0"},
                    "text": "alpha bravo charlie delta",
                }
            },
            {"deleteNamedRange": {"name": "spike:target"}},
            {
                "createNamedRange": {
                    "name": "spike:target",
                    "range": {"startIndex": 21, "endIndex": 26, "tabId": "t.0"},
                }
            },
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
        "table_middle_row_insert": [
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
        "table_middle_row_delete": [
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
        "table_middle_column_insert": [
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
        "table_middle_column_delete": [
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
        "table_middle_row_insert_with_cell_edit": [
            {
                "deleteContentRange": {
                    "range": {"startIndex": 34, "endIndex": 41, "tabId": "t.0"}
                }
            },
            {
                "insertText": {
                    "location": {"index": 34, "tabId": "t.0"},
                    "text": "omega",
                }
            },
            {
                "insertTableRow": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 1,
                        "columnIndex": 0,
                    },
                    "insertBelow": True,
                }
            },
        ],
        "table_middle_row_insert_with_inserted_content": [
            {
                "insertTableRow": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 1,
                        "columnIndex": 0,
                    },
                    "insertBelow": True,
                }
            },
            {
                "insertText": {
                    "location": {"index": 34, "tabId": "t.0"},
                    "text": "NEW",
                }
            },
        ],
        "table_row_insert_below_merged": [
            {
                "insertTableRow": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 0,
                        "columnIndex": 0,
                    },
                    "insertBelow": True,
                }
            }
        ],
        "table_middle_column_insert_with_inserted_content": [
            {
                "insertTableColumn": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 2, "tabId": "t.0"},
                        "rowIndex": 0,
                        "columnIndex": 1,
                    },
                    "insertRight": True,
                }
            },
            {
                "insertText": {
                    "location": {"index": 39, "tabId": "t.0"},
                    "text": "NEW",
                }
            },
        ],
        "table_pin_header_rows": [
            {
                "pinTableHeaderRows": {
                    "tableStartLocation": {"index": 2, "tabId": "t.0"},
                    "pinnedHeaderRowsCount": 1,
                }
            }
        ],
        "table_row_style_min_height": [
            {
                "updateTableRowStyle": {
                    "tableStartLocation": {"index": 2, "tabId": "t.0"},
                    "rowIndices": [1],
                    "tableRowStyle": {
                        "minRowHeight": {"magnitude": 30.0, "unit": "PT"}
                    },
                    "fields": "minRowHeight",
                }
            }
        ],
        "table_column_properties_width": [
            {
                "updateTableColumnProperties": {
                    "tableStartLocation": {"index": 2, "tabId": "t.0"},
                    "columnIndices": [1],
                    "tableColumnProperties": {
                        "width": {"magnitude": 72.0, "unit": "PT"},
                        "widthType": "FIXED_WIDTH",
                    },
                    "fields": "width,widthType",
                }
            }
        ],
        "table_cell_style_background": [
            {
                "updateTableCellStyle": {
                    "tableRange": {
                        "tableCellLocation": {
                            "tableStartLocation": {"index": 2, "tabId": "t.0"},
                            "rowIndex": 1,
                            "columnIndex": 1,
                        },
                        "rowSpan": 1,
                        "columnSpan": 1,
                    },
                    "tableCellStyle": {
                        "backgroundColor": {
                            "color": {"rgbColor": {"red": 1.0}}
                        }
                    },
                    "fields": "backgroundColor",
                }
            }
        ],
        "table_row_and_column_insert": load_expected_lowered_requests(
            "table_row_and_column_insert"
        ),
    }

    for name, expected in cases.items():
        base, desired = _load_fixture_pair(name)
        assert lower_semantic_diff(base, desired) == expected


def test_lower_semantic_diff_preserves_inserted_heading_and_link_styles() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": ""},
            document_id="style-insert",
            title="Style Insert",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {"Tab_1": "# Delivery Plan\n\nSee [spec](https://example.com).\n"},
            document_id="style-insert",
            title="Style Insert",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    batches = lower_semantic_diff_batches(base, desired, transport_base=base)
    requests = [request for batch in batches for request in batch]

    assert requests == [
        {
            "insertText": {
                "location": {"index": 1, "tabId": "t.0"},
                "text": "Delivery Plan\nSee spec.",
            }
        },
        {
            "updateParagraphStyle": {
                "range": {"startIndex": 1, "endIndex": 15, "tabId": "t.0"},
                "paragraphStyle": {"namedStyleType": "HEADING_1"},
                "fields": "namedStyleType",
            }
        },
        {
            "updateTextStyle": {
                "range": {"startIndex": 19, "endIndex": 23, "tabId": "t.0"},
                "textStyle": {"link": {"url": "https://example.com"}},
                "fields": "link",
            }
        },
    ]


def test_lower_semantic_diff_supports_mixed_section_list_insert() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": "Intro\n"},
            document_id="mixed-list-insert",
            title="Mixed List Insert",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {"Tab_1": "Intro\n\n- one\n- two\n"},
            document_id="mixed-list-insert",
            title="Mixed List Insert",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    assert lower_semantic_diff(base, desired) == [
        {
            "insertText": {
                "location": {"index": 7, "tabId": "t.0"},
                "text": "one\ntwo\n",
            }
        },
        {
            "createParagraphBullets": {
                "range": {"startIndex": 7, "endIndex": 15, "tabId": "t.0"},
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
            }
        },
    ]


def test_lower_semantic_diff_supports_mixed_section_list_delete() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": "Intro\n\n- one\n- two\n"},
            document_id="mixed-list-delete",
            title="Mixed List Delete",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {"Tab_1": "Intro\n"},
            document_id="mixed-list-delete",
            title="Mixed List Delete",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    assert lower_semantic_diff(base, desired) == [
        {
            "deleteContentRange": {
                "range": {"startIndex": 7, "endIndex": 15, "tabId": "t.0"}
            }
        }
    ]


def test_lower_semantic_diff_supports_paragraph_list_replacement() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": "Alpha\n"},
            document_id="replace-paragraph-with-list",
            title="Replace Paragraph With List",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {"Tab_1": "- one\n- two\n"},
            document_id="replace-paragraph-with-list",
            title="Replace Paragraph With List",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    assert lower_semantic_diff(base, desired) == [
        {
            "deleteContentRange": {
                "range": {"startIndex": 1, "endIndex": 6, "tabId": "t.0"}
            }
        },
        {
            "insertText": {
                "location": {"index": 1, "tabId": "t.0"},
                "text": "one\ntwo\n",
            }
        },
        {
            "createParagraphBullets": {
                "range": {"startIndex": 1, "endIndex": 9, "tabId": "t.0"},
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
            }
        },
    ]


def test_lower_semantic_diff_supports_table_insert_between_paragraphs() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": "Alpha\n\nOmega\n"},
            document_id="insert-table-between-paragraphs",
            title="Insert Table Between Paragraphs",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {"Tab_1": "Alpha\n\n```\ncode\n```\n\nOmega\n"},
            document_id="insert-table-between-paragraphs",
            title="Insert Table Between Paragraphs",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    assert lower_semantic_diff(base, desired) == [
        {
            "insertTable": {
                "rows": 1,
                "columns": 1,
                "location": {"index": 7, "tabId": "t.0"},
            }
        },
        {
            "insertText": {
                "location": {"index": 11, "tabId": "t.0"},
                "text": "code",
            }
        },
        {
            "updateTextStyle": {
                "range": {"startIndex": 11, "endIndex": 15, "tabId": "t.0"},
                "textStyle": {
                    "fontSize": {"magnitude": 10.0, "unit": "PT"},
                    "weightedFontFamily": {"fontFamily": "Courier New"},
                },
                "fields": "fontSize,weightedFontFamily",
            }
        },
        {
            "createNamedRange": {
                "name": "extradoc:codeblock",
                "range": {"startIndex": 7, "endIndex": 13, "tabId": "t.0"},
            }
        },
    ]


def test_lower_semantic_diff_supports_paragraph_table_replacement() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": "Alpha\n"},
            document_id="replace-paragraph-with-table",
            title="Replace Paragraph With Table",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {"Tab_1": "```\ncode\n```\n"},
            document_id="replace-paragraph-with-table",
            title="Replace Paragraph With Table",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    assert lower_semantic_diff(base, desired) == [
        {
            "deleteContentRange": {
                "range": {"startIndex": 1, "endIndex": 6, "tabId": "t.0"}
            }
        },
        {
            "insertTable": {
                "rows": 1,
                "columns": 1,
                "location": {"index": 1, "tabId": "t.0"},
            }
        },
        {
            "insertText": {
                "location": {"index": 5, "tabId": "t.0"},
                "text": "code",
            }
        },
        {
            "updateTextStyle": {
                "range": {"startIndex": 5, "endIndex": 9, "tabId": "t.0"},
                "textStyle": {
                    "fontSize": {"magnitude": 10.0, "unit": "PT"},
                    "weightedFontFamily": {"fontFamily": "Courier New"},
                },
                "fields": "fontSize,weightedFontFamily",
            }
        },
            {
                "createNamedRange": {
                    "name": "extradoc:codeblock",
                    "range": {"startIndex": 2, "endIndex": 11, "tabId": "t.0"},
                }
            },
        ]


def test_lower_semantic_diff_supports_table_paragraph_replacement() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": "```\ncode\n```\n"},
            document_id="replace-table-with-paragraph",
            title="Replace Table With Paragraph",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {"Tab_1": "Alpha\n"},
            document_id="replace-table-with-paragraph",
            title="Replace Table With Paragraph",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    assert lower_semantic_diff(base, desired) == [
        {
            "deleteContentRange": {
                "range": {"startIndex": 1, "endIndex": 11, "tabId": "t.0"}
            }
        },
        {
            "insertText": {
                "location": {"index": 1, "tabId": "t.0"},
                "text": "Alpha",
            }
        },
    ]


def test_lower_semantic_diff_supports_paragraph_insert_before_table() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": "```\ncode\n```\n"},
            document_id="insert-paragraph-before-table",
            title="Insert Paragraph Before Table",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {"Tab_1": "Lead\n\n```\ncode\n```\n"},
            document_id="insert-paragraph-before-table",
            title="Insert Paragraph Before Table",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    assert lower_semantic_diff(base, desired) == [
        {
            "insertText": {
                "location": {"index": 1, "tabId": "t.0"},
                "text": "Lead\n",
            }
        },
        {
            "createNamedRange": {
                "name": "extradoc:codeblock",
                "range": {"startIndex": 6, "endIndex": 16, "tabId": "t.0"},
            }
        },
    ]


def test_lower_semantic_diff_supports_empty_body_mixed_sequence() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": ""},
            document_id="mixed-empty-body-insert",
            title="Mixed Empty Body Insert",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {
                "Tab_1": (
                    "# Mixed Body QA\n\n"
                    "Lead paragraph.\n\n"
                    "- first bullet\n"
                    "- second bullet\n\n"
                    "```python\n"
                    "print('hi')\n"
                    "```\n\n"
                    "Closing paragraph.\n"
                )
            },
            document_id="mixed-empty-body-insert",
            title="Mixed Empty Body Insert",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    requests = lower_semantic_diff(base, desired)

    text_requests = [
        request["insertText"]
        for request in requests
        if "insertText" in request
    ]

    assert any(
        request["location"]["index"] == 1
        and request["text"].startswith("Mixed Body QA")
        for request in text_requests
    )
    assert any(
        request["location"]["index"] == 1
        and request["text"].startswith("Closing paragraph.")
        for request in text_requests
    )
    assert any("insertTable" in request for request in requests)
    assert any("createParagraphBullets" in request for request in requests)
    assert any("updateParagraphStyle" in request for request in requests)
    create_named_range = next(
        request["createNamedRange"] for request in requests if "createNamedRange" in request
    )
    assert create_named_range["name"] == "extradoc:codeblock:python"
    assert create_named_range["range"]["startIndex"] < create_named_range["range"]["endIndex"]

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


def test_lower_semantic_diff_supports_dense_empty_body_markdown_insert() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": ""},
            document_id="dense-empty-body-insert",
            title="Dense Empty Body Insert",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {
                "Tab_1": (
                    "# Stress Doc\n\n"
                    "Lead with **bold**, *italic*, ~~strike~~, <u>underline</u>, "
                    "`code`, and a [link](https://example.com).\n\n"
                    "## Matrix\n\n"
                    "| A | B |\n"
                    "| --- | --- |\n"
                    "| one | two |\n\n"
                    "## Narrative\n\n"
                    "> Block quote line one.\n"
                    ">\n"
                    "> Block quote line two.\n\n"
                    "> [!INFO]\n"
                    "> Info callout.\n\n"
                    "> [!WARNING]\n"
                    "> Warning callout.\n\n"
                    "### Tasks\n\n"
                    "- first bullet\n"
                    "- second bullet\n\n"
                    "1. first number\n"
                    "2. second number\n\n"
                    "- [x] checked\n"
                    "- [ ] pending\n\n"
                    "## Code\n\n"
                    "```python\n"
                    "print('hi')\n"
                    "```\n\n"
                    "```json\n"
                    "{\"ok\": true}\n"
                    "```\n\n"
                    "## Closing\n\n"
                    "| Area | Status |\n"
                    "| --- | --- |\n"
                    "| lowering | green |\n"
                )
            },
            document_id="dense-empty-body-insert",
            title="Dense Empty Body Insert",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    requests = lower_semantic_diff(base, desired)
    layout = build_body_layout(desired, tab_id="t.0")

    assert [type(block).__name__ for block in layout.sections[0].block_locations] == [
        "ParagraphLocation",
        "ParagraphLocation",
        "ParagraphLocation",
        "TableLocation",
        "ParagraphLocation",
        "TableLocation",
        "TableLocation",
        "TableLocation",
        "ParagraphLocation",
        "ListLocation",
        "ListLocation",
        "ListLocation",
        "ParagraphLocation",
        "TableLocation",
        "TableLocation",
        "ParagraphLocation",
        "TableLocation",
    ]
    assert sum(1 for request in requests if "insertTable" in request) >= 5
    named_ranges = {
        request["createNamedRange"]["name"]
        for request in requests
        if "createNamedRange" in request
    }
    assert {
        "extradoc:blockquote",
        "extradoc:callout:info",
        "extradoc:callout:warning",
        "extradoc:codeblock:python",
        "extradoc:codeblock:json",
    } <= named_ranges
    for request in requests:
        if "createNamedRange" in request:
            range_ = request["createNamedRange"]["range"]
            assert range_["startIndex"] < range_["endIndex"]
    assert any("createParagraphBullets" in request for request in requests)
    assert any("updateParagraphStyle" in request for request in requests)

    mock = MockGoogleDocsAPI(base)
    mock._batch_update_raw(requests)
    body = (
        mock.get()
        .model_dump(by_alias=True, exclude_none=True)["tabs"][0]["documentTab"]["body"]["content"]
    )
    assert body[-1]["endIndex"] >= max(
        request["createNamedRange"]["range"]["endIndex"]
        for request in requests
        if "createNamedRange" in request
    )
    paragraph_texts = [
        "".join(
            child.get("textRun", {}).get("content", "")
            for child in element["paragraph"].get("elements", [])
        ).strip()
        for element in body
        if "paragraph" in element
    ]
    assert [text for text in paragraph_texts if text][:4] == [
        "Stress Doc",
        "Lead with bold, italic, strike, underline, code, and a link.",
        "Matrix",
        "Narrative",
    ]


def test_lower_semantic_diff_uses_actual_reverse_ranges_for_list_then_heading() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": ""},
            document_id="reverse-range-regression",
            title="Reverse Range Regression",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {
                "Tab_1": (
                    "> Quote one.\n"
                    ">\n"
                    "> Quote two.\n\n"
                    "> [!INFO]\n"
                    "> Info callout.\n\n"
                    "> [!WARNING]\n"
                    "> Warning callout.\n\n"
                    "- item one\n"
                    "- [ ] item two\n\n"
                    "## Operational Notes\n\n"
                    "The reconciler should preserve ordinary prose.\n"
                )
            },
            document_id="reverse-range-regression",
            title="Reverse Range Regression",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    batches = lower_semantic_diff_batches(base, desired, transport_base=base)
    mock = MockGoogleDocsAPI(base)
    prior_responses: list[dict[str, object]] = []
    for batch in batches:
        resolved_batch = resolve_deferred_placeholders(prior_responses, list(batch))
        response = mock._batch_update_raw(resolved_batch)
        prior_responses.append(response)
    body = (
        mock.get()
        .model_dump(by_alias=True, exclude_none=True)["tabs"][0]["documentTab"]["body"]["content"]
    )
    paragraphs = [
        element["paragraph"]
        for element in body
        if "paragraph" in element
        and "".join(
            child.get("textRun", {}).get("content", "")
            for child in element["paragraph"].get("elements", [])
        ).strip()
    ]

    operational = next(
        paragraph
        for paragraph in paragraphs
        if "".join(
            child.get("textRun", {}).get("content", "")
            for child in paragraph.get("elements", [])
        ).strip()
        == "Operational Notes"
    )
    prose = next(
        paragraph
        for paragraph in paragraphs
        if "".join(
            child.get("textRun", {}).get("content", "")
            for child in paragraph.get("elements", [])
        ).strip()
        == "The reconciler should preserve ordinary prose."
    )

    assert "bullet" not in operational
    assert operational["paragraphStyle"]["namedStyleType"] == "HEADING_2"
    assert prose.get("paragraphStyle", {}).get("namedStyleType", "NORMAL_TEXT") == "NORMAL_TEXT"


def test_lower_semantic_diff_uses_structural_nesting_for_inserted_lists() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": ""},
            document_id="nested-list-insert",
            title="Nested List Insert",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {"Tab_1": "- parent\n  - child\n"},
            document_id="nested-list-insert",
            title="Nested List Insert",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    requests = lower_semantic_diff(base, desired)

    text_payloads = [
        request["insertText"]["text"]
        for request in requests
        if "insertText" in request
    ]
    assert text_payloads == ["\nparent\nchild"]
    assert any("createParagraphBullets" in request for request in requests)
    indent_updates = [
        request["updateParagraphStyle"]
        for request in requests
        if "updateParagraphStyle" in request
        and "indentStart" in request["updateParagraphStyle"]["paragraphStyle"]
    ]
    assert indent_updates
    assert indent_updates[0]["paragraphStyle"]["indentStart"]["magnitude"] == 72


def test_lower_semantic_diff_relevels_lists_without_tab_text_edits() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": "- parent\n- child\n"},
            document_id="nested-list-relevel",
            title="Nested List Relevel",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {"Tab_1": "- parent\n  - child\n"},
            document_id="nested-list-relevel",
            title="Nested List Relevel",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    requests = lower_semantic_diff(base, desired)

    assert not any(
        "insertText" in request and "\t" in request["insertText"]["text"]
        for request in requests
    )
    assert any("deleteParagraphBullets" in request for request in requests)
    assert any("createParagraphBullets" in request for request in requests)
    assert any(
        "updateParagraphStyle" in request
        and "indentStart" in request["updateParagraphStyle"]["paragraphStyle"]
        for request in requests
    )
    delete_index = next(
        index for index, request in enumerate(requests) if "deleteParagraphBullets" in request
    )
    create_index = next(
        index for index, request in enumerate(requests) if "createParagraphBullets" in request
    )
    style_index = next(
        index
        for index, request in enumerate(requests)
        if "updateParagraphStyle" in request
        and "indentStart" in request["updateParagraphStyle"]["paragraphStyle"]
    )
    assert delete_index < create_index < style_index

    mock = MockGoogleDocsAPI(base)
    mock._batch_update_raw(requests)
    body = mock.get().model_dump(by_alias=True, exclude_none=True)["tabs"][0]["documentTab"][
        "body"
    ]["content"]
    child = next(
        element["paragraph"]
        for element in body
        if "paragraph" in element
        and "".join(
            child.get("textRun", {}).get("content", "")
            for child in element["paragraph"].get("elements", [])
        ).strip()
        == "child"
    )
    assert child["bullet"]["nestingLevel"] == 1


def test_lower_semantic_diff_deletes_body_paragraph_slice_after_table() -> None:
    base = reindex_document(
        markdown_to_document(
            {
                "Tab_1": (
                    "| Col |\n"
                    "| --- |\n"
                    "| value |\n\n"
                    "## Heading\n\n"
                    "Body paragraph.\n\n"
                    "Tail paragraph.\n"
                )
            },
            document_id="body-slice-after-table",
            title="Body Slice After Table",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {
                "Tab_1": (
                    "| Col |\n"
                    "| --- |\n"
                    "| value |\n\n"
                    "Tail paragraph.\n"
                )
            },
            document_id="body-slice-after-table",
            title="Body Slice After Table",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    requests = lower_semantic_diff(base, desired)

    assert any("deleteContentRange" in request for request in requests)


def test_lower_semantic_diff_from_empty_body_avoids_leading_carrier_newlines() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": ""},
            document_id="empty-body-mixed-build",
            title="Empty Body Mixed Build",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {
                "Tab_1": (
                    "# Program Overview\n\n"
                    "Lead paragraph.\n\n"
                    "## Alerts\n\n"
                    "> [!INFO]\n"
                    "> Info callout opening text.\n\n"
                    "## After Alert\n\n"
                    "Tail paragraph.\n"
                )
            },
            document_id="empty-body-mixed-build",
            title="Empty Body Mixed Build",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    batches = lower_semantic_diff_batches(base, desired, transport_base=base)
    flattened = [request for batch in batches for request in batch]

    assert not any(
        "insertText" in request
        and request["insertText"]["location"].get("tabId") == "t.0"
        and request["insertText"]["location"].get("index") == 1
        and isinstance(request["insertText"]["text"], str)
        and request["insertText"]["text"].startswith("\n")
        for request in flattened
    )


def test_lower_semantic_diff_resets_unstyled_text_after_heading_for_callouts() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": ""},
            document_id="callout-style-reset",
            title="Callout Style Reset",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {
                "Tab_1": (
                    "## Alerts Revised\n\n"
                    "> [!TIP]\n"
                    "> Tip callout replacement text.\n"
                )
            },
            document_id="callout-style-reset",
            title="Callout Style Reset",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    batches = lower_semantic_diff_batches(base, desired, transport_base=base)
    flattened = [request for batch in batches for request in batch]

    assert any(
        request.get("updateTextStyle", {}).get("textStyle") == {}
        and "fontSize" in request.get("updateTextStyle", {}).get("fields", "")
        for request in flattened
    )


def test_lower_semantic_diff_resets_unstyled_replaced_callout_text_after_heading() -> None:
    base = reindex_document(
        markdown_to_document(
            {
                "Tab_1": (
                    "## Alerts\n\n"
                    "> [!TIP]\n"
                    "> Tip opening text.\n"
                )
            },
            document_id="callout-style-reset-replace",
            title="Callout Style Reset Replace",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {
                "Tab_1": (
                    "## Alerts Revised\n\n"
                    "> [!TIP]\n"
                    "> Tip callout replacement text.\n"
                )
            },
            document_id="callout-style-reset-replace",
            title="Callout Style Reset Replace",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    requests = lower_semantic_diff(base, desired)

    assert any(
        request.get("updateTextStyle", {}).get("textStyle") == {}
        and "fontSize" in request.get("updateTextStyle", {}).get("fields", "")
        for request in requests
    )


def test_lower_semantic_diff_resets_inserted_list_items_to_normal_text() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": "## Lists Revised\n"},
            document_id="list-normal-reset",
            title="List Normal Reset",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {
                "Tab_1": (
                    "## Lists Revised\n\n"
                    "- First bullet edited\n"
                    "- Second bullet edited\n"
                    "  - Nested bullet edited\n"
                )
            },
            document_id="list-normal-reset",
            title="List Normal Reset",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    requests = lower_semantic_diff(base, desired)

    normal_text_updates = [
        request
        for request in requests
        if request.get("updateParagraphStyle", {}).get("paragraphStyle", {}).get("namedStyleType")
        == "NORMAL_TEXT"
    ]
    assert normal_text_updates


def test_lower_semantic_diff_repairs_live_multitab_probe_after_table_backed_rewrites() -> None:
    fixture_root = FIXTURES_ROOT / "live_multitab_cycle2_probe"
    base = Document.model_validate(
        json.loads((fixture_root / "base.json").read_text(encoding="utf-8"))
    )
    desired_bundle = serde.deserialize(fixture_root / "desired")
    _normalize_raw_base_para_styles(base, desired_bundle.document)
    desired = reindex_document(desired_bundle.document)

    batches = lower_semantic_diff_batches(base, desired, transport_base=base)
    requests = [request for batch in batches for request in batch]

    delete_ranges = [
        request["deleteContentRange"]["range"]
        for request in requests
        if "deleteContentRange" in request
        and request["deleteContentRange"]["range"].get("tabId") == "t.0"
    ]
    assert {"startIndex": 466, "endIndex": 517, "tabId": "t.0"} not in delete_ranges

    assert not any(
        "insertText" in request
        and request["insertText"]["location"].get("tabId") == "t.0"
        and "\t" in request["insertText"]["text"]
        for request in requests
    )

    mock = MockGoogleDocsAPI(base)
    prior_responses: list[dict[str, object]] = []
    for batch in batches:
        resolved_batch = resolve_deferred_placeholders(prior_responses, list(batch))
        response = mock._batch_update_raw(resolved_batch)
        prior_responses.append(response)
    body = (
        mock.get()
        .model_dump(by_alias=True, exclude_none=True)["tabs"][0]["documentTab"]["body"]["content"]
    )
    paragraph_texts = [
        "".join(
            child.get("textRun", {}).get("content", "")
            for child in element["paragraph"].get("elements", [])
        ).strip()
        for element in body
        if "paragraph" in element
    ]
    assert "Program Overview Revised" in paragraph_texts
    assert "Code Samples Revised" in paragraph_texts
    assert (
        "This replacement paragraph still carries a footnote reference after editing."
        in paragraph_texts
    )
    footnotes = mock.get().model_dump(by_alias=True, exclude_none=True)["tabs"][0][
        "documentTab"
    ].get("footnotes", {})
    assert footnotes


def test_lower_semantic_diff_applies_cell_styles_for_inserted_special_tables() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": ""},
            document_id="special-table-style-insert",
            title="Special Table Style Insert",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {
                "Tab_1": (
                    "> [!INFO]\n"
                    "> Styled callout cell.\n\n"
                    "```python\n"
                    "print('styled')\n"
                    "```\n"
                )
            },
            document_id="special-table-style-insert",
            title="Special Table Style Insert",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    requests = lower_semantic_diff(base, desired)

    assert any("insertTable" in request for request in requests)
    assert any("updateTableCellStyle" in request for request in requests)


def test_transport_block_keep_mask_drops_carrier_runs_adjacent_to_tables() -> None:
    blocks = [
        ParagraphIR(
            role="HEADING_2",
            explicit_style={"namedStyleType": "HEADING_2"},
            inlines=[TextSpanIR(text="Code Samples", explicit_text_style={})],
        ),
        ParagraphIR(
            role="HEADING_2",
            explicit_style={"namedStyleType": "HEADING_2"},
            inlines=[],
        ),
        ParagraphIR(
            role="NORMAL_TEXT",
            explicit_style={"namedStyleType": "NORMAL_TEXT"},
            inlines=[],
        ),
        TableIR(style={}, pinned_header_rows=0, column_properties=[], merge_regions=[], rows=[]),
    ]

    assert _transport_block_keep_mask(blocks) == [True, False, False, True]


def test_transport_block_keep_mask_drops_carrier_runs_adjacent_to_page_breaks() -> None:
    blocks = [
        ParagraphIR(
            role="NORMAL_TEXT",
            explicit_style={"namedStyleType": "NORMAL_TEXT"},
            inlines=[TextSpanIR(text="Before break", explicit_text_style={})],
        ),
        ParagraphIR(
            role="NORMAL_TEXT",
            explicit_style={"namedStyleType": "NORMAL_TEXT"},
            inlines=[],
        ),
        ParagraphIR(
            role="HEADING_2",
            explicit_style={"namedStyleType": "HEADING_2"},
            inlines=[],
        ),
        PageBreakIR(),
        ParagraphIR(
            role="HEADING_2",
            explicit_style={"namedStyleType": "HEADING_2"},
            inlines=[TextSpanIR(text="After break", explicit_text_style={})],
        ),
    ]

    assert _transport_block_keep_mask(blocks) == [True, False, False, True, True]


def test_lower_semantic_diff_table_cell_text_replace_preserves_cell_paragraphs() -> None:
    base = reindex_document(
        markdown_to_document(
            {
                "Tab_1": (
                    "```python\n"
                    "def sprint_status() -> str:\n"
                    '    return "green"\n'
                    "```\n"
                )
            },
            document_id="table-cell-paragraph-preserve",
            title="Table Cell Paragraph Preserve",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {
                "Tab_1": (
                    "```python\n"
                    "def sprint_status() -> str:\n"
                    '    return "blue"\n'
                    "```\n"
                )
            },
            document_id="table-cell-paragraph-preserve",
            title="Table Cell Paragraph Preserve",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    requests = lower_semantic_diff(base, desired)

    mock = MockGoogleDocsAPI(base)
    mock._batch_update_raw(requests)
    repaired = canonicalize_transport_document(mock.get())
    table = repaired.tabs[0].body.sections[0].blocks[0]
    cell_blocks = table.rows[0].cells[0].content.blocks

    assert len(cell_blocks) == 2
    assert "".join(span.text for span in cell_blocks[0].inlines) == "def sprint_status() -> str:"
    assert "".join(span.text for span in cell_blocks[1].inlines) == '    return "blue"'


def test_lower_semantic_diff_batches_repair_operational_notes_fixture() -> None:
    base, desired = _load_fixture_pair("operational_notes_repair")

    batches = lower_semantic_diff_batches(base, desired, transport_base=base)

    assert batches

    mock = MockGoogleDocsAPI(base)
    for batch in batches:
        mock._batch_update_raw(batch)

    body = (
        mock.get()
        .model_dump(by_alias=True, exclude_none=True)["tabs"][0]["documentTab"]["body"]["content"]
    )
    paragraph_texts = [
        "".join(
            child.get("textRun", {}).get("content", "")
            for child in element["paragraph"].get("elements", [])
        ).strip()
        for element in body
        if "paragraph" in element
    ]
    assert "Operational Notes" in paragraph_texts
    assert (
        "The reconciler should preserve ordinary prose like this paragraph while also supporting structural markdown features in the same document."
        in paragraph_texts
    )


def test_lower_semantic_diff_ignores_empty_live_table_row_height_styles() -> None:
    fixture_root = FIXTURES_ROOT / "live_delete_json_probe"
    base = Document.model_validate(
        json.loads((fixture_root / "base.json").read_text(encoding="utf-8"))
    )
    desired_bundle = serde.deserialize(fixture_root / "desired")
    _normalize_raw_base_para_styles(base, desired_bundle.document)
    desired = reindex_document(desired_bundle.document)

    requests = lower_semantic_diff(base, desired)

    assert not any(
        "updateTableRowStyle" in request
        and request["updateTableRowStyle"].get("fields") == "minRowHeight"
        and request["updateTableRowStyle"].get("tableRowStyle") == {}
        for request in requests
    )
    assert not any("updateTableCellStyle" in request for request in requests)
    deleted_named_ranges = [
        request["deleteNamedRange"]["name"]
        for request in requests
        if "deleteNamedRange" in request
    ]
    assert "extradoc:blockquote" not in deleted_named_ranges
    assert "extradoc:codeblock:python" not in deleted_named_ranges
    assert "extradoc:codeblock:json" not in deleted_named_ranges

    mock = MockGoogleDocsAPI(base)
    mock._batch_update_raw(requests)


def test_lower_semantic_diff_rejects_column_insert_through_merged_region() -> None:
    base, desired = _load_fixture_pair("table_column_insert_through_merged")

    with pytest.raises(
        UnsupportedSpikeError,
        match="column structural edits through merged regions",
    ):
        lower_semantic_diff(base, desired)


def test_lower_semantic_diff_rejects_toc_mismatch() -> None:
    base = _make_doc_with_toc(include_toc=True)
    desired = _make_doc_with_toc(include_toc=False)

    with pytest.raises(
        UnsupportedSpikeError,
        match="read-only or opaque body blocks",
    ):
        lower_semantic_diff(base, desired)


def test_lower_semantic_diff_supports_mixed_edits_around_unchanged_toc() -> None:
    base = _make_doc_with_toc_and_table()
    desired = _make_doc_with_toc_and_table(intro_text="Lead", include_table=False)

    assert lower_semantic_diff(base, desired) == [
        {
            "deleteContentRange": {
                "range": {"startIndex": 4, "endIndex": 14, "tabId": "t.0"}
            }
        },
        {
            "insertText": {
                "location": {"index": 1, "tabId": "t.0"},
                "text": "Lead\n",
            }
        },
    ]


def test_lower_semantic_diff_named_range_add_ignores_desired_named_range_id() -> None:
    base, desired = _load_fixture_pair("named_range_add")
    desired_raw = desired.model_dump(by_alias=True, exclude_none=True)
    named_ranges = desired_raw["tabs"][0]["documentTab"]["namedRanges"]["spike:bravo"][
        "namedRanges"
    ]
    for named_range in named_ranges:
        named_range.pop("namedRangeId", None)
    desired_without_ids = Document.model_validate(desired_raw)

    assert lower_semantic_diff(base, desired_without_ids) == [
        {
            "createNamedRange": {
                "name": "spike:bravo",
                "range": {"startIndex": 7, "endIndex": 12, "tabId": "t.0"},
            }
        }
    ]


def test_lower_semantic_diff_supports_first_paragraph_insert_into_empty_body() -> None:
    base = _make_single_tab_doc(paragraphs=[])
    desired = _make_single_tab_doc(
        paragraphs=["alpha paragraph", "beta paragraph"]
    )

    assert lower_semantic_diff(base, desired) == [
        {
            "insertText": {
                "location": {"index": 1, "tabId": "t.0"},
                "text": "alpha paragraph\nbeta paragraph",
            }
        }
    ]


def test_lower_semantic_diff_supports_zero_width_paragraph_insert_between_blocks() -> None:
    base = _make_single_tab_doc(paragraphs=["alpha", "charlie"])
    desired = _make_single_tab_doc(paragraphs=["alpha", "bravo", "charlie"])

    assert lower_semantic_diff(base, desired) == [
        {
            "insertText": {
                "location": {"index": 7, "tabId": "t.0"},
                "text": "bravo\n",
            }
        }
    ]


def test_lower_semantic_diff_stages_named_range_anchor_moves_after_content_edits() -> None:
    base = _make_doc_with_named_range(
        text="alpha bravo charlie",
        range_name="spike:target",
        target_text="bravo",
    )
    desired = _make_doc_with_named_range(
        text="alpha bravo charlie delta",
        range_name="spike:target",
        target_text="delta",
    )

    assert lower_semantic_diff(base, desired) == [
        {
            "deleteContentRange": {
                "range": {"startIndex": 1, "endIndex": 20, "tabId": "t.0"}
            }
        },
        {
            "insertText": {
                "location": {"index": 1, "tabId": "t.0"},
                "text": "alpha bravo charlie delta",
            }
        },
        {"deleteNamedRange": {"name": "spike:target"}},
        {
            "createNamedRange": {
                "name": "spike:target",
                "range": {"startIndex": 21, "endIndex": 26, "tabId": "t.0"},
            }
        },
    ]


def test_lower_semantic_diff_batches_repair_live_list_role_bleed_fixture() -> None:
    fixture_root = FIXTURES_ROOT / "live_list_role_bleed_repair"
    base = Document.model_validate(
        json.loads((fixture_root / "base.json").read_text(encoding="utf-8"))
    )
    desired_bundle = serde.deserialize(fixture_root / "desired")
    _normalize_raw_base_para_styles(base, desired_bundle.document)
    desired = reindex_document(desired_bundle.document)

    batches = lower_semantic_diff_batches(base, desired, transport_base=base)
    requests = [request for batch in batches for request in batch]

    normalized_role_ranges = {
        (
            request["updateParagraphStyle"]["range"]["startIndex"],
            request["updateParagraphStyle"]["range"]["endIndex"],
        )
        for request in requests
        if "updateParagraphStyle" in request
        and request["updateParagraphStyle"]["paragraphStyle"].get("namedStyleType")
        == "NORMAL_TEXT"
    }

    assert (485, 505) in normalized_role_ranges
    assert (505, 526) in normalized_role_ranges
    assert (526, 550) in normalized_role_ranges
    assert (550, 574) in normalized_role_ranges


def _load_fixture_pair(name: str) -> tuple[Document, Document]:
    fixture_dir = FIXTURES_ROOT / name
    base = Document.model_validate(json.loads((fixture_dir / "base.json").read_text()))
    desired = Document.model_validate(
        json.loads((fixture_dir / "desired.json").read_text())
    )
    return base, desired
