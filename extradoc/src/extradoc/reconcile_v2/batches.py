"""Plan multi-batch request sequences for ``reconcile_v2``."""

from __future__ import annotations

import copy
import hashlib
from typing import TYPE_CHECKING, Any

from extradoc.api_types._generated import Document
from extradoc.indexer import utf16_len
from extradoc.mock.api import MockGoogleDocsAPI
from extradoc.reconcile_v2.canonical import canonicalize_document
from extradoc.reconcile_v2.diff import (
    CreateFootnoteEdit,
    CreateSectionAttachmentEdit,
    DeleteListBlockEdit,
    DeleteTableBlockEdit,
    InsertListBlockEdit,
    InsertTableBlockEdit,
    ReplaceNamedRangesEdit,
    ReplaceParagraphSliceEdit,
    diff_documents,
)
from extradoc.reconcile_v2.errors import UnsupportedSpikeError
from extradoc.reconcile_v2.executor import resolve_deferred_placeholders
from extradoc.reconcile_v2.ir import (
    FootnoteRefIR,
    ParagraphIR,
    PositionEdge,
    StoryIR,
    TabIR,
    TableIR,
    TextSpanIR,
)
from extradoc.reconcile_v2.layout import ParagraphLocation, build_body_layout
from extradoc.reconcile_v2.lower import _content_edit_order_key, lower_document_edits
from extradoc.reconcile_v2.requests import (
    make_add_document_tab,
    make_create_footer,
    make_create_footnote,
    make_create_header,
    make_create_named_range,
    make_insert_table,
    make_insert_text_in_story,
    make_update_section_attachment,
)

if TYPE_CHECKING:
    from extradoc.reconcile_v2.diff import SemanticEdit
    from extradoc.reconcile_v2.ir import BlockIR, CellIR


def lower_document_batches(
    base: Document,
    desired: Document,
    *,
    transport_base: Document | None = None,
) -> list[list[dict[str, Any]]]:
    """Lower the supported reconcile_v2 slice into one or more request batches."""
    edits = diff_documents(base, desired)
    batches = _plan_new_tab_batches(base, desired)
    attachment_batches, remaining_edits = _plan_attachment_batches(
        base,
        edits,
        batch_offset=len(batches),
    )
    batches.extend(attachment_batches)
    footnote_edits = [
        edit for edit in remaining_edits if isinstance(edit, CreateFootnoteEdit)
    ]
    remaining_edits = [
        edit for edit in remaining_edits if not isinstance(edit, CreateFootnoteEdit)
    ]
    if remaining_edits:
        if _should_iteratively_batch_content(remaining_edits):
            batches.extend(
                _plan_iterative_content_batches(
                    transport_base or base,
                    remaining_edits,
                    desired,
                )
            )
        else:
            matched_requests = lower_document_edits(base, remaining_edits, desired=desired)
            if matched_requests:
                batches.append(matched_requests)
    if footnote_edits:
        shadow_base = _apply_shadow_batches(transport_base or base, batches)
        footnote_batches, unresolved_edits = _plan_footnote_batches(
            shadow_base,
            footnote_edits,
            batch_offset=len(batches),
        )
        if unresolved_edits:
            raise UnsupportedSpikeError(
                "reconcile_v2 could not resolve post-content footnote insertion anchors"
            )
        batches.extend(footnote_batches)
    return batches


def _should_iteratively_batch_content(edits: list[SemanticEdit]) -> bool:
    content_edits = [edit for edit in edits if not isinstance(edit, ReplaceNamedRangesEdit)]
    body_delete_count = 0
    has_table_delete = False
    for edit in content_edits:
        if isinstance(edit, DeleteTableBlockEdit):
            has_table_delete = True
            body_delete_count += 1
        elif isinstance(edit, DeleteListBlockEdit) or (
            isinstance(edit, ReplaceParagraphSliceEdit)
            and edit.story_id == f"{edit.tab_id}:body"
            and edit.delete_block_count > 0
        ):
            body_delete_count += 1
    return has_table_delete and body_delete_count > 1


def _plan_iterative_content_batches(
    base: Document,
    _edits: list[SemanticEdit],
    desired: Document,
) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current_base = copy.deepcopy(base)
    desired_content = _document_without_named_ranges(desired)
    seen_state_hashes: set[str] = set()
    while True:
        state_hash = hashlib.sha256(
            current_base.model_dump_json(by_alias=True, exclude_none=True).encode("utf-8")
        ).hexdigest()
        if state_hash in seen_state_hashes:
            raise UnsupportedSpikeError(
                "reconcile_v2 iterative content planning entered a repeated state "
                "while lowering a mixed body rewrite"
            )
        seen_state_hashes.add(state_hash)
        current_content_base = _document_without_named_ranges(current_base)
        current_edits = diff_documents(current_content_base, desired_content)
        content_edits = [
            edit
            for edit in current_edits
            if not isinstance(edit, ReplaceNamedRangesEdit | CreateFootnoteEdit)
        ]
        if not content_edits:
            break
        content_edits.sort(
            key=lambda edit: _content_edit_order_key(0, edit)  # type: ignore[arg-type]
        )
        requests: list[dict[str, Any]] = []
        next_base: Document | None = None
        best_remaining_count = len(content_edits)
        for start_index in range(len(content_edits)):
            for next_batch_edits in _iterative_batch_candidates(content_edits, start_index):
                try:
                    candidate_requests = lower_document_edits(
                        current_base,
                        next_batch_edits,
                        desired=desired,
                    )
                except UnsupportedSpikeError:
                    continue
                if not candidate_requests:
                    continue
                shadow = MockGoogleDocsAPI(current_base)
                try:
                    shadow._batch_update_raw(candidate_requests)
                except Exception:
                    continue
                candidate_next_base = shadow.get()
                candidate_remaining_count = len(
                    [
                        edit
                        for edit in diff_documents(
                            _document_without_named_ranges(candidate_next_base),
                            desired_content,
                        )
                        if not isinstance(edit, ReplaceNamedRangesEdit | CreateFootnoteEdit)
                    ]
                )
                if candidate_remaining_count < best_remaining_count:
                    best_remaining_count = candidate_remaining_count
                    requests = candidate_requests
                    next_base = candidate_next_base
                    if best_remaining_count == 0:
                        break
            if best_remaining_count == 0:
                break
        if not requests:
            break
        if best_remaining_count >= len(content_edits):
            raise UnsupportedSpikeError(
                "reconcile_v2 iterative content planning could not find a batch "
                "that reduced the remaining mixed body rewrite"
            )
        batches.append(requests)
        if next_base is None:
            shadow = MockGoogleDocsAPI(current_base)
            shadow._batch_update_raw(requests)
            next_base = shadow.get()
        current_base = next_base

    named_range_edits = [
        edit
        for edit in diff_documents(_document_without_named_ranges(current_base), desired)
        if isinstance(edit, ReplaceNamedRangesEdit)
    ]
    if named_range_edits:
        requests = lower_document_edits(current_base, named_range_edits, desired=desired)
        if requests:
            batches.append(requests)
    return batches


def _document_without_named_ranges(document: Document) -> Document:
    raw = document.model_dump(by_alias=True, exclude_none=True)
    for tab in raw.get("tabs", []):
        document_tab = tab.get("documentTab")
        if not isinstance(document_tab, dict):
            continue
        document_tab["namedRanges"] = {}
    return Document.model_validate(raw)


def _next_iterative_content_group_end(
    edits: list[SemanticEdit],
    start_index: int,
) -> int:
    anchor = _iterative_body_insert_anchor(edits[start_index])
    if anchor is None:
        return start_index + 1
    end_index = start_index + 1
    while end_index < len(edits) and _iterative_body_insert_anchor(edits[end_index]) == anchor:
        end_index += 1
    return end_index


def _iterative_batch_candidates(
    edits: list[SemanticEdit],
    start_index: int,
) -> list[list[SemanticEdit]]:
    next_index = _next_iterative_content_group_end(edits, start_index)
    if next_index == start_index + 1:
        return [edits[start_index:next_index]]
    group = edits[start_index:next_index]
    candidates = [group]
    for index in range(next_index - 1, start_index - 1, -1):
        candidates.append(edits[index : index + 1])
    return candidates


def _iterative_body_insert_anchor(
    edit: SemanticEdit,
) -> tuple[str, int, int, int | None] | None:
    if isinstance(edit, (InsertTableBlockEdit, InsertListBlockEdit)):
        return (
            edit.tab_id,
            edit.section_index,
            edit.block_index,
            edit.body_anchor_block_index,
        )
    if (
        isinstance(edit, ReplaceParagraphSliceEdit)
        and edit.section_index is not None
        and edit.story_id == f"{edit.tab_id}:body"
        and (
            edit.delete_block_count == 0
            or (edit.delete_block_count > 0 and not edit.inserted_paragraphs)
        )
    ):
        return (
            edit.tab_id,
            edit.section_index,
            edit.start_block_index,
            edit.body_anchor_block_index,
        )
    return None


def _plan_attachment_batches(
    base: Document,
    edits: list[SemanticEdit],
    *,
    batch_offset: int,
) -> tuple[list[list[dict[str, Any]]], list[SemanticEdit]]:
    create_edits = [
        edit for edit in edits if isinstance(edit, CreateSectionAttachmentEdit)
    ]
    if not create_edits:
        return [], edits

    creation_batch: list[dict[str, Any]] = []
    population_batch: list[dict[str, Any]] = []
    additional_attach_batch: list[dict[str, Any]] = []
    body_layouts: dict[str, object] = {}

    grouped_create_edits: dict[tuple[str, str], list[CreateSectionAttachmentEdit]] = {}
    for edit in create_edits:
        key = (edit.attachment_kind, edit.desired_story.id)
        grouped_create_edits.setdefault(key, []).append(edit)

    for grouped in grouped_create_edits.values():
        first_edit = grouped[0]
        section_break_index = _section_break_index(
            body_layouts,
            base,
            tab_id=first_edit.tab_id,
            section_index=first_edit.section_index,
        )
        request_index = len(creation_batch)
        if first_edit.attachment_kind == "headers":
            creation_batch.append(
                make_create_header(
                    header_type=first_edit.slot,
                    tab_id=first_edit.tab_id if section_break_index is not None else None,
                    section_break_index=section_break_index,
                )
            )
            response_path = "createHeader.headerId"
        elif first_edit.attachment_kind == "footers":
            creation_batch.append(
                make_create_footer(
                    footer_type=first_edit.slot,
                    tab_id=first_edit.tab_id if section_break_index is not None else None,
                    section_break_index=section_break_index,
                )
            )
            response_path = "createFooter.footerId"
        else:
            raise UnsupportedSpikeError(
                f"Unsupported attachment kind for creation: {first_edit.attachment_kind}"
            )
        deferred_story_id = _deferred_id(
            placeholder=f"{first_edit.attachment_kind[:-1]}-{first_edit.tab_id}-{first_edit.section_index}-{first_edit.slot}",
            batch_index=batch_offset,
            request_index=request_index,
            response_path=response_path,
        )
        population_batch.extend(
            _lower_blocks_into_empty_story(
                first_edit.desired_story.blocks,
                story_start_index=0,
                tab_id=first_edit.tab_id,
                segment_id=deferred_story_id,
            )
        )
        for additional_edit in grouped[1:]:
            boundary = _section_boundary_for_update(
                body_layouts,
                base,
                tab_id=additional_edit.tab_id,
                section_index=additional_edit.section_index,
            )
            additional_attach_batch.append(
                make_update_section_attachment(
                    start_index=boundary["startIndex"],
                    end_index=boundary["endIndex"],
                    tab_id=additional_edit.tab_id,
                    attachment_kind=additional_edit.attachment_kind,
                    slot=additional_edit.slot,
                    attachment_id=deferred_story_id,
                )
            )

    remaining_edits: list[SemanticEdit] = []
    for edit in edits:
        if isinstance(edit, CreateSectionAttachmentEdit):
            continue
        remaining_edits.append(edit)

    batches: list[list[dict[str, Any]]] = [creation_batch]
    if population_batch or additional_attach_batch:
        batches.append([*population_batch, *additional_attach_batch])
    return batches, remaining_edits


def _plan_footnote_batches(
    base: Document,
    edits: list[SemanticEdit],
    *,
    batch_offset: int,
) -> tuple[list[list[dict[str, Any]]], list[SemanticEdit]]:
    footnote_edits = [edit for edit in edits if isinstance(edit, CreateFootnoteEdit)]
    if not footnote_edits:
        return [], edits

    creation_batch: list[dict[str, Any]] = []
    population_batch: list[dict[str, Any]] = []
    layouts: dict[str, object] = {}
    unresolved_footnotes: list[CreateFootnoteEdit] = []

    for edit in footnote_edits:
        layout = layouts.setdefault(edit.tab_id, build_body_layout(base, tab_id=edit.tab_id))
        if (
            edit.section_index >= len(layout.sections)
            or edit.block_index >= len(layout.sections[edit.section_index].block_locations)
        ):
            unresolved_footnotes.append(edit)
            continue
        paragraph = layout.sections[edit.section_index].block_locations[edit.block_index]
        if not isinstance(paragraph, ParagraphLocation):
            unresolved_footnotes.append(edit)
            continue
        request_index = len(creation_batch)
        creation_batch.append(
            make_create_footnote(
                index=paragraph.text_start_index + edit.text_offset_utf16,
                tab_id=edit.tab_id,
            )
        )
        deferred_footnote_id = _deferred_id(
            placeholder=f"footnote-{edit.tab_id}-{edit.section_index}-{edit.block_index}",
            batch_index=batch_offset,
            request_index=request_index,
            response_path="createFootnote.footnoteId",
        )
        population_batch.extend(
            _lower_blocks_into_empty_story(
                edit.desired_story.blocks,
                story_start_index=0,
                tab_id=edit.tab_id,
                segment_id=deferred_footnote_id,
            )
        )

    remaining_edits = [
        edit
        for edit in edits
        if not isinstance(edit, CreateFootnoteEdit) or edit in unresolved_footnotes
    ]
    batches: list[list[dict[str, Any]]] = []
    if creation_batch:
        batches.append(creation_batch)
    if population_batch:
        batches.append(population_batch)
    return batches, remaining_edits


def _apply_shadow_batches(
    base: Document,
    batches: list[list[dict[str, Any]]],
) -> Document:
    if not batches:
        return copy.deepcopy(base)
    shadow = MockGoogleDocsAPI(copy.deepcopy(base))
    prior_responses: list[dict[str, Any]] = []
    for batch in batches:
        resolved = resolve_deferred_placeholders(prior_responses, list(batch))
        response = shadow._batch_update_raw(resolved)
        prior_responses.append(response)
    return shadow.get()


def _plan_new_tab_batches(
    base: Document,
    desired: Document,
) -> list[list[dict[str, Any]]]:
    base_ir = canonicalize_document(base)
    desired_ir = canonicalize_document(desired)

    base_tabs_by_path = dict(_walk_tabs(base_ir.tabs))
    new_tabs = [
        (path, tab)
        for path, tab in _walk_tabs(desired_ir.tabs)
        if path not in base_tabs_by_path
    ]
    desired_raw_tabs_by_path = dict(_walk_raw_tabs(desired.model_dump(by_alias=True, exclude_none=True).get("tabs", [])))
    if not new_tabs:
        return []

    batches: list[list[dict[str, Any]]] = []
    created_tab_refs: dict[tuple[int, ...], dict[str, object]] = {}
    for path, tab in new_tabs:
        if tab.resource_graph.headers or tab.resource_graph.footers:
            raise UnsupportedSpikeError(
                "reconcile_v2 cannot safely create headers/footers on a newly added tab "
                "in a document that already has tabs; the Docs API misroutes createHeader/"
                "createFooter to the first tab"
            )

        creation_batch_index = len(batches)
        creation_batch = [
            make_add_document_tab(
                title=tab.title,
                parent_tab_id=_parent_tab_reference(
                    path=path,
                    base_tabs_by_path=base_tabs_by_path,
                    created_tab_refs=created_tab_refs,
                ),
                index=path[-1],
                icon_emoji=tab.icon_emoji,
            )
        ]
        batches.append(creation_batch)
        deferred_tab_id = _deferred_id(
            placeholder=f"new-tab-{'-'.join(str(part) for part in path)}",
            batch_index=creation_batch_index,
            request_index=0,
            response_path="addDocumentTab.tabProperties.tabId",
        )
        created_tab_refs[path] = deferred_tab_id

    population_batch: list[dict[str, Any]] = []
    deferred_followup_batch: list[dict[str, Any]] = []
    population_batch_index = len(batches)
    for path, tab in new_tabs:
        deferred_tab_id = created_tab_refs[path]
        population_requests = _lower_new_tab_body(
            tab,
            desired_raw_tab=desired_raw_tabs_by_path[path],
            deferred_tab_id=deferred_tab_id,
        )
        population_batch.extend(population_requests)
        footnote_requests, footnote_population_requests = _lower_new_tab_footnotes(
            tab,
            deferred_tab_id,
            placeholder_prefix="-".join(str(part) for part in path),
            batch_index=population_batch_index,
            request_index_offset=len(population_batch),
        )
        population_batch.extend(footnote_requests)
        if footnote_requests:
            named_range_requests = _lower_new_tab_named_ranges(
                tab,
                deferred_tab_id,
                anchors_include_footnote_refs=True,
            )
            deferred_followup_batch.extend(footnote_population_requests)
            deferred_followup_batch.extend(named_range_requests)
    if population_batch:
        batches.append(population_batch)
    if deferred_followup_batch:
        batches.append(deferred_followup_batch)
    return batches


def _lower_new_tab_body(
    tab: TabIR,
    *,
    desired_raw_tab: dict[str, object],
    deferred_tab_id: dict[str, object],
) -> list[dict[str, Any]]:
    if len(tab.body.sections) != 1:
        raise UnsupportedSpikeError(
            "reconcile_v2 currently supports creating tabs with exactly one body section"
        )
    section = tab.body.sections[0]
    if section.attachments.headers or section.attachments.footers:
        raise UnsupportedSpikeError(
            "reconcile_v2 does not yet support creating tabs with section attachments"
        )
    if not section.blocks:
        return []
    shadow_tab_id = "t.shadow"
    synthetic_base = _make_empty_shadow_tab_document(title=tab.title, tab_id=shadow_tab_id)
    synthetic_desired = _make_shadow_tab_document_from_raw(
        desired_raw_tab,
        tab_id=shadow_tab_id,
    )
    filter_named_ranges = bool(tab.resource_graph.footnotes)
    body_edits = [
        edit
        for edit in diff_documents(synthetic_base, synthetic_desired)
        if not isinstance(edit, CreateFootnoteEdit | CreateSectionAttachmentEdit)
        and not (filter_named_ranges and isinstance(edit, ReplaceNamedRangesEdit))
    ]
    return _replace_tab_id(
        lower_document_edits(synthetic_base, body_edits, desired=synthetic_desired),
        old_tab_id=shadow_tab_id,
        new_tab_id=deferred_tab_id,
    )


def _lower_new_tab_named_ranges(
    tab: TabIR,
    deferred_tab_id: dict[str, object],
    *,
    anchors_include_footnote_refs: bool = False,
) -> list[dict[str, Any]]:
    if not any(tab.annotations.named_ranges.values()):
        return []
    if len(tab.body.sections) != 1:
        raise UnsupportedSpikeError(
            "reconcile_v2 currently supports new-tab named ranges only for "
            "single-section body stories"
        )
    blocks = tab.body.sections[0].blocks
    requests: list[dict[str, Any]] = []
    for name, anchors in tab.annotations.named_ranges.items():
        for anchor in anchors:
            if anchor.start.story_id != tab.body.id or anchor.end.story_id != tab.body.id:
                raise UnsupportedSpikeError(
                    "reconcile_v2 currently supports new-tab named ranges only "
                    "in the body story"
                )
            requests.append(
                make_create_named_range(
                    name=name,
                    start_index=_resolve_new_body_position(
                        blocks,
                        position=anchor.start,
                        story_start_index=1,
                        include_footnote_refs=anchors_include_footnote_refs,
                    ),
                    end_index=_resolve_new_body_position(
                        blocks,
                        position=anchor.end,
                        story_start_index=1,
                        include_footnote_refs=anchors_include_footnote_refs,
                    ),
                    tab_id=deferred_tab_id,
                )
            )
    return requests


def _lower_new_tab_footnotes(
    tab: TabIR,
    deferred_tab_id: dict[str, object],
    *,
    placeholder_prefix: str,
    batch_index: int,
    request_index_offset: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not tab.resource_graph.footnotes:
        return [], []
    if len(tab.body.sections) != 1:
        raise UnsupportedSpikeError(
            "reconcile_v2 currently supports new-tab footnotes only for "
            "single-section body stories"
        )
    blocks = tab.body.sections[0].blocks
    if not all(isinstance(block, ParagraphIR) for block in blocks):
        raise UnsupportedSpikeError(
            "reconcile_v2 currently supports new-tab footnotes only in "
            "paragraph-only body stories"
        )

    create_requests: list[dict[str, Any]] = []
    population_requests: list[dict[str, Any]] = []
    anchors = sorted(
        _new_tab_footnote_anchors(blocks, tab.resource_graph.footnotes),
        key=lambda item: (item["index"], item["story"].id),
        reverse=True,
    )
    for ordinal, anchor in enumerate(anchors):
        create_requests.append(
            make_create_footnote(
                index=anchor["index"],
                tab_id=deferred_tab_id,
            )
        )
        deferred_footnote_id = _deferred_id(
            placeholder=f"new-tab-footnote-{placeholder_prefix}-{ordinal}",
            batch_index=batch_index,
            request_index=request_index_offset + ordinal,
            response_path="createFootnote.footnoteId",
        )
        population_requests.extend(
            _lower_blocks_into_empty_story(
                anchor["story"].blocks,
                story_start_index=0,
                tab_id=deferred_tab_id,
                segment_id=deferred_footnote_id,
            )
        )
    return create_requests, population_requests


def _lower_blocks_into_empty_story(
    blocks: list[BlockIR],
    *,
    story_start_index: int,
    tab_id: Any,
    segment_id: Any,
) -> list[dict[str, Any]]:
    if not blocks:
        return []
    if all(isinstance(block, ParagraphIR) for block in blocks):
        text = "\n".join(_paragraph_text(block) for block in blocks)
        if not text:
            return []
        return [
            make_insert_text_in_story(
                index=story_start_index,
                tab_id=tab_id,
                segment_id=segment_id,
                text=text,
            )
        ]
    if len(blocks) == 1 and isinstance(blocks[0], TableIR):
        return _lower_table_into_empty_story(
            blocks[0],
            story_start_index=story_start_index,
            tab_id=tab_id,
            segment_id=segment_id,
        )
    raise UnsupportedSpikeError(
        "reconcile_v2 currently supports creating new-story content only for "
        "paragraph-only stories or a single recursively-populated table block"
    )


def _lower_table_into_empty_story(
    table: TableIR,
    *,
    story_start_index: int,
    tab_id: Any,
    segment_id: Any,
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
            "reconcile_v2 currently requires rectangular tables for creation"
        )
    if table.pinned_header_rows or table.merge_regions:
        raise UnsupportedSpikeError(
            "reconcile_v2 currently supports plain unmerged table creation only"
        )

    requests: list[dict[str, Any]] = [
        make_insert_table(
            rows=row_count,
            columns=column_count,
            tab_id=tab_id,
            segment_id=segment_id,
            index=story_start_index,
        )
    ]
    for row_index in range(row_count - 1, -1, -1):
        row = table.rows[row_index]
        for column_index in range(column_count - 1, -1, -1):
            cell = row.cells[column_index]
            if cell.row_span != 1 or cell.column_span != 1 or cell.merge_head is not None:
                raise UnsupportedSpikeError(
                    "reconcile_v2 currently supports unmerged cells only"
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
                    tab_id=tab_id,
                    segment_id=segment_id,
                )
            )
    return requests


def _lower_cell_into_empty_story(
    cell: CellIR,
    *,
    story_start_index: int,
    tab_id: Any,
    segment_id: Any,
) -> list[dict[str, Any]]:
    return _lower_blocks_into_empty_story(
        cell.content.blocks,
        story_start_index=story_start_index,
        tab_id=tab_id,
        segment_id=segment_id,
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


def _new_tab_footnote_anchors(
    blocks: list[ParagraphIR],
    footnotes: dict[str, StoryIR],
) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    current = 1
    for block_index, block in enumerate(blocks):
        paragraph_start = current
        text_offset = 0
        for inline in block.inlines:
            if isinstance(inline, TextSpanIR):
                text_offset += utf16_len(inline.text)
            elif isinstance(inline, FootnoteRefIR):
                story = footnotes.get(inline.ref)
                if story is None:
                    raise UnsupportedSpikeError(
                        f"Missing desired footnote story for ref {inline.ref!r}"
                    )
                anchors.append(
                    {
                        "index": paragraph_start + text_offset,
                        "story": story,
                        "block_index": block_index,
                    }
                )
        current = paragraph_start + utf16_len(_paragraph_text(block)) + 1
    return anchors


def _resolve_new_body_position(
    blocks: list[Any],
    *,
    position: Any,
    story_start_index: int,
    include_footnote_refs: bool = False,
) -> int:
    path = position.path
    if path.section_index not in (None, 0):
        raise UnsupportedSpikeError(
            "reconcile_v2 currently supports new-tab named ranges only in section 0"
        )
    if path.node_path:
        raise UnsupportedSpikeError(
            "reconcile_v2 currently supports new-tab named ranges only on "
            "top-level body paragraphs"
        )
    current = story_start_index
    for block_index, block in enumerate(blocks):
        if not isinstance(block, ParagraphIR):
            raise UnsupportedSpikeError(
                "reconcile_v2 currently supports new-tab named ranges only for "
                "paragraph-only body stories"
            )
        paragraph_start = current
        if block_index == path.block_index:
            inline_start = paragraph_start
            for inline_index, inline in enumerate(block.inlines):
                inline_length = _new_body_inline_transport_length(
                    inline,
                    include_footnote_refs=include_footnote_refs,
                )
                if path.inline_index == inline_index:
                    if path.text_offset_utf16 is not None:
                        return inline_start + path.text_offset_utf16
                    if path.edge == PositionEdge.BEFORE:
                        return inline_start
                    if path.edge == PositionEdge.AFTER:
                        return inline_start + inline_length
                    return inline_start
                inline_start += inline_length
            paragraph_end = paragraph_start + _new_body_paragraph_transport_length(
                block,
                include_footnote_refs=include_footnote_refs,
            )
            if path.edge == PositionEdge.BEFORE:
                return paragraph_start
            if path.edge == PositionEdge.AFTER:
                return paragraph_end
            if path.text_offset_utf16 is not None:
                return paragraph_start + path.text_offset_utf16
            return paragraph_start
        current = paragraph_start + _new_body_paragraph_transport_length(
            block,
            include_footnote_refs=include_footnote_refs,
        ) + 1
    raise UnsupportedSpikeError(
        "reconcile_v2 could not resolve a new-tab named range anchor into the created story"
    )


def _new_body_paragraph_transport_length(
    paragraph: ParagraphIR,
    *,
    include_footnote_refs: bool,
) -> int:
    return sum(
        _new_body_inline_transport_length(
            inline,
            include_footnote_refs=include_footnote_refs,
        )
        for inline in paragraph.inlines
    )


def _new_body_inline_transport_length(
    inline: object,
    *,
    include_footnote_refs: bool,
) -> int:
    if isinstance(inline, TextSpanIR):
        return utf16_len(inline.text)
    if isinstance(inline, FootnoteRefIR):
        return 1 if include_footnote_refs else 0
    raise UnsupportedSpikeError(
        "reconcile_v2 currently supports new-tab named ranges only for "
        "plain text plus footnote-reference paragraphs"
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


def _section_break_index(
    body_layouts: dict[str, object],
    base: Document,
    *,
    tab_id: str,
    section_index: int,
) -> int | None:
    if section_index == 0:
        return None
    layout = body_layouts.setdefault(tab_id, build_body_layout(base, tab_id=tab_id))
    boundary = layout.sections[section_index].incoming_boundary
    if boundary is None:
        raise UnsupportedSpikeError(
            f"Missing section boundary for tab {tab_id} section {section_index}"
        )
    return boundary.section_break_start_index


def _section_boundary_for_update(
    body_layouts: dict[str, object],
    base: Document,
    *,
    tab_id: str,
    section_index: int,
) -> dict[str, int]:
    if section_index == 0:
        raise UnsupportedSpikeError(
            "reconcile_v2 does not yet support first-section attachment reassignment "
            "through updateSectionStyle"
        )
    layout = body_layouts.setdefault(tab_id, build_body_layout(base, tab_id=tab_id))
    boundary = layout.sections[section_index].incoming_boundary
    if boundary is None:
        raise UnsupportedSpikeError(
            f"Missing section boundary for tab {tab_id} section {section_index}"
        )
    return {
        "startIndex": boundary.section_break_start_index,
        "endIndex": boundary.section_break_end_index,
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


def _walk_raw_tabs(
    tabs: list[dict[str, object]],
    prefix: tuple[int, ...] = (),
) -> list[tuple[tuple[int, ...], dict[str, object]]]:
    pairs: list[tuple[tuple[int, ...], dict[str, object]]] = []
    for index, tab in enumerate(tabs):
        path = (*prefix, index)
        pairs.append((path, tab))
        child_tabs = tab.get("childTabs", [])
        if isinstance(child_tabs, list):
            pairs.extend(_walk_raw_tabs(child_tabs, path))
    return pairs


def _make_empty_shadow_tab_document(*, title: str, tab_id: str) -> Document:
    return Document.model_validate(
        {
            "documentId": "new-tab-shadow",
            "title": title,
            "tabs": [
                {
                    "tabProperties": {"tabId": tab_id, "title": title, "index": 0},
                    "documentTab": {
                        "body": {
                            "content": [
                                {
                                    "endIndex": 1,
                                    "sectionBreak": {
                                        "sectionStyle": {
                                            "columnSeparatorStyle": "NONE"
                                        }
                                    },
                                },
                                {
                                    "startIndex": 1,
                                    "endIndex": 2,
                                    "paragraph": {
                                        "elements": [
                                            {
                                                "startIndex": 1,
                                                "endIndex": 2,
                                                "textRun": {"content": "\n"},
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
    )


def _make_shadow_tab_document_from_raw(raw_tab: dict[str, object], *, tab_id: str) -> Document:
    cloned_tab = copy.deepcopy(raw_tab)
    tab_props = cloned_tab.setdefault("tabProperties", {})
    if isinstance(tab_props, dict):
        tab_props["tabId"] = tab_id
        tab_props["index"] = 0
    cloned_tab.pop("childTabs", None)
    return Document.model_validate(
        {
            "documentId": "new-tab-shadow",
            "title": tab_props.get("title", "Shadow Tab") if isinstance(tab_props, dict) else "Shadow Tab",
            "tabs": [cloned_tab],
        }
    )


def _replace_tab_id(
    requests: list[dict[str, Any]],
    *,
    old_tab_id: str,
    new_tab_id: dict[str, object],
) -> list[dict[str, Any]]:
    replaced = copy.deepcopy(requests)

    def _replace(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: _replace(item) for key, item in value.items()}
        if isinstance(value, list):
            return [_replace(item) for item in value]
        if value == old_tab_id:
            return new_tab_id
        return value

    return [_replace(request) for request in replaced]


def _parent_tab_reference(
    *,
    path: tuple[int, ...],
    base_tabs_by_path: dict[tuple[int, ...], TabIR],
    created_tab_refs: dict[tuple[int, ...], dict[str, object]],
) -> str | dict[str, object] | None:
    if len(path) == 1:
        return None
    parent_path = path[:-1]
    if parent_path in created_tab_refs:
        return created_tab_refs[parent_path]
    parent = base_tabs_by_path.get(parent_path)
    if parent is None:
        raise UnsupportedSpikeError(
            f"Could not resolve parent tab for new tab at path {path!r}"
        )
    return parent.id
