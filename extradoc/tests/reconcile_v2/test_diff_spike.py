from __future__ import annotations

import json
from pathlib import Path

from extradoc.api_types._generated import Document
from extradoc.reconcile_v2.diff import (
    AppendListItemsEdit,
    DeleteSectionEdit,
    InsertSectionEdit,
    ReplaceListSpecEdit,
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


def _load_fixture_pair(name: str) -> tuple[Document, Document]:
    fixture_dir = FIXTURES_ROOT / name
    base = Document.model_validate(json.loads((fixture_dir / "base.json").read_text()))
    desired = Document.model_validate(
        json.loads((fixture_dir / "desired.json").read_text())
    )
    return base, desired
