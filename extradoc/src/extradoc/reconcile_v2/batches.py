"""Plan narrow multi-batch request sequences for confidence-sprint scenarios."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from extradoc.reconcile_v2.canonical import canonicalize_document
from extradoc.reconcile_v2.diff import diff_documents
from extradoc.reconcile_v2.errors import UnsupportedSpikeError
from extradoc.reconcile_v2.ir import ParagraphIR, TabIR, TableIR, TextSpanIR
from extradoc.reconcile_v2.lower import lower_document_edits
from extradoc.reconcile_v2.requests import (
    make_add_document_tab,
    make_insert_table,
    make_insert_text,
)

if TYPE_CHECKING:
    from extradoc.api_types._generated import Document
    from extradoc.reconcile_v2.ir import BlockIR, CellIR


def lower_document_batches(
    base: Document,
    desired: Document,
) -> list[list[dict[str, Any]]]:
    """Lower the supported reconcile_v2 slice into one or more request batches."""
    batches = _plan_new_tab_batches(base, desired)
    matched_requests = lower_document_edits(base, diff_documents(base, desired))
    if matched_requests:
        batches.append(matched_requests)
    return batches


def _plan_new_tab_batches(
    base: Document,
    desired: Document,
) -> list[list[dict[str, Any]]]:
    base_ir = canonicalize_document(base)
    desired_ir = canonicalize_document(desired)

    base_paths = {path for path, _ in _walk_tabs(base_ir.tabs)}
    new_tabs = [
        (path, tab)
        for path, tab in _walk_tabs(desired_ir.tabs)
        if path not in base_paths
    ]
    if not new_tabs:
        return []

    creation_batch: list[dict[str, Any]] = []
    population_batches: list[list[dict[str, Any]]] = []
    for path, tab in new_tabs:
        if len(path) != 1:
            raise UnsupportedSpikeError(
                "reconcile_v2 multi-batch spike currently supports only top-level tab creation"
            )
        if tab.parent_tab_id is not None:
            raise UnsupportedSpikeError(
                "reconcile_v2 multi-batch spike does not yet support child-tab creation"
            )
        if tab.resource_graph.headers or tab.resource_graph.footers or tab.resource_graph.footnotes:
            raise UnsupportedSpikeError(
                "reconcile_v2 multi-batch spike does not yet support creating tabs with attached stories"
            )
        if any(tab.annotations.named_ranges.values()):
            raise UnsupportedSpikeError(
                "reconcile_v2 multi-batch spike does not yet support creating tabs with named ranges"
            )

        creation_request_index = len(creation_batch)
        creation_batch.append(make_add_document_tab(title=tab.title, index=path[0]))
        deferred_tab_id = _deferred_id(
            placeholder=f"new-tab-{path[0]}",
            batch_index=0,
            request_index=creation_request_index,
            response_path="addDocumentTab.tabProperties.tabId",
        )
        population_requests = _lower_new_tab_body(tab, deferred_tab_id)
        if population_requests:
            population_batches.append(population_requests)

    return [creation_batch, *population_batches]


def _lower_new_tab_body(tab: TabIR, deferred_tab_id: dict[str, object]) -> list[dict[str, Any]]:
    if len(tab.body.sections) != 1:
        raise UnsupportedSpikeError(
            "reconcile_v2 multi-batch spike supports creating tabs with exactly one body section"
        )
    section = tab.body.sections[0]
    if section.attachments.headers or section.attachments.footers:
        raise UnsupportedSpikeError(
            "reconcile_v2 multi-batch spike does not yet support creating tabs with section attachments"
        )
    return _lower_blocks_into_empty_story(
        section.blocks,
        story_start_index=1,
        deferred_tab_id=deferred_tab_id,
    )


def _lower_blocks_into_empty_story(
    blocks: list[BlockIR],
    *,
    story_start_index: int,
    deferred_tab_id: dict[str, object],
) -> list[dict[str, Any]]:
    if not blocks:
        return []
    if all(isinstance(block, ParagraphIR) for block in blocks):
        text = "\n".join(_paragraph_text(block) for block in blocks)
        if not text:
            return []
        return [
            make_insert_text(
                index=story_start_index,
                tab_id=deferred_tab_id,
                text=text,
            )
        ]
    if len(blocks) == 1 and isinstance(blocks[0], TableIR):
        return _lower_table_into_empty_story(
            blocks[0],
            story_start_index=story_start_index,
            deferred_tab_id=deferred_tab_id,
        )
    raise UnsupportedSpikeError(
        "reconcile_v2 multi-batch spike supports creating new-story content only for "
        "paragraph-only stories or a single recursively-populated table block"
    )


def _lower_table_into_empty_story(
    table: TableIR,
    *,
    story_start_index: int,
    deferred_tab_id: dict[str, object],
) -> list[dict[str, Any]]:
    row_count = len(table.rows)
    column_count = max((len(row.cells) for row in table.rows), default=0)
    if row_count == 0 or column_count == 0:
        return []
    if any(
        len(row.cells) != column_count
        for row in table.rows
    ):
        raise UnsupportedSpikeError(
            "reconcile_v2 multi-batch spike requires rectangular tables for creation"
        )
    if table.pinned_header_rows or table.merge_regions:
        raise UnsupportedSpikeError(
            "reconcile_v2 multi-batch spike currently supports plain unmerged table creation only"
        )

    requests: list[dict[str, Any]] = [
        make_insert_table(
            rows=row_count,
            columns=column_count,
            tab_id=deferred_tab_id,
            index=story_start_index,
        )
    ]
    for row_index in range(row_count - 1, -1, -1):
        row = table.rows[row_index]
        for column_index in range(column_count - 1, -1, -1):
            cell = row.cells[column_index]
            if cell.row_span != 1 or cell.column_span != 1 or cell.merge_head is not None:
                raise UnsupportedSpikeError(
                    "reconcile_v2 multi-batch spike currently supports unmerged cells only"
                )
            cell_start = _cell_content_start(
                story_start_index=story_start_index,
                row_index=row_index,
                column_index=column_index,
                column_count=column_count,
            )
            requests.extend(
                _lower_cell_into_empty_story(
                    cell,
                    story_start_index=cell_start,
                    deferred_tab_id=deferred_tab_id,
                )
            )
    return requests


def _lower_cell_into_empty_story(
    cell: CellIR,
    *,
    story_start_index: int,
    deferred_tab_id: dict[str, object],
) -> list[dict[str, Any]]:
    return _lower_blocks_into_empty_story(
        cell.content.blocks,
        story_start_index=story_start_index,
        deferred_tab_id=deferred_tab_id,
    )


def _cell_content_start(
    *,
    story_start_index: int,
    row_index: int,
    column_index: int,
    column_count: int,
) -> int:
    return story_start_index + 4 + row_index * (1 + 2 * column_count) + 2 * column_index


def _paragraph_text(paragraph: ParagraphIR) -> str:
    return "".join(
        inline.text for inline in paragraph.inlines if isinstance(inline, TextSpanIR)
    )


def _deferred_id(
    *,
    placeholder: str,
    batch_index: int,
    request_index: int,
    response_path: str,
) -> dict[str, object]:
    return {
        "placeholder": placeholder,
        "batch_index": batch_index,
        "request_index": request_index,
        "response_path": response_path,
    }


def _walk_tabs(
    tabs: list[TabIR],
    prefix: tuple[int, ...] = (),
) -> list[tuple[tuple[int, ...], TabIR]]:
    pairs: list[tuple[tuple[int, ...], TabIR]] = []
    for index, tab in enumerate(tabs):
        path = (*prefix, index)
        pairs.append((path, tab))
        pairs.extend(_walk_tabs(tab.child_tabs, path))
    return pairs
