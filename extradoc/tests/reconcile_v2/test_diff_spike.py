from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from extradoc.api_types._generated import Document
from extradoc.reconcile import reindex_document
from extradoc.reconcile_v2.diff import (
    AppendListItemsEdit,
    DeleteListBlockEdit,
    DeleteSectionEdit,
    DeleteTableBlockEdit,
    DeleteTableColumnEdit,
    DeleteTableRowEdit,
    InsertListBlockEdit,
    InsertSectionEdit,
    InsertTableBlockEdit,
    InsertTableColumnEdit,
    InsertTableRowEdit,
    MergeTableCellsEdit,
    RelevelListItemsEdit,
    ReplaceListSpecEdit,
    ReplaceNamedRangesEdit,
    ReplaceParagraphSliceEdit,
    UnmergeTableCellsEdit,
    UpdateParagraphRoleEdit,
    UpdateTableCellStyleEdit,
    UpdateTableColumnPropertiesEdit,
    UpdateTablePinnedHeaderRowsEdit,
    UpdateTableRowStyleEdit,
    _filter_conflicting_table_edits,
    diff_documents,
    summarize_semantic_edits,
)
from extradoc.reconcile_v2.errors import UnsupportedSpikeError
from extradoc.serde._from_markdown import markdown_to_document

from .helpers import load_fixture_pair as load_fixture_pair_shared

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


def test_paragraph_to_heading_fixture_emits_role_change() -> None:
    base, desired = _load_fixture_pair("paragraph_to_heading")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], UpdateParagraphRoleEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 block 0 role NORMAL_TEXT -> HEADING_1"
    ]


def test_list_append_fixture_emits_semantic_list_append() -> None:
    base, desired = _load_fixture_pair("list_append")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], AppendListItemsEdit)
    assert [item.text for item in edits[0].appended_items] == ["three"]
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 list 0 append 1 item(s) to BULLETED"
    ]


def test_section_split_fixture_emits_topology_change_not_carrier_paragraph_noise() -> None:
    base, desired = _load_fixture_pair("section_split")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], InsertSectionEdit)
    assert edits[0].section_index == 0
    assert edits[0].split_after_block_index == 0
    assert summarize_semantic_edits(edits) == [
        "tab t.0: split section 0 after block 0 and insert section with 1 block(s)"
    ]


def test_section_delete_fixture_emits_boundary_delete() -> None:
    base, desired = _load_fixture_pair("section_delete")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], DeleteSectionEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: delete section 1 with 1 block(s)"
    ]


def test_list_kind_change_fixture_emits_list_spec_replace() -> None:
    base, desired = _load_fixture_pair("list_kind_change")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], ReplaceListSpecEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 list 0 kind BULLETED -> NUMBERED"
    ]


def test_list_relevel_fixture_emits_relevel_edit() -> None:
    base, desired = load_fixture_pair_shared("list_relevel")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], RelevelListItemsEdit)
    assert edits[0].before_levels == (0, 0)
    assert edits[0].after_levels == (0, 1)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 list 0 relevel 1 item(s) in BULLETED"
    ]


def test_mixed_section_list_insert_emits_list_block_insert() -> None:
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

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], InsertListBlockEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 insert BULLETED list at block 1 with 2 item(s)"
    ]


def test_mixed_section_list_delete_emits_list_block_delete() -> None:
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

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], DeleteListBlockEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 delete list at block 1"
    ]


def test_replace_paragraph_with_list_emits_delete_then_list_insert() -> None:
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

    edits = diff_documents(base, desired)

    assert [type(edit) for edit in edits] == [ReplaceParagraphSliceEdit, InsertListBlockEdit]


def test_replace_list_with_paragraph_emits_delete_then_paragraph_insert() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": "- one\n- two\n"},
            document_id="replace-list-with-paragraph",
            title="Replace List With Paragraph",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {"Tab_1": "Alpha\n"},
            document_id="replace-list-with-paragraph",
            title="Replace List With Paragraph",
            tab_ids={"Tab_1": "t.0"},
        )
    )

    edits = diff_documents(base, desired)

    assert [type(edit) for edit in edits] == [DeleteListBlockEdit, ReplaceParagraphSliceEdit]


def test_insert_table_between_paragraphs_emits_table_insert_and_named_range() -> None:
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

    edits = diff_documents(base, desired)

    assert [type(edit) for edit in edits] == [ReplaceNamedRangesEdit, InsertTableBlockEdit]


def test_replace_paragraph_with_table_emits_delete_insert_and_named_range() -> None:
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

    edits = diff_documents(base, desired)

    assert [type(edit) for edit in edits] == [
        ReplaceNamedRangesEdit,
        ReplaceParagraphSliceEdit,
        InsertTableBlockEdit,
    ]


def test_replace_table_with_paragraph_emits_delete_insert_and_named_range_delete() -> None:
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

    edits = diff_documents(base, desired)

    assert [type(edit) for edit in edits] == [
        ReplaceNamedRangesEdit,
        DeleteTableBlockEdit,
        ReplaceParagraphSliceEdit,
    ]


def test_insert_mixed_body_sequence_into_empty_section_emits_reverse_order_plan() -> None:
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

    edits = diff_documents(base, desired)

    assert [type(edit) for edit in edits] == [
        ReplaceNamedRangesEdit,
        ReplaceParagraphSliceEdit,
        InsertTableBlockEdit,
        InsertListBlockEdit,
        ReplaceParagraphSliceEdit,
    ]
    assert summarize_semantic_edits(edits) == [
        "tab t.0: named range extradoc:codeblock:python replace 0 range(s) with 1 range(s)",
        "tab t.0: story t.0:body replace 0 paragraph block(s) at 0 with 1 paragraph(s)",
        "tab t.0: section 0 insert table at block 0",
        "tab t.0: section 0 insert BULLETED list at block 0 with 2 item(s)",
        "tab t.0: story t.0:body replace 0 paragraph block(s) at 0 with 2 paragraph(s)",
    ]


def test_text_replace_fixture_emits_story_text_replace() -> None:
    base, desired = _load_fixture_pair("text_replace")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], ReplaceParagraphSliceEdit)
    assert edits[0].story_id == "t.0:body"
    assert summarize_semantic_edits(edits) == [
        "tab t.0: story t.0:body replace 1 paragraph block(s) at 0 with 1 paragraph(s)"
    ]


def test_multitab_text_replace_fixture_emits_edit_only_for_second_tab() -> None:
    base, desired = load_fixture_pair_shared("multitab_text_replace")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], ReplaceParagraphSliceEdit)
    assert edits[0].tab_id != "t.0"
    assert edits[0].story_id == f"{edits[0].tab_id}:body"
    assert summarize_semantic_edits(edits) == [
        f"tab {edits[0].tab_id}: story {edits[0].story_id} replace 1 paragraph block(s) at 0 with 1 paragraph(s)"
    ]


def test_paragraph_split_fixture_emits_paragraph_slice_replace() -> None:
    base, desired = _load_fixture_pair("paragraph_split")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], ReplaceParagraphSliceEdit)
    assert [fragment.text for fragment in edits[0].inserted_paragraphs] == [
        "alpha",
        "beta",
    ]
    assert summarize_semantic_edits(edits) == [
        "tab t.0: story t.0:body replace 1 paragraph block(s) at 0 with 2 paragraph(s)"
    ]


def test_table_cell_text_replace_fixture_emits_nested_story_replace() -> None:
    base, desired = _load_fixture_pair("table_cell_text_replace")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], ReplaceParagraphSliceEdit)
    assert edits[0].story_id == "t.0:body:table:0:r1:c0"
    assert summarize_semantic_edits(edits) == [
        "tab t.0: story t.0:body:table:0:r1:c0 replace 1 paragraph block(s) at 0 with 1 paragraph(s)"
    ]


def test_header_text_replace_fixture_emits_segment_story_replace() -> None:
    base, desired = _load_fixture_pair("header_text_replace")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], ReplaceParagraphSliceEdit)
    assert edits[0].story_id.startswith("t.0:header:")
    assert summarize_semantic_edits(edits) == [
        f"tab t.0: story {edits[0].story_id} replace 1 paragraph block(s) at 0 with 1 paragraph(s)"
    ]


def test_header_text_replace_matches_by_attachment_slot_not_transport_id() -> None:
    base, desired = _load_fixture_pair("header_text_replace")
    desired_raw = copy.deepcopy(desired.model_dump(by_alias=True, exclude_none=True))
    old_header_id = next(iter(desired_raw["tabs"][0]["documentTab"]["headers"]))
    new_header_id = "kix.synthetic-slot-match"
    desired_raw["tabs"][0]["documentTab"]["headers"] = {
        new_header_id: {
            **desired_raw["tabs"][0]["documentTab"]["headers"][old_header_id],
            "headerId": new_header_id,
        }
    }
    desired_raw["tabs"][0]["documentTab"]["documentStyle"]["defaultHeaderId"] = (
        new_header_id
    )
    desired_raw["tabs"][0]["documentTab"]["body"]["content"][0]["sectionBreak"][
        "sectionStyle"
    ]["defaultHeaderId"] = new_header_id
    desired_with_new_id = Document.model_validate(desired_raw)

    edits = diff_documents(base, desired_with_new_id)

    assert len(edits) == 1
    assert isinstance(edits[0], ReplaceParagraphSliceEdit)


def test_named_range_add_fixture_emits_named_range_replace() -> None:
    base, desired = _load_fixture_pair("named_range_add")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], ReplaceNamedRangesEdit)
    assert edits[0].name == "spike:bravo"
    assert summarize_semantic_edits(edits) == [
        "tab t.0: named range spike:bravo replace 0 range(s) with 1 range(s)"
    ]


def test_named_range_delete_fixture_emits_named_range_replace() -> None:
    base, desired = _load_fixture_pair("named_range_delete")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], ReplaceNamedRangesEdit)
    assert edits[0].name == "spike:bravo"
    assert summarize_semantic_edits(edits) == [
        "tab t.0: named range spike:bravo replace 1 range(s) with 0 range(s)"
    ]


def test_unchanged_toc_is_tolerated() -> None:
    base = _make_doc_with_toc(include_toc=True)
    desired = _make_doc_with_toc(include_toc=True)

    assert diff_documents(base, desired) == []


def test_toc_mismatch_is_explicitly_unsupported() -> None:
    base = _make_doc_with_toc(include_toc=True)
    desired = _make_doc_with_toc(include_toc=False)

    with pytest.raises(
        UnsupportedSpikeError,
        match="read-only or opaque body blocks",
    ):
        diff_documents(base, desired)


def test_unchanged_toc_can_anchor_mixed_body_edits_around_it() -> None:
    base = _make_doc_with_toc_and_table()
    desired = _make_doc_with_toc_and_table(intro_text="Lead", include_table=False)

    edits = diff_documents(base, desired)

    assert [type(edit) for edit in edits] == [
        DeleteTableBlockEdit,
        ReplaceParagraphSliceEdit,
    ]
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 delete table at block 0",
        "tab t.0: story t.0:body replace 0 paragraph block(s) at 0 with 1 paragraph(s)",
    ]


def test_table_row_insert_fixture_emits_structural_row_insert() -> None:
    base, desired = _load_fixture_pair("table_row_insert")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], InsertTableRowEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 0 insert row below 1"
    ]


def test_table_middle_row_insert_fixture_emits_structural_middle_row_insert() -> None:
    base, desired = _load_fixture_pair("table_middle_row_insert")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], InsertTableRowEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 0 insert row below 1"
    ]


def test_table_row_delete_fixture_emits_structural_row_delete() -> None:
    base, desired = _load_fixture_pair("table_row_delete")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], DeleteTableRowEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 0 delete row 2"
    ]


def test_table_middle_row_delete_fixture_emits_structural_middle_row_delete() -> None:
    base, desired = _load_fixture_pair("table_middle_row_delete")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], DeleteTableRowEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 0 delete row 2"
    ]


def test_table_column_insert_fixture_emits_structural_column_insert() -> None:
    base, desired = _load_fixture_pair("table_column_insert")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], InsertTableColumnEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 0 insert column right of 1"
    ]


def test_table_middle_column_insert_fixture_emits_structural_middle_column_insert() -> None:
    base, desired = _load_fixture_pair("table_middle_column_insert")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], InsertTableColumnEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 0 insert column right of 1"
    ]


def test_table_column_delete_fixture_emits_structural_column_delete() -> None:
    base, desired = _load_fixture_pair("table_column_delete")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], DeleteTableColumnEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 0 delete column 2"
    ]


def test_table_middle_column_delete_fixture_emits_structural_middle_column_delete() -> None:
    base, desired = _load_fixture_pair("table_middle_column_delete")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], DeleteTableColumnEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 0 delete column 2"
    ]


def test_table_merge_cells_fixture_emits_merge_edit() -> None:
    base, desired = _load_fixture_pair("table_merge_cells")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], MergeTableCellsEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 0 merge cells r0 c0 span 1x2"
    ]


def test_table_unmerge_cells_fixture_emits_unmerge_edit() -> None:
    base, desired = _load_fixture_pair("table_unmerge_cells")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], UnmergeTableCellsEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 0 unmerge cells r0 c0 span 1x2"
    ]


def test_table_middle_row_insert_with_cell_edit_emits_text_replace_then_row_insert() -> None:
    base, desired = _load_fixture_pair("table_middle_row_insert_with_cell_edit")

    edits = diff_documents(base, desired)

    assert len(edits) == 2
    assert isinstance(edits[0], ReplaceParagraphSliceEdit)
    assert isinstance(edits[1], InsertTableRowEdit)
    assert edits[0].story_id == "t.0:body:table:0:r2:c0"
    assert summarize_semantic_edits(edits) == [
        "tab t.0: story t.0:body:table:0:r2:c0 replace 1 paragraph block(s) at 0 with 1 paragraph(s)",
        "tab t.0: section 0 table 0 insert row below 1",
    ]


def test_table_middle_row_insert_with_inserted_content_emits_populated_insert() -> None:
    base, desired = _load_fixture_pair("table_middle_row_insert_with_inserted_content")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], InsertTableRowEdit)
    assert edits[0].inserted_cells == ("NEW", "")
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 0 insert row below 1 with 1 populated cell(s)"
    ]


def test_table_row_insert_below_merged_fixture_emits_structural_insert() -> None:
    base, desired = _load_fixture_pair("table_row_insert_below_merged")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], InsertTableRowEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 0 insert row below 0"
    ]


def test_table_middle_column_insert_with_inserted_content_emits_populated_insert() -> None:
    base, desired = _load_fixture_pair("table_middle_column_insert_with_inserted_content")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], InsertTableColumnEdit)
    assert edits[0].inserted_cells == ("", "NEW")
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 0 insert column right of 1 with 1 populated cell(s)"
    ]


def test_table_pin_header_rows_fixture_emits_table_header_pin() -> None:
    base, desired = _load_fixture_pair("table_pin_header_rows")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], UpdateTablePinnedHeaderRowsEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 0 pin header rows 1"
    ]


def test_table_row_style_min_height_fixture_emits_row_style_update() -> None:
    base, desired = _load_fixture_pair("table_row_style_min_height")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], UpdateTableRowStyleEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 0 update row 1 style minRowHeight"
    ]


def test_table_column_properties_width_fixture_emits_column_property_update() -> None:
    base, desired = _load_fixture_pair("table_column_properties_width")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], UpdateTableColumnPropertiesEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 0 update column 1 properties width,widthType"
    ]


def test_table_cell_style_background_fixture_emits_cell_style_update() -> None:
    base, desired = _load_fixture_pair("table_cell_style_background")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], UpdateTableCellStyleEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 0 update cell r1 c1 style backgroundColor"
    ]


def test_table_row_and_column_insert_fixture_emits_two_structural_edits() -> None:
    base, desired = _load_fixture_pair("table_row_and_column_insert")

    edits = diff_documents(base, desired)

    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 0 insert row below 1",
        "tab t.0: section 0 table 0 insert column right of 1",
    ]


def test_operational_notes_repair_fixture_preserves_mixed_body_repair_slice() -> None:
    base, desired = _load_fixture_pair("operational_notes_repair")

    edits = diff_documents(base, desired)

    assert summarize_semantic_edits(edits) == [
        "tab t.0: named range extradoc:codeblock:json replace 1 range(s) with 1 range(s)",
        "tab t.0: named range extradoc:codeblock:python replace 1 range(s) with 1 range(s)",
        "tab t.0: story t.0:body:table:16:r0:c0 replace 5 paragraph block(s) at 0 with 14 paragraph(s)",
        "tab t.0: story t.0:body replace 1 paragraph block(s) at 14 with 0 paragraph(s)",
        "tab t.0: section 0 delete list at block 13",
        "tab t.0: story t.0:body replace 0 paragraph block(s) at 13 with 2 paragraph(s)",
        "tab t.0: section 0 insert BULLETED list at block 13 with 13 item(s)",
    ]


def test_table_column_insert_through_merged_fixture_is_explicitly_unsupported() -> None:
    base, desired = _load_fixture_pair("table_column_insert_through_merged")

    with pytest.raises(
        UnsupportedSpikeError,
        match="column structural edits through merged regions",
    ):
        diff_documents(base, desired)


def test_filter_conflicting_table_edits_drops_nested_cell_edit_for_deleted_table() -> None:
    table_cell_edit = ReplaceParagraphSliceEdit(
        tab_id="t.0",
        story_id="t.0:body:table:16:r0:c0",
        section_index=None,
        start_block_index=0,
        delete_block_count=5,
        inserted_paragraphs=(),
    )
    body_edits = [
        DeleteTableBlockEdit(
            tab_id="t.0",
            section_index=0,
            block_index=16,
        )
    ]

    assert _filter_conflicting_table_edits([table_cell_edit], body_edits) == []


def _load_fixture_pair(name: str) -> tuple[Document, Document]:
    fixture_dir = FIXTURES_ROOT / name
    base = Document.model_validate(json.loads((fixture_dir / "base.json").read_text()))
    desired = Document.model_validate(
        json.loads((fixture_dir / "desired.json").read_text())
    )
    return base, desired
