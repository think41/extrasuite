from __future__ import annotations

import copy
import json
from pathlib import Path

from extradoc.api_types._generated import Document
from extradoc.reconcile_v2.diff import (
    AppendListItemsEdit,
    DeleteSectionEdit,
    DeleteTableColumnEdit,
    DeleteTableRowEdit,
    InsertSectionEdit,
    InsertTableColumnEdit,
    InsertTableRowEdit,
    MergeTableCellsEdit,
    ReplaceListSpecEdit,
    ReplaceNamedRangesEdit,
    ReplaceParagraphSliceEdit,
    UnmergeTableCellsEdit,
    UpdateParagraphRoleEdit,
    diff_documents,
    summarize_semantic_edits,
)

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"


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


def test_text_replace_fixture_emits_story_text_replace() -> None:
    base, desired = _load_fixture_pair("text_replace")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], ReplaceParagraphSliceEdit)
    assert edits[0].story_id == "t.0:body"
    assert summarize_semantic_edits(edits) == [
        "tab t.0: story t.0:body replace 1 paragraph block(s) at 0 with 1 paragraph(s)"
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
    assert edits[0].story_id == "t.0:body:table:1:r1:c0"
    assert summarize_semantic_edits(edits) == [
        "tab t.0: story t.0:body:table:1:r1:c0 replace 1 paragraph block(s) at 0 with 1 paragraph(s)"
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


def test_table_row_insert_fixture_emits_structural_row_insert() -> None:
    base, desired = _load_fixture_pair("table_row_insert")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], InsertTableRowEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 1 insert row below 1"
    ]


def test_table_row_delete_fixture_emits_structural_row_delete() -> None:
    base, desired = _load_fixture_pair("table_row_delete")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], DeleteTableRowEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 1 delete row 2"
    ]


def test_table_column_insert_fixture_emits_structural_column_insert() -> None:
    base, desired = _load_fixture_pair("table_column_insert")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], InsertTableColumnEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 1 insert column right of 1"
    ]


def test_table_column_delete_fixture_emits_structural_column_delete() -> None:
    base, desired = _load_fixture_pair("table_column_delete")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], DeleteTableColumnEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 1 delete column 2"
    ]


def test_table_merge_cells_fixture_emits_merge_edit() -> None:
    base, desired = _load_fixture_pair("table_merge_cells")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], MergeTableCellsEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 1 merge cells r0 c0 span 1x2"
    ]


def test_table_unmerge_cells_fixture_emits_unmerge_edit() -> None:
    base, desired = _load_fixture_pair("table_unmerge_cells")

    edits = diff_documents(base, desired)

    assert len(edits) == 1
    assert isinstance(edits[0], UnmergeTableCellsEdit)
    assert summarize_semantic_edits(edits) == [
        "tab t.0: section 0 table 1 unmerge cells r0 c0 span 1x2"
    ]


def _load_fixture_pair(name: str) -> tuple[Document, Document]:
    fixture_dir = FIXTURES_ROOT / name
    base = Document.model_validate(json.loads((fixture_dir / "base.json").read_text()))
    desired = Document.model_validate(
        json.loads((fixture_dir / "desired.json").read_text())
    )
    return base, desired
