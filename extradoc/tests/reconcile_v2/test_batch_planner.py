from __future__ import annotations

import json
from pathlib import Path

import pytest

import extradoc.serde as serde
from extradoc.api_types._generated import BatchUpdateDocumentRequest, Document
from extradoc.client import _normalize_raw_base_para_styles
from extradoc.mock.api import MockGoogleDocsAPI
from extradoc.reconcile import reindex_document
from extradoc.reconcile_v2.api import lower_semantic_diff_batches, reconcile
from extradoc.reconcile_v2.errors import UnsupportedSpikeError
from extradoc.serde._from_markdown import markdown_to_document

from .helpers import (
    load_expected_lowered_batches,
    load_fixture_pair,
)


def test_create_tab_table_write_batches_match_fixture() -> None:
    base, desired = load_fixture_pair("create_tab_table_write")

    assert lower_semantic_diff_batches(base, desired) == load_expected_lowered_batches(
        "create_tab_table_write"
    )


def test_create_tab_nested_table_write_batches_match_fixture() -> None:
    base, desired = load_fixture_pair("create_tab_nested_table_write")

    assert lower_semantic_diff_batches(base, desired) == load_expected_lowered_batches(
        "create_tab_nested_table_write"
    )


def test_create_tab_named_range_write_batches_match_fixture() -> None:
    base, desired = load_fixture_pair("create_tab_named_range_write")

    assert lower_semantic_diff_batches(base, desired) == load_expected_lowered_batches(
        "create_tab_named_range_write"
    )


def test_create_parent_child_tab_write_batches_match_fixture() -> None:
    base, desired = load_fixture_pair("create_parent_child_tab_write")

    assert lower_semantic_diff_batches(base, desired) == load_expected_lowered_batches(
        "create_parent_child_tab_write"
    )


def test_create_tab_footnote_write_batches_match_fixture() -> None:
    base, desired = load_fixture_pair("create_tab_footnote_write")

    assert lower_semantic_diff_batches(base, desired) == load_expected_lowered_batches(
        "create_tab_footnote_write"
    )


def test_create_tab_named_range_footnote_write_batches_match_fixture() -> None:
    base, desired = load_fixture_pair("create_tab_named_range_footnote_write")

    assert lower_semantic_diff_batches(base, desired) == load_expected_lowered_batches(
        "create_tab_named_range_footnote_write"
    )


def test_section_create_distinct_header_batches_match_fixture() -> None:
    base, desired = load_fixture_pair("section_create_distinct_header")

    assert lower_semantic_diff_batches(base, desired) == load_expected_lowered_batches(
        "section_create_distinct_header"
    )


def test_section_create_footer_batches_match_fixture() -> None:
    base, desired = load_fixture_pair("section_create_footer")

    assert lower_semantic_diff_batches(base, desired) == load_expected_lowered_batches(
        "section_create_footer"
    )


def test_footnote_create_write_batches_match_fixture() -> None:
    base, desired = load_fixture_pair("footnote_create_write")

    assert lower_semantic_diff_batches(base, desired) == load_expected_lowered_batches(
        "footnote_create_write"
    )


def test_create_tab_batches_ignore_desired_future_tab_id() -> None:
    base, desired = load_fixture_pair("create_tab_table_write")
    desired_raw = desired.model_dump(by_alias=True, exclude_none=True)
    desired_raw["tabs"][1]["tabProperties"]["tabId"] = "future.invalid.tab"
    desired_future_id = Document.model_validate(desired_raw)

    assert lower_semantic_diff_batches(base, desired_future_id) == load_expected_lowered_batches(
        "create_tab_table_write"
    )


def test_create_tab_batches_ignore_desired_new_tab_transport_indices() -> None:
    base, desired = load_fixture_pair("create_tab_table_write")
    desired_raw = desired.model_dump(by_alias=True, exclude_none=True)
    _strip_indices(desired_raw["tabs"][1]["documentTab"]["body"]["content"])
    desired_without_indices = Document.model_validate(desired_raw)

    assert lower_semantic_diff_batches(
        base,
        desired_without_indices,
    ) == load_expected_lowered_batches("create_tab_table_write")


def test_create_tab_named_range_batches_ignore_desired_future_tab_id() -> None:
    base, desired = load_fixture_pair("create_tab_named_range_write")
    desired_raw = desired.model_dump(by_alias=True, exclude_none=True)
    desired_raw["tabs"][1]["tabProperties"]["tabId"] = "future.invalid.tab"
    desired_future_id = Document.model_validate(desired_raw)

    assert lower_semantic_diff_batches(base, desired_future_id) == load_expected_lowered_batches(
        "create_tab_named_range_write"
    )


def test_create_parent_child_batches_ignore_desired_future_tab_ids() -> None:
    base, desired = load_fixture_pair("create_parent_child_tab_write")
    desired_raw = desired.model_dump(by_alias=True, exclude_none=True)
    desired_raw["tabs"][1]["tabProperties"]["tabId"] = "future.parent.tab"
    desired_raw["tabs"][1]["childTabs"][0]["tabProperties"]["tabId"] = "future.child.tab"
    desired_future_id = Document.model_validate(desired_raw)

    assert lower_semantic_diff_batches(base, desired_future_id) == load_expected_lowered_batches(
        "create_parent_child_tab_write"
    )


def test_create_tab_footnote_batches_ignore_desired_future_tab_and_footnote_ids() -> None:
    base, desired = load_fixture_pair("create_tab_footnote_write")
    desired_raw = desired.model_dump(by_alias=True, exclude_none=True)
    desired_raw["tabs"][1]["tabProperties"]["tabId"] = "future.footnote.tab"
    footnotes = desired_raw["tabs"][1]["documentTab"]["footnotes"]
    footnote_id = next(iter(footnotes))
    footnote = footnotes.pop(footnote_id)
    footnote["footnoteId"] = "future.footnote.segment"
    footnotes["future.footnote.segment"] = footnote
    for element in desired_raw["tabs"][1]["documentTab"]["body"]["content"]:
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for child in paragraph.get("elements", []):
            footnote_ref = child.get("footnoteReference")
            if footnote_ref:
                footnote_ref["footnoteId"] = "future.footnote.segment"
    desired_future_id = Document.model_validate(desired_raw)

    assert lower_semantic_diff_batches(base, desired_future_id) == load_expected_lowered_batches(
        "create_tab_footnote_write"
    )


def test_create_new_tab_with_mixed_markdown_body_is_supported() -> None:
    base = reindex_document(
        markdown_to_document(
            {"Tab_1": "alpha\n"},
            document_id="new-tab-mixed-body",
            title="New Tab Mixed Body",
            tab_ids={"Tab_1": "t.0"},
        )
    )
    desired = reindex_document(
        markdown_to_document(
            {
                "Tab_1": "alpha\n",
                "Second_Tab": (
                    "# Heading\n\n"
                    "Lead paragraph.\n\n"
                    "- bullet one\n"
                    "- bullet two\n\n"
                    "```python\n"
                    "print('ok')\n"
                    "```\n"
                ),
            },
            document_id="new-tab-mixed-body",
            title="New Tab Mixed Body",
            tab_ids={"Tab_1": "t.0", "Second_Tab": "t.future"},
        )
    )

    batches = lower_semantic_diff_batches(base, desired)

    assert len(batches) >= 2
    assert "addDocumentTab" in batches[0][0]
    flattened = [request for batch in batches[1:] for request in batch]
    assert any("insertText" in request for request in flattened)
    assert any("insertTable" in request for request in flattened)
    assert any("createParagraphBullets" in request for request in flattened)
    assert any("updateParagraphStyle" in request for request in flattened)
    assert any("createNamedRange" in request for request in flattened)


def test_iterative_batches_split_complex_live_table_backed_body_rewrite() -> None:
    fixture_root = (
        Path(__file__).resolve().parent / "fixtures" / "live_multitab_cycle2_probe"
    )
    base = Document.model_validate(
        json.loads((fixture_root / "base.json").read_text(encoding="utf-8"))
    )
    desired_bundle = serde.deserialize(fixture_root / "desired")
    _normalize_raw_base_para_styles(base, desired_bundle.document)

    batches = lower_semantic_diff_batches(base, reindex_document(desired_bundle.document))

    assert len(batches) > 1
    assert batches[0] == [
        {
            "deleteContentRange": {
                "range": {"startIndex": 518, "endIndex": 561, "tabId": "t.0"}
            }
        }
    ]

    current = base
    for batch in batches:
        mock = MockGoogleDocsAPI(current)
        mock._batch_update_raw(batch)
        current = mock.get()


def test_create_tab_named_range_footnote_batches_ignore_desired_future_tab_and_footnote_ids() -> None:
    base, desired = load_fixture_pair("create_tab_named_range_footnote_write")
    desired_raw = desired.model_dump(by_alias=True, exclude_none=True)
    desired_raw["tabs"][1]["tabProperties"]["tabId"] = "future.range.footnote.tab"
    footnotes = desired_raw["tabs"][1]["documentTab"]["footnotes"]
    footnote_id = next(iter(footnotes))
    footnote = footnotes.pop(footnote_id)
    footnote["footnoteId"] = "future.range.footnote.segment"
    footnotes["future.range.footnote.segment"] = footnote
    for element in desired_raw["tabs"][1]["documentTab"]["body"]["content"]:
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for child in paragraph.get("elements", []):
            footnote_ref = child.get("footnoteReference")
            if footnote_ref:
                footnote_ref["footnoteId"] = "future.range.footnote.segment"
    desired_future_id = Document.model_validate(desired_raw)

    assert lower_semantic_diff_batches(base, desired_future_id) == load_expected_lowered_batches(
        "create_tab_named_range_footnote_write"
    )


def test_reconcile_returns_batch_update_models() -> None:
    base, desired = load_fixture_pair("create_tab_table_write")

    batches = reconcile(base, desired)

    assert all(isinstance(batch, BatchUpdateDocumentRequest) for batch in batches)
    assert [batch.model_dump(by_alias=True, exclude_none=True)["requests"] for batch in batches] == (
        load_expected_lowered_batches("create_tab_table_write")
    )


def test_create_tab_with_footer_is_explicitly_unsupported() -> None:
    base, desired = load_fixture_pair("create_tab_table_write")
    _, footer_desired = load_fixture_pair("section_create_footer")
    desired_raw = desired.model_dump(by_alias=True, exclude_none=True)
    footer_raw = footer_desired.model_dump(by_alias=True, exclude_none=True)
    desired_raw["tabs"][1]["documentTab"]["footers"] = footer_raw["tabs"][0]["documentTab"][
        "footers"
    ]
    desired_with_footer = Document.model_validate(desired_raw)

    with pytest.raises(UnsupportedSpikeError, match="cannot safely create headers/footers"):
        lower_semantic_diff_batches(base, desired_with_footer)


def _strip_indices(elements: list[dict]) -> None:
    for element in elements:
        element.pop("startIndex", None)
        element.pop("endIndex", None)
        paragraph = element.get("paragraph")
        if isinstance(paragraph, dict):
            for child in paragraph.get("elements", []):
                child.pop("startIndex", None)
                child.pop("endIndex", None)
        table = element.get("table")
        if isinstance(table, dict):
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    _strip_indices(cell.get("content", []))
