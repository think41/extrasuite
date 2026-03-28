from __future__ import annotations

import json
from pathlib import Path

import pytest

from extradoc.api_types._generated import Document
from extradoc.reconcile import reindex_document
from extradoc.reconcile_v2.api import (
    canonical_document_signature,
    canonicalize_transport_document,
    lower_semantic_diff,
)
from extradoc.reconcile_v2.errors import UnsupportedSpikeError
from extradoc.serde._from_markdown import markdown_to_document

from .helpers import load_expected_lowered_requests

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"


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

    requests = lower_semantic_diff(base, desired)

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


def _load_fixture_pair(name: str) -> tuple[Document, Document]:
    fixture_dir = FIXTURES_ROOT / name
    base = Document.model_validate(json.loads((fixture_dir / "base.json").read_text()))
    desired = Document.model_validate(
        json.loads((fixture_dir / "desired.json").read_text())
    )
    return base, desired
