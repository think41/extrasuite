from __future__ import annotations

from extradoc.api_types._generated import BatchUpdateDocumentRequest, Document
from extradoc.reconcile_v2.api import lower_semantic_diff_batches, reconcile

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


def test_reconcile_returns_batch_update_models() -> None:
    base, desired = load_fixture_pair("create_tab_table_write")

    batches = reconcile(base, desired)

    assert all(isinstance(batch, BatchUpdateDocumentRequest) for batch in batches)
    assert [batch.model_dump(by_alias=True, exclude_none=True)["requests"] for batch in batches] == (
        load_expected_lowered_batches("create_tab_table_write")
    )


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
