"""Compute a semantic diff over the supported IR surface."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from itertools import accumulate
from typing import TYPE_CHECKING, TypeVar

from extradoc.indexer import utf16_len
from extradoc.reconcile_v2.canonical import canonicalize_document_ir
from extradoc.reconcile_v2.errors import UnsupportedSpikeError
from extradoc.reconcile_v2.ir import (
    AnchorRangeIR,
    FootnoteRefIR,
    ListIR,
    OpaqueBlockIR,
    OpaqueInlineIR,
    PageBreakIR,
    ParagraphIR,
    PositionIR,
    SectionIR,
    StoryIR,
    TableIR,
    TextSpanIR,
    TocIR,
)
from extradoc.reconcile_v2.parse import parse_document

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from extradoc.api_types._generated import Document
    from extradoc.reconcile_v2.ir import (
        BlockIR,
        DocumentIR,
        TabIR,
    )


T = TypeVar("T")


@dataclass(slots=True)
class InsertSectionEdit:
    tab_id: str
    section_index: int
    split_after_block_index: int
    inserted_block_count: int


@dataclass(slots=True)
class DeleteSectionEdit:
    tab_id: str
    section_index: int
    block_count: int


@dataclass(slots=True)
class CreateSectionAttachmentEdit:
    tab_id: str
    section_index: int
    attachment_kind: str
    slot: str
    desired_story: StoryIR


@dataclass(slots=True)
class DeleteSectionAttachmentEdit:
    tab_id: str
    section_index: int
    attachment_kind: str
    slot: str
    story_id: str


@dataclass(slots=True)
class CreateFootnoteEdit:
    tab_id: str
    section_index: int
    block_index: int
    text_offset_utf16: int
    desired_story: StoryIR


@dataclass(slots=True)
class UpdateParagraphRoleEdit:
    tab_id: str
    section_index: int
    block_index: int
    before_role: str
    after_role: str


@dataclass(slots=True)
class ReplaceParagraphTextEdit:
    tab_id: str
    story_id: str
    section_index: int | None
    block_index: int
    desired_paragraph: ParagraphIR


@dataclass(slots=True)
class AppendListItemsEdit:
    tab_id: str
    section_index: int
    block_index: int
    list_kind: str
    appended_items: tuple[ListItemFragment, ...]


@dataclass(slots=True)
class ReplaceListSpecEdit:
    tab_id: str
    section_index: int
    block_index: int
    before_kind: str
    after_kind: str


@dataclass(slots=True)
class RelevelListItemsEdit:
    tab_id: str
    section_index: int
    block_index: int
    list_kind: str
    before_levels: tuple[int, ...]
    after_levels: tuple[int, ...]


@dataclass(slots=True)
class UpdateListItemRolesEdit:
    tab_id: str
    section_index: int
    block_index: int
    list_kind: str
    item_indexes: tuple[int, ...]
    before_roles: tuple[str, ...]
    after_roles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParagraphFragment:
    paragraph: ParagraphIR

    @property
    def role(self) -> str:
        return self.paragraph.role

    @property
    def text(self) -> str:
        return _paragraph_text(self.paragraph)


@dataclass(slots=True)
class ReplaceParagraphSliceEdit:
    tab_id: str
    story_id: str
    section_index: int | None
    start_block_index: int
    delete_block_count: int
    inserted_paragraphs: tuple[ParagraphFragment, ...]
    body_anchor_block_index: int | None = None


@dataclass(slots=True)
class InsertListBlockEdit:
    tab_id: str
    section_index: int
    block_index: int
    list_kind: str
    items: tuple[ListItemFragment, ...]
    body_anchor_block_index: int | None = None


@dataclass(slots=True)
class DeleteListBlockEdit:
    tab_id: str
    section_index: int
    block_index: int
    body_anchor_block_index: int | None = None


@dataclass(slots=True)
class InsertTableBlockEdit:
    tab_id: str
    section_index: int
    block_index: int
    table: TableIR
    body_anchor_block_index: int | None = None


@dataclass(slots=True)
class DeleteTableBlockEdit:
    tab_id: str
    section_index: int
    block_index: int
    body_anchor_block_index: int | None = None


@dataclass(slots=True)
class InsertPageBreakBlockEdit:
    tab_id: str
    section_index: int
    block_index: int
    body_anchor_block_index: int | None = None


@dataclass(slots=True)
class DeletePageBreakBlockEdit:
    tab_id: str
    section_index: int
    block_index: int
    body_anchor_block_index: int | None = None


@dataclass(slots=True)
class ReplaceNamedRangesEdit:
    tab_id: str
    name: str
    before_count: int
    desired_ranges: tuple[AnchorRangeIR, ...]


@dataclass(slots=True)
class InsertTableRowEdit:
    tab_id: str
    section_index: int
    block_index: int
    row_index: int
    insert_below: bool
    inserted_cells: tuple[str, ...] = ()


@dataclass(slots=True)
class DeleteTableRowEdit:
    tab_id: str
    section_index: int
    block_index: int
    row_index: int


@dataclass(slots=True)
class InsertTableColumnEdit:
    tab_id: str
    section_index: int
    block_index: int
    column_index: int
    insert_right: bool
    inserted_cells: tuple[str, ...] = ()


@dataclass(slots=True)
class DeleteTableColumnEdit:
    tab_id: str
    section_index: int
    block_index: int
    column_index: int


@dataclass(slots=True)
class MergeTableCellsEdit:
    tab_id: str
    section_index: int
    block_index: int
    row_index: int
    column_index: int
    row_span: int
    column_span: int


@dataclass(slots=True)
class UnmergeTableCellsEdit:
    tab_id: str
    section_index: int
    block_index: int
    row_index: int
    column_index: int
    row_span: int
    column_span: int


@dataclass(slots=True)
class UpdateTablePinnedHeaderRowsEdit:
    tab_id: str
    section_index: int
    block_index: int
    pinned_header_rows: int


@dataclass(slots=True)
class UpdateTableRowStyleEdit:
    tab_id: str
    section_index: int
    block_index: int
    row_index: int
    style: dict[str, object]
    fields: tuple[str, ...]


@dataclass(slots=True)
class UpdateTableColumnPropertiesEdit:
    tab_id: str
    section_index: int
    block_index: int
    column_index: int
    properties: dict[str, object]
    fields: tuple[str, ...]


@dataclass(slots=True)
class UpdateTableCellStyleEdit:
    tab_id: str
    section_index: int
    block_index: int
    row_index: int
    column_index: int
    style: dict[str, object]
    fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ListItemFragment:
    level: int
    text: str


@dataclass(frozen=True, slots=True)
class TableComparisonPlan:
    row_pairs: tuple[tuple[int, int], ...]
    column_pairs: tuple[tuple[int, int], ...]
    structural_edits: tuple[SemanticEdit, ...] = ()
    recurse_cells: bool = True


SemanticEdit = (
    InsertSectionEdit
    | DeleteSectionEdit
    | CreateSectionAttachmentEdit
    | DeleteSectionAttachmentEdit
    | CreateFootnoteEdit
    | UpdateParagraphRoleEdit
    | ReplaceParagraphTextEdit
    | AppendListItemsEdit
    | ReplaceListSpecEdit
    | RelevelListItemsEdit
    | UpdateListItemRolesEdit
    | ReplaceParagraphSliceEdit
    | InsertListBlockEdit
    | DeleteListBlockEdit
    | InsertTableBlockEdit
    | DeleteTableBlockEdit
    | InsertPageBreakBlockEdit
    | DeletePageBreakBlockEdit
    | ReplaceNamedRangesEdit
    | InsertTableRowEdit
    | DeleteTableRowEdit
    | InsertTableColumnEdit
    | DeleteTableColumnEdit
    | MergeTableCellsEdit
    | UnmergeTableCellsEdit
    | UpdateTablePinnedHeaderRowsEdit
    | UpdateTableRowStyleEdit
    | UpdateTableColumnPropertiesEdit
    | UpdateTableCellStyleEdit
)


def diff_documents(base: Document, desired: Document) -> list[SemanticEdit]:
    """Return a semantic edit list for the supported ``reconcile_v2`` surface."""
    return diff_document_irs(
        parse_document(base),
        parse_document(desired),
        raw_base_document=base,
    )


def diff_document_irs(
    base: DocumentIR,
    desired: DocumentIR,
    *,
    raw_base_document: Document | None = None,
) -> list[SemanticEdit]:
    """Diff parsed IR values, normalizing away transport carrier paragraphs."""
    base = canonicalize_document_ir(base)
    desired = canonicalize_document_ir(desired)
    desired = _normalize_desired_semantic_ids(base, desired)
    edits: list[SemanticEdit] = []
    desired_tabs = _tabs_by_path(desired.tabs)
    for path, base_tab in _walk_tabs(base.tabs):
        desired_tab = desired_tabs.get(path)
        if desired_tab is None:
            continue
        edits.extend(
            _diff_tab(
                base_tab,
                desired_tab,
                raw_base_document=raw_base_document,
            )
        )
    return edits


def summarize_semantic_edits(edits: Iterable[SemanticEdit]) -> list[str]:
    """Render semantic edits as compact human-readable lines."""
    lines: list[str] = []
    for edit in edits:
        if isinstance(edit, InsertSectionEdit):
            lines.append(
                f"tab {edit.tab_id}: split section {edit.section_index} "
                f"after block {edit.split_after_block_index} and insert section "
                f"with {edit.inserted_block_count} block(s)"
            )
        elif isinstance(edit, DeleteSectionEdit):
            lines.append(
                f"tab {edit.tab_id}: delete section {edit.section_index} "
                f"with {edit.block_count} block(s)"
            )
        elif isinstance(edit, CreateSectionAttachmentEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} create "
                f"{edit.attachment_kind[:-1]} {edit.slot}"
            )
        elif isinstance(edit, DeleteSectionAttachmentEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} delete "
                f"{edit.attachment_kind[:-1]} {edit.slot}"
            )
        elif isinstance(edit, CreateFootnoteEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} block {edit.block_index} "
                "insert footnote"
            )
        elif isinstance(edit, UpdateParagraphRoleEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} block {edit.block_index} "
                f"role {edit.before_role} -> {edit.after_role}"
            )
        elif isinstance(edit, ReplaceParagraphTextEdit):
            lines.append(
                f"tab {edit.tab_id}: story {edit.story_id} paragraph {edit.block_index} "
                "replace text preserving footnote refs"
            )
        elif isinstance(edit, AppendListItemsEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} list {edit.block_index} "
                f"append {len(edit.appended_items)} item(s) to {edit.list_kind}"
            )
        elif isinstance(edit, ReplaceListSpecEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} list {edit.block_index} "
                f"kind {edit.before_kind} -> {edit.after_kind}"
            )
        elif isinstance(edit, RelevelListItemsEdit):
            changed = sum(
                before != after
                for before, after in zip(edit.before_levels, edit.after_levels, strict=True)
            )
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} list {edit.block_index} "
                f"relevel {changed} item(s) in {edit.list_kind}"
            )
        elif isinstance(edit, UpdateListItemRolesEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} list {edit.block_index} "
                f"reset paragraph role on {len(edit.item_indexes)} item(s) in {edit.list_kind}"
            )
        elif isinstance(edit, ReplaceParagraphSliceEdit):
            lines.append(
                f"tab {edit.tab_id}: story {edit.story_id} replace "
                f"{edit.delete_block_count} paragraph block(s) at {edit.start_block_index} "
                f"with {len(edit.inserted_paragraphs)} paragraph(s)"
            )
        elif isinstance(edit, InsertListBlockEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} insert "
                f"{edit.list_kind} list at block {edit.block_index} with {len(edit.items)} item(s)"
            )
        elif isinstance(edit, DeleteListBlockEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} delete list at block {edit.block_index}"
            )
        elif isinstance(edit, InsertTableBlockEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} insert table at block {edit.block_index}"
            )
        elif isinstance(edit, DeleteTableBlockEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} delete table at block {edit.block_index}"
            )
        elif isinstance(edit, InsertPageBreakBlockEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} insert page break at block {edit.block_index}"
            )
        elif isinstance(edit, DeletePageBreakBlockEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} delete page break at block {edit.block_index}"
            )
        elif isinstance(edit, ReplaceNamedRangesEdit):
            lines.append(
                f"tab {edit.tab_id}: named range {edit.name} replace "
                f"{edit.before_count} range(s) with {len(edit.desired_ranges)} range(s)"
            )
        elif isinstance(edit, InsertTableRowEdit):
            suffix = ""
            if any(edit.inserted_cells):
                suffix = (
                    f" with {sum(bool(text) for text in edit.inserted_cells)} populated cell(s)"
                )
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} table {edit.block_index} "
                f"insert row {'below' if edit.insert_below else 'above'} {edit.row_index}{suffix}"
            )
        elif isinstance(edit, DeleteTableRowEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} table {edit.block_index} "
                f"delete row {edit.row_index}"
            )
        elif isinstance(edit, InsertTableColumnEdit):
            suffix = ""
            if any(edit.inserted_cells):
                suffix = (
                    f" with {sum(bool(text) for text in edit.inserted_cells)} populated cell(s)"
                )
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} table {edit.block_index} "
                f"insert column {'right of' if edit.insert_right else 'left of'} {edit.column_index}{suffix}"
            )
        elif isinstance(edit, DeleteTableColumnEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} table {edit.block_index} "
                f"delete column {edit.column_index}"
            )
        elif isinstance(edit, MergeTableCellsEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} table {edit.block_index} "
                f"merge cells r{edit.row_index} c{edit.column_index} "
                f"span {edit.row_span}x{edit.column_span}"
            )
        elif isinstance(edit, UnmergeTableCellsEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} table {edit.block_index} "
                f"unmerge cells r{edit.row_index} c{edit.column_index} "
                f"span {edit.row_span}x{edit.column_span}"
            )
        elif isinstance(edit, UpdateTablePinnedHeaderRowsEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} table {edit.block_index} "
                f"pin header rows {edit.pinned_header_rows}"
            )
        elif isinstance(edit, UpdateTableRowStyleEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} table {edit.block_index} "
                f"update row {edit.row_index} style {','.join(edit.fields)}"
            )
        elif isinstance(edit, UpdateTableColumnPropertiesEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} table {edit.block_index} "
                f"update column {edit.column_index} properties {','.join(edit.fields)}"
            )
        elif isinstance(edit, UpdateTableCellStyleEdit):
            lines.append(
                f"tab {edit.tab_id}: section {edit.section_index} table {edit.block_index} "
                f"update cell r{edit.row_index} c{edit.column_index} style {','.join(edit.fields)}"
            )
    return lines


def _diff_tab(
    base: TabIR,
    desired: TabIR,
    *,
    raw_base_document: Document | None = None,
) -> list[SemanticEdit]:
    base_sections = base.body.sections
    desired_sections = desired.body.sections
    raw_base_sections = (
        _raw_body_sections_from_document(raw_base_document, tab_id=base.id)
        if raw_base_document is not None
        else None
    )
    _ensure_read_only_blocks_unchanged(base_sections, desired_sections)
    edits: list[SemanticEdit] = []
    edits.extend(
        _diff_footnote_changes(
            tab_id=base.id,
            base_sections=base_sections,
            desired_sections=desired_sections,
            base_catalog=base.resource_graph.footnotes,
            desired_catalog=desired.resource_graph.footnotes,
        )
    )
    edits.extend(
        _diff_body_footnote_paragraph_text_changes(
            tab_id=base.id,
            base_sections=base_sections,
            desired_sections=desired_sections,
        )
    )
    edits.extend(
        _diff_section_attachment_changes(
            tab_id=base.id,
            base_sections=base_sections,
            desired_sections=desired_sections,
            base_catalog=base.resource_graph.headers,
            desired_catalog=desired.resource_graph.headers,
            attachment_kind="headers",
        )
    )
    edits.extend(
        _diff_section_attachment_changes(
            tab_id=base.id,
            base_sections=base_sections,
            desired_sections=desired_sections,
            base_catalog=base.resource_graph.footers,
            desired_catalog=desired.resource_graph.footers,
            attachment_kind="footers",
        )
    )
    edits.extend(
        _diff_attached_story_catalog(
            base.id,
            base.body.sections,
            desired.body.sections,
            base.resource_graph.headers,
            desired.resource_graph.headers,
            attachment_kind="headers",
        )
    )
    edits.extend(
        _diff_attached_story_catalog(
            base.id,
            base.body.sections,
            desired.body.sections,
            base.resource_graph.footers,
            desired.resource_graph.footers,
            attachment_kind="footers",
        )
    )
    edits.extend(
        _diff_story_catalog(
            base.id,
            base.resource_graph.footnotes,
            desired.resource_graph.footnotes,
            pair_selector=_select_matching_footnote_story_pairs(
                base_sections,
                desired_sections,
            ),
        )
    )
    table_edits = _diff_section_tables(
        tab_id=base.id,
        base_tab=base,
        desired_tab=desired,
        base_sections=base_sections,
        desired_sections=desired_sections,
    )

    base_flat = _flatten_section_fingerprints(base_sections)
    desired_flat = _flatten_section_fingerprints(desired_sections)
    if base_flat == desired_flat:
        edits = _diff_named_ranges(base, desired, content_edits=edits) + edits
        edits.extend(table_edits)
        edits.extend(
            _diff_section_boundaries(
                tab_id=base.id,
                base_sections=base_sections,
                desired_sections=desired_sections,
            )
        )
        return edits

    block_edits: list[SemanticEdit] = []
    for section_index, (base_section, desired_section) in enumerate(
        zip(base_sections, desired_sections, strict=False)
    ):
        block_edits.extend(
            _diff_section_blocks(
                tab_id=base.id,
                section_index=section_index,
                base_section=base_section,
                desired_section=desired_section,
                raw_base_blocks=(
                    raw_base_sections[section_index]
                    if raw_base_sections is not None and section_index < len(raw_base_sections)
                    else None
                ),
            )
        )
    edits.extend(_filter_conflicting_table_edits(table_edits, block_edits))
    edits.extend(block_edits)
    edits = _diff_named_ranges(base, desired, content_edits=edits) + edits
    return edits


def _filter_conflicting_table_edits(
    table_edits: list[SemanticEdit],
    body_edits: list[SemanticEdit],
) -> list[SemanticEdit]:
    deleted_ranges = _body_deleted_block_ranges(body_edits)
    if not deleted_ranges:
        return table_edits
    filtered: list[SemanticEdit] = []
    for edit in table_edits:
        table_ref = _table_edit_reference(edit)
        if table_ref is None:
            filtered.append(edit)
            continue
        if any(
            table_ref[0] == tab_id
            and table_ref[1] == section_index
            and start <= table_ref[2] <= end
            for tab_id, section_index, start, end in deleted_ranges
        ):
            continue
        filtered.append(edit)
    return filtered


def _body_deleted_block_ranges(
    edits: list[SemanticEdit],
) -> list[tuple[str, int, int, int]]:
    deleted: list[tuple[str, int, int, int]] = []
    for edit in edits:
        if (
            isinstance(edit, ReplaceParagraphSliceEdit)
            and edit.story_id == f"{edit.tab_id}:body"
            and edit.section_index is not None
            and edit.delete_block_count > 0
        ):
            deleted.append(
                (
                    edit.tab_id,
                    edit.section_index,
                    edit.start_block_index,
                    edit.start_block_index + edit.delete_block_count - 1,
                )
            )
            continue
        if isinstance(edit, DeleteListBlockEdit | DeleteTableBlockEdit | DeletePageBreakBlockEdit):
            deleted.append(
                (edit.tab_id, edit.section_index, edit.block_index, edit.block_index)
            )
    return deleted


def _table_edit_reference(edit: SemanticEdit) -> tuple[str, int, int] | None:
    if isinstance(
        edit,
        InsertTableRowEdit
        | DeleteTableRowEdit
        | InsertTableColumnEdit
        | DeleteTableColumnEdit
        | MergeTableCellsEdit
        | UnmergeTableCellsEdit
        | UpdateTablePinnedHeaderRowsEdit
        | UpdateTableRowStyleEdit
        | UpdateTableColumnPropertiesEdit
        | UpdateTableCellStyleEdit,
    ):
        return (edit.tab_id, edit.section_index, edit.block_index)
    if isinstance(edit, ReplaceParagraphSliceEdit):
        prefix = f"{edit.tab_id}:body:table:"
        if not edit.story_id.startswith(prefix):
            return None
        block_part = edit.story_id[len(prefix) :].split(":", 1)[0]
        if not block_part.isdigit():
            return None
        return (
            edit.tab_id,
            0 if edit.section_index is None else edit.section_index,
            int(block_part),
        )
    return None


def _diff_section_attachment_changes(
    *,
    tab_id: str,
    base_sections: list[SectionIR],
    desired_sections: list[SectionIR],
    base_catalog: dict[str, StoryIR],
    desired_catalog: dict[str, StoryIR],
    attachment_kind: str,
) -> list[SemanticEdit]:
    edits: list[SemanticEdit] = []
    base_ref_counts = _attachment_ref_counts(base_sections, attachment_kind)
    for section_index, (base_section, desired_section) in enumerate(
        zip(base_sections, desired_sections, strict=False)
    ):
        base_attachments = getattr(base_section.attachments, attachment_kind)
        desired_attachments = getattr(desired_section.attachments, attachment_kind)
        for slot in sorted(set(base_attachments) | set(desired_attachments)):
            base_ref = base_attachments.get(slot)
            desired_ref = desired_attachments.get(slot)
            if base_ref == desired_ref:
                continue
            if desired_ref is not None:
                desired_story = desired_catalog.get(desired_ref)
                if desired_story is None:
                    continue
                if base_ref is not None:
                    base_story = base_catalog.get(base_ref)
                    if base_story is not None and _story_signature(base_story) == _story_signature(
                        desired_story
                    ):
                        continue
                if base_ref is not None and base_ref_counts.get(base_ref, 0) == 1:
                    # Unique attachments can be updated in place by story-content diff.
                    continue
                edits.append(
                    CreateSectionAttachmentEdit(
                        tab_id=tab_id,
                        section_index=section_index,
                        attachment_kind=attachment_kind,
                        slot=slot,
                        desired_story=desired_story,
                    )
                )
                continue
            if base_ref is not None:
                if base_ref_counts.get(base_ref, 0) > 1:
                    raise UnsupportedSpikeError(
                        "reconcile_v2 does not yet support deleting a shared "
                        f"{attachment_kind[:-1]} attachment from only one section"
                    )
                edits.append(
                    DeleteSectionAttachmentEdit(
                        tab_id=tab_id,
                        section_index=section_index,
                        attachment_kind=attachment_kind,
                        slot=slot,
                        story_id=base_ref,
                    )
                )
    return edits


def _ensure_read_only_blocks_unchanged(
    base_sections: list[SectionIR],
    desired_sections: list[SectionIR],
) -> None:
    max_sections = max(len(base_sections), len(desired_sections))
    for section_index in range(max_sections):
        base_blocks = (
            base_sections[section_index].blocks if section_index < len(base_sections) else []
        )
        desired_blocks = (
            desired_sections[section_index].blocks
            if section_index < len(desired_sections)
            else []
        )
        base_read_only = [
            _read_only_block_signature(block)
            for block in base_blocks
            if _is_read_only_block(block)
        ]
        desired_read_only = [
            _read_only_block_signature(block)
            for block in desired_blocks
            if _is_read_only_block(block)
        ]
        if base_read_only != desired_read_only:
            raise UnsupportedSpikeError(
                "reconcile_v2 does not support editing read-only or opaque body blocks "
                f"in section {section_index}"
            )


def _is_read_only_block(block: BlockIR | None) -> bool:
    return isinstance(block, TocIR | OpaqueBlockIR) or (
        isinstance(block, ParagraphIR) and _is_read_only_paragraph(block)
    )


def _read_only_block_positions(blocks: list[BlockIR]) -> list[tuple[int, BlockIR]]:
    return [
        (index, block)
        for index, block in enumerate(blocks)
        if _is_read_only_block(block)
    ]


def _read_only_block_signature(block: BlockIR) -> tuple[object, ...]:
    if isinstance(block, TocIR):
        return ("toc",)
    if isinstance(block, OpaqueBlockIR):
        return ("opaque", block.kind, tuple(sorted(block.payload.items())))
    if isinstance(block, ParagraphIR) and _is_read_only_paragraph(block):
        return (
            "paragraph-opaque",
            tuple(
                (
                    inline.kind,
                    tuple(sorted(inline.payload.items())),
                )
                for inline in block.inlines
                if isinstance(inline, OpaqueInlineIR)
            ),
        )
    raise TypeError(f"Unsupported read-only block: {type(block).__name__}")


def _editable_block_count(blocks: list[BlockIR]) -> int:
    return sum(not _is_read_only_block(block) for block in blocks)


def _tabs_by_path(tabs: list[TabIR]) -> dict[tuple[int, ...], TabIR]:
    return dict(_walk_tabs(tabs))


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


def _diff_section_boundaries(
    *,
    tab_id: str,
    base_sections: list[SectionIR],
    desired_sections: list[SectionIR],
) -> list[SemanticEdit]:
    edits: list[SemanticEdit] = []
    base_boundaries = set(_section_boundaries(base_sections))
    desired_boundaries = set(_section_boundaries(desired_sections))
    desired_counts = _section_prefix_counts(desired_sections)
    base_counts = _section_prefix_counts(base_sections)

    for section_index, boundary in enumerate(desired_counts[:-1], start=1):
        if boundary not in base_boundaries:
            split_section_index, split_after_block_index = _locate_split_anchor(
                base_sections,
                boundary,
            )
            edits.append(
                InsertSectionEdit(
                    tab_id=tab_id,
                    section_index=split_section_index,
                    split_after_block_index=split_after_block_index,
                    inserted_block_count=len(desired_sections[section_index].blocks),
                )
            )
    for section_index, boundary in enumerate(base_counts[:-1], start=1):
        if boundary not in desired_boundaries:
            edits.append(
                DeleteSectionEdit(
                    tab_id=tab_id,
                    section_index=section_index,
                    block_count=len(base_sections[section_index].blocks),
                )
            )
    return edits


def _diff_section_blocks(
    *,
    tab_id: str,
    section_index: int,
    base_section: SectionIR,
    desired_section: SectionIR,
    raw_base_blocks: list[dict[str, object]] | None = None,
) -> list[SemanticEdit]:
    base_anchors = _anchor_block_positions(base_section.blocks)
    desired_anchors = _anchor_block_positions(desired_section.blocks)
    if not base_anchors and not desired_anchors:
        return _diff_editable_block_span(
            tab_id=tab_id,
            section_index=section_index,
            base_blocks=base_section.blocks,
            desired_blocks=desired_section.blocks,
            block_offset=0,
            raw_block_offset=(
                None
                if raw_base_blocks is None
                else _canonical_to_raw_body_block_index(raw_base_blocks, 0)
            ),
        )
    if [_anchor_block_signature(block) for _, block in base_anchors] != [
        _anchor_block_signature(block) for _, block in desired_anchors
    ]:
        return _diff_editable_block_span(
            tab_id=tab_id,
            section_index=section_index,
            base_blocks=base_section.blocks,
            desired_blocks=desired_section.blocks,
            block_offset=0,
            raw_block_offset=(
                None
                if raw_base_blocks is None
                else _canonical_to_raw_body_block_index(raw_base_blocks, 0)
            ),
        )

    spans: list[tuple[list[BlockIR], list[BlockIR], int, int | None]] = []
    base_start = 0
    desired_start = 0
    editable_offset = 0
    for (base_index, _base_block), (desired_index, _desired_block) in zip(
        base_anchors,
        desired_anchors,
        strict=True,
    ):
        spans.append(
            (
                base_section.blocks[base_start:base_index],
                desired_section.blocks[desired_start:desired_index],
                editable_offset,
                (
                    None
                    if raw_base_blocks is None
                    else _canonical_to_raw_body_block_index(raw_base_blocks, base_start)
                ),
            )
        )
        editable_offset += _editable_block_count(base_section.blocks[base_start:base_index])
        base_start = base_index + 1
        desired_start = desired_index + 1
    spans.append(
        (
            base_section.blocks[base_start:],
            desired_section.blocks[desired_start:],
            editable_offset,
            (
                None
                if raw_base_blocks is None
                else _canonical_to_raw_body_block_index(raw_base_blocks, base_start)
            ),
        )
    )
    edits: list[SemanticEdit] = []
    for base_span, desired_span, block_offset, raw_block_offset in reversed(spans):
        edits.extend(
            _diff_editable_block_span(
                tab_id=tab_id,
                section_index=section_index,
                base_blocks=base_span,
                desired_blocks=desired_span,
                block_offset=block_offset,
                raw_block_offset=raw_block_offset,
            )
        )
    return edits


def _anchor_block_positions(blocks: list[BlockIR]) -> list[tuple[int, BlockIR]]:
    return [
        (index, block)
        for index, block in enumerate(blocks)
        if _is_anchor_block(block)
    ]


def _is_anchor_block(block: BlockIR | None) -> bool:
    return _is_read_only_block(block) or isinstance(block, PageBreakIR | TableIR)


def _anchor_block_signature(block: BlockIR) -> tuple[object, ...]:
    if isinstance(block, PageBreakIR):
        return ("pagebreak",)
    if isinstance(block, TableIR):
        return _table_anchor_signature(block)
    return _read_only_block_signature(block)


def _table_anchor_signature(table: TableIR) -> tuple[object, ...]:
    return (
        "table",
        len(table.rows),
        tuple(len(row.cells) for row in table.rows),
        tuple(
            tuple((cell.row_span, cell.column_span) for cell in row.cells)
            for row in table.rows
        ),
        table.pinned_header_rows,
    )


def _raw_body_sections_from_document(
    document: Document | None,
    *,
    tab_id: str,
) -> list[list[dict[str, object]]]:
    if document is None:
        return []
    raw_tab = next(
        (
            tab
            for tab in document.model_dump(by_alias=True, exclude_none=True).get("tabs", [])
            if tab.get("tabProperties", {}).get("tabId") == tab_id
        ),
        None,
    )
    if raw_tab is None:
        raise ValueError(f"Unknown tab id {tab_id}")
    sections: list[list[dict[str, object]]] = [[]]
    for element in raw_tab.get("documentTab", {}).get("body", {}).get("content", []):
        if "sectionBreak" in element:
            if sections[-1]:
                sections.append([])
            continue
        start_index = int(element.get("startIndex", 0))
        end_index = int(element.get("endIndex", start_index))
        if "paragraph" in element:
            if any(
                child.get("pageBreak") is not None
                for child in element["paragraph"].get("elements", [])
            ):
                sections[-1].append(
                    {"kind": "pagebreak", "start": start_index, "end": end_index}
                )
                continue
            text = "".join(
                run.get("textRun", {}).get("content", "")
                for run in element["paragraph"].get("elements", [])
            )
            sections[-1].append(
                {
                    "kind": "paragraph",
                    "start": start_index,
                    "end": end_index,
                    "text_start": start_index,
                    "text_end": end_index - 1,
                    "text": text.removesuffix("\n"),
                }
            )
        elif "table" in element:
            sections[-1].append({"kind": "table", "start": start_index, "end": end_index})
        elif "tableOfContents" in element:
            sections[-1].append({"kind": "toc", "start": start_index, "end": end_index})
        else:
            sections[-1].append({"kind": "opaque", "start": start_index, "end": end_index})
    return sections


def _canonical_to_raw_body_block_index(
    raw_blocks: list[dict[str, object]],
    block_index: int,
) -> int:
    keep_mask = _raw_transport_block_keep_mask(raw_blocks)
    kept_indices = [index for index, keep in enumerate(keep_mask) if keep]
    if not kept_indices:
        return 0
    if block_index < len(kept_indices):
        return kept_indices[block_index]
    return len(raw_blocks)


def _raw_transport_block_keep_mask(
    raw_blocks: list[dict[str, object]],
) -> list[bool]:
    keep_mask = [True] * len(raw_blocks)
    for index, block in enumerate(raw_blocks):
        if not _is_raw_transport_carrier_paragraph(block):
            continue
        prev_is_structural = index > 0 and _is_raw_transport_carrier_anchor(raw_blocks[index - 1])
        next_is_structural = (
            index + 1 < len(raw_blocks) and _is_raw_transport_carrier_anchor(raw_blocks[index + 1])
        )
        if prev_is_structural or next_is_structural:
            keep_mask[index] = False
    run_start = 0
    while run_start < len(raw_blocks):
        if not _is_raw_transport_carrier_paragraph(raw_blocks[run_start]):
            run_start += 1
            continue
        run_end = run_start
        while run_end + 1 < len(raw_blocks) and _is_raw_transport_carrier_paragraph(
            raw_blocks[run_end + 1]
        ):
            run_end += 1
        prev_is_structural = run_start > 0 and _is_raw_transport_carrier_anchor(
            raw_blocks[run_start - 1]
        )
        next_is_structural = run_end + 1 < len(raw_blocks) and _is_raw_transport_carrier_anchor(
            raw_blocks[run_end + 1]
        )
        if prev_is_structural or next_is_structural:
            for index in range(run_start, run_end + 1):
                keep_mask[index] = False
        run_start = run_end + 1
    saw_noncarrier = any(
        not _is_raw_transport_carrier_paragraph(block) for block in raw_blocks
    )
    if saw_noncarrier:
        for index, block in enumerate(raw_blocks):
            if not keep_mask[index] or not _is_raw_transport_carrier_paragraph(block):
                break
            keep_mask[index] = False
    for index in range(len(raw_blocks) - 1, -1, -1):
        if not keep_mask[index] or not _is_raw_transport_carrier_paragraph(raw_blocks[index]):
            break
        keep_mask[index] = False
    return keep_mask


def _is_raw_transport_carrier_paragraph(block: dict[str, object]) -> bool:
    return block["kind"] == "paragraph" and block.get("text") == ""


def _is_raw_transport_carrier_anchor(block: dict[str, object]) -> bool:
    return block["kind"] in {"table", "pagebreak", "page_break"}


def _diff_editable_block_span(
    *,
    tab_id: str,
    section_index: int,
    base_blocks: list[BlockIR],
    desired_blocks: list[BlockIR],
    block_offset: int,
    raw_block_offset: int | None,
) -> list[SemanticEdit]:
    edits: list[SemanticEdit] = []
    paragraph_slice = _diff_story_paragraph_slice(
        tab_id=tab_id,
        story_id=f"{tab_id}:body",
        section_index=section_index,
        base_blocks=base_blocks,
        desired_blocks=desired_blocks,
        block_offset=block_offset,
        raw_block_offset=raw_block_offset,
    )
    if paragraph_slice is not None:
        edits.append(paragraph_slice)
        return edits

    block_slice = _diff_section_block_slice(
        tab_id=tab_id,
        section_index=section_index,
        base_blocks=base_blocks,
        desired_blocks=desired_blocks,
        block_offset=block_offset,
        raw_block_offset=raw_block_offset,
    )
    if block_slice:
        edits.extend(block_slice)
        return edits

    for block_index, (base_block, desired_block) in enumerate(
        zip(base_blocks, desired_blocks, strict=False)
    ):
        if isinstance(base_block, ParagraphIR) and isinstance(desired_block, ParagraphIR):
            if (
                _paragraph_text(base_block) == _paragraph_text(desired_block)
                and base_block.role != desired_block.role
            ):
                edits.append(
                    UpdateParagraphRoleEdit(
                        tab_id=tab_id,
                        section_index=section_index,
                        block_index=block_offset + block_index,
                        before_role=base_block.role,
                        after_role=desired_block.role,
                    )
                )
        elif isinstance(base_block, ListIR) and isinstance(desired_block, ListIR):
            if base_block.spec.kind != desired_block.spec.kind:
                edits.append(
                    ReplaceListSpecEdit(
                        tab_id=tab_id,
                        section_index=section_index,
                        block_index=block_offset + block_index,
                        before_kind=base_block.spec.kind,
                        after_kind=desired_block.spec.kind,
                    )
                )
                continue
            base_items = [_paragraph_text(item.paragraph) for item in base_block.items]
            desired_items = [
                _paragraph_text(item.paragraph) for item in desired_block.items
            ]
            if (
                len(desired_items) > len(base_items)
                and desired_items[: len(base_items)] == base_items
            ):
                edits.append(
                    AppendListItemsEdit(
                        tab_id=tab_id,
                        section_index=section_index,
                        block_index=block_offset + block_index,
                        list_kind=desired_block.spec.kind,
                        appended_items=tuple(
                            ListItemFragment(
                                level=item.level,
                                text=_paragraph_text(item.paragraph),
                            )
                            for item in desired_block.items[len(base_items) :]
                        ),
                    )
                )
                continue
            base_levels = tuple(item.level for item in base_block.items)
            desired_levels = tuple(item.level for item in desired_block.items)
            if base_items == desired_items and base_levels != desired_levels:
                edits.append(
                    RelevelListItemsEdit(
                        tab_id=tab_id,
                        section_index=section_index,
                        block_index=block_offset + block_index,
                        list_kind=desired_block.spec.kind,
                        before_levels=base_levels,
                        after_levels=desired_levels,
                    )
                )
            base_roles = tuple(item.paragraph.role for item in base_block.items)
            desired_roles = tuple(item.paragraph.role for item in desired_block.items)
            if (
                len(base_roles) == len(desired_roles)
                and base_roles != desired_roles
                and base_items == desired_items
            ):
                changed_indexes = tuple(
                    index
                    for index, (before_role, after_role) in enumerate(
                        zip(base_roles, desired_roles, strict=True)
                    )
                    if before_role != after_role
                )
                edits.append(
                    UpdateListItemRolesEdit(
                        tab_id=tab_id,
                        section_index=section_index,
                        block_index=block_offset + block_index,
                        list_kind=desired_block.spec.kind,
                        item_indexes=changed_indexes,
                        before_roles=tuple(base_roles[index] for index in changed_indexes),
                        after_roles=tuple(
                            desired_roles[index] for index in changed_indexes
                        ),
                    )
                )
    return edits


def _diff_section_block_slice(
    *,
    tab_id: str,
    section_index: int,
    base_blocks: list[BlockIR],
    desired_blocks: list[BlockIR],
    block_offset: int,
    raw_block_offset: int | None,
) -> list[SemanticEdit]:
    base_fingerprints = _block_fingerprints(base_blocks)
    desired_fingerprints = _block_fingerprints(desired_blocks)
    if base_fingerprints == desired_fingerprints:
        return []

    prefix = 0
    while (
        prefix < len(base_fingerprints)
        and prefix < len(desired_fingerprints)
        and base_fingerprints[prefix] == desired_fingerprints[prefix]
    ):
        prefix += 1

    suffix = 0
    while (
        suffix < len(base_fingerprints) - prefix
        and suffix < len(desired_fingerprints) - prefix
        and base_fingerprints[-(suffix + 1)] == desired_fingerprints[-(suffix + 1)]
    ):
        suffix += 1

    delete_stop = len(base_blocks) - suffix
    insert_stop = len(desired_blocks) - suffix
    base_slice = _normalize_structural_block_slice(base_blocks[prefix:delete_stop])
    desired_slice = _normalize_structural_block_slice(desired_blocks[prefix:insert_stop])
    edge_edits: list[SemanticEdit] = []
    if any(
        isinstance(block, PageBreakIR)
        for block in (*base_slice, *desired_slice)
    ):
        leading_pairs = 0
        while leading_pairs < min(len(base_slice), len(desired_slice)):
            pair_edits = _diff_compatible_edge_pair(
                tab_id=tab_id,
                section_index=section_index,
                block_index=block_offset + prefix + leading_pairs,
                base_block=base_slice[leading_pairs],
                desired_block=desired_slice[leading_pairs],
            )
            if pair_edits is None:
                break
            edge_edits.extend(pair_edits)
            leading_pairs += 1

        trailing_pairs = 0
        while trailing_pairs < min(
            len(base_slice) - leading_pairs,
            len(desired_slice) - leading_pairs,
        ):
            base_index = len(base_slice) - 1 - trailing_pairs
            desired_index = len(desired_slice) - 1 - trailing_pairs
            pair_edits = _diff_compatible_edge_pair(
                tab_id=tab_id,
                section_index=section_index,
                block_index=block_offset + prefix + base_index,
                base_block=base_slice[base_index],
                desired_block=desired_slice[desired_index],
            )
            if pair_edits is None:
                break
            edge_edits.extend(pair_edits)
            trailing_pairs += 1

        if leading_pairs or trailing_pairs:
            base_slice = base_slice[leading_pairs : len(base_slice) - trailing_pairs]
            desired_slice = desired_slice[leading_pairs : len(desired_slice) - trailing_pairs]
            prefix += leading_pairs
            delete_stop -= trailing_pairs
            insert_stop -= trailing_pairs
            if not base_slice and not desired_slice:
                return edge_edits

    if _all_paragraphs(base_slice) and _all_paragraphs(desired_slice):
        if (
            len(base_slice) == len(desired_slice)
            and [_paragraph_signature(block) for block in base_slice]
            == [_paragraph_signature(block) for block in desired_slice]
        ):
            return []
        if (
            len(base_slice) == len(desired_slice)
            and [_paragraph_text(block) for block in base_slice]
            == [_paragraph_text(block) for block in desired_slice]
        ):
            return []
        return [
            ReplaceParagraphSliceEdit(
                tab_id=tab_id,
                story_id=f"{tab_id}:body",
                section_index=section_index,
                start_block_index=block_offset + prefix,
                delete_block_count=max(0, delete_stop - prefix),
                inserted_paragraphs=tuple(
                    ParagraphFragment(paragraph=block) for block in desired_slice
                ),
                body_anchor_block_index=(
                    raw_block_offset + prefix if raw_block_offset is not None else None
                ),
            )
        ]

    if (
        len(base_slice) == len(desired_slice) == 1
        and (
            (isinstance(base_slice[0], ListIR) and isinstance(desired_slice[0], ListIR))
            or (isinstance(base_slice[0], TableIR) and isinstance(desired_slice[0], TableIR))
        )
    ):
        return edge_edits

    return edge_edits + _plan_mixed_body_block_slice(
        tab_id=tab_id,
        section_index=section_index,
        block_index=block_offset + prefix,
        raw_block_index=(
            raw_block_offset + prefix if raw_block_offset is not None else None
        ),
        base_slice=base_slice,
        desired_slice=desired_slice,
    )


def _diff_compatible_edge_pair(
    *,
    tab_id: str,
    section_index: int,
    block_index: int,
    base_block: BlockIR,
    desired_block: BlockIR,
) -> list[SemanticEdit] | None:
    if isinstance(base_block, PageBreakIR) and isinstance(desired_block, PageBreakIR):
        return []
    if not isinstance(base_block, ParagraphIR) or not isinstance(desired_block, ParagraphIR):
        return None
    if _non_text_inline_signature(base_block) != _non_text_inline_signature(desired_block):
        return None
    if _paragraphs_share_trailing_single_footnote_ref(base_block, desired_block):
        return []
    edits: list[SemanticEdit] = []
    if base_block.role != desired_block.role:
        edits.append(
            UpdateParagraphRoleEdit(
                tab_id=tab_id,
                section_index=section_index,
                block_index=block_index,
                before_role=base_block.role,
                after_role=desired_block.role,
            )
        )
    if _paragraph_text(base_block) != _paragraph_text(desired_block):
        edits.append(
            ReplaceParagraphTextEdit(
                tab_id=tab_id,
                story_id=f"{tab_id}:body",
                section_index=section_index,
                block_index=block_index,
                desired_paragraph=desired_block,
            )
        )
    return edits


def _normalize_structural_block_slice(blocks: list[BlockIR]) -> list[BlockIR]:
    normalized: list[BlockIR] = []
    for block in blocks:
        if _is_empty_paragraph_block(block) and normalized and isinstance(normalized[-1], TableIR):
            continue
        normalized.append(block)
    return normalized


def _plan_mixed_body_block_slice(
    *,
    tab_id: str,
    section_index: int,
    block_index: int,
    raw_block_index: int,
    base_slice: list[BlockIR],
    desired_slice: list[BlockIR],
) -> list[SemanticEdit]:
    edits: list[SemanticEdit] = []
    edits.extend(
        _delete_body_block_sequence(
            tab_id=tab_id,
            section_index=section_index,
            start_block_index=block_index,
            raw_start_block_index=raw_block_index,
            blocks=base_slice,
        )
    )
    edits.extend(
        _insert_body_block_sequence(
            tab_id=tab_id,
            section_index=section_index,
            block_index=block_index,
            raw_block_index=raw_block_index,
            blocks=desired_slice,
        )
    )
    return edits


def _delete_body_block_sequence(
    *,
    tab_id: str,
    section_index: int,
    start_block_index: int,
    raw_start_block_index: int | None,
    blocks: list[BlockIR],
) -> list[SemanticEdit]:
    edits: list[SemanticEdit] = []
    index = len(blocks) - 1
    while index >= 0:
        block = blocks[index]
        if isinstance(block, ParagraphIR):
            start = index
            while start > 0 and isinstance(blocks[start - 1], ParagraphIR):
                start -= 1
            edits.append(
                ReplaceParagraphSliceEdit(
                    tab_id=tab_id,
                    story_id=f"{tab_id}:body",
                    section_index=section_index,
                    start_block_index=start_block_index + start,
                    delete_block_count=index - start + 1,
                    inserted_paragraphs=(),
                    body_anchor_block_index=(
                        None
                        if raw_start_block_index is None
                        else raw_start_block_index + start
                    ),
                )
            )
            index = start - 1
            continue
        if isinstance(block, ListIR):
            edits.append(
                DeleteListBlockEdit(
                    tab_id=tab_id,
                    section_index=section_index,
                    block_index=start_block_index + index,
                    body_anchor_block_index=(
                        None
                        if raw_start_block_index is None
                        else raw_start_block_index + index
                    ),
                )
            )
        elif isinstance(block, TableIR):
            edits.append(
                DeleteTableBlockEdit(
                    tab_id=tab_id,
                    section_index=section_index,
                    block_index=start_block_index + index,
                    body_anchor_block_index=(
                        None
                        if raw_start_block_index is None
                        else raw_start_block_index + index
                    ),
                )
            )
        elif isinstance(block, PageBreakIR):
            edits.append(
                DeletePageBreakBlockEdit(
                    tab_id=tab_id,
                    section_index=section_index,
                    block_index=start_block_index + index,
                    body_anchor_block_index=(
                        None
                        if raw_start_block_index is None
                        else raw_start_block_index + index
                    ),
                )
            )
        index -= 1
    return edits


def _insert_body_block_sequence(
    *,
    tab_id: str,
    section_index: int,
    block_index: int,
    raw_block_index: int | None,
    blocks: list[BlockIR],
) -> list[SemanticEdit]:
    edits: list[SemanticEdit] = []
    index = len(blocks) - 1
    while index >= 0:
        block = blocks[index]
        if isinstance(block, ParagraphIR):
            start = index
            while start > 0 and isinstance(blocks[start - 1], ParagraphIR):
                start -= 1
            edits.append(
                ReplaceParagraphSliceEdit(
                    tab_id=tab_id,
                    story_id=f"{tab_id}:body",
                    section_index=section_index,
                    start_block_index=block_index,
                    delete_block_count=0,
                    inserted_paragraphs=tuple(
                        ParagraphFragment(paragraph=paragraph)
                        for paragraph in blocks[start : index + 1]
                    ),
                    body_anchor_block_index=raw_block_index,
                )
            )
            index = start - 1
            continue
        if isinstance(block, ListIR):
            edits.append(
                InsertListBlockEdit(
                    tab_id=tab_id,
                    section_index=section_index,
                    block_index=block_index,
                    list_kind=block.spec.kind,
                    items=tuple(
                        ListItemFragment(
                            level=item.level,
                            text=_paragraph_text(item.paragraph),
                        )
                    for item in block.items
                    ),
                    body_anchor_block_index=raw_block_index,
                )
            )
        elif isinstance(block, TableIR):
            edits.append(
                InsertTableBlockEdit(
                    tab_id=tab_id,
                    section_index=section_index,
                    block_index=block_index,
                    table=block,
                    body_anchor_block_index=raw_block_index,
                )
            )
        elif isinstance(block, PageBreakIR):
            edits.append(
                InsertPageBreakBlockEdit(
                    tab_id=tab_id,
                    section_index=section_index,
                    block_index=block_index,
                    body_anchor_block_index=raw_block_index,
                )
            )
        index -= 1
    return edits


def _diff_footnote_changes(
    *,
    tab_id: str,
    base_sections: list[SectionIR],
    desired_sections: list[SectionIR],
    base_catalog: dict[str, StoryIR],
    desired_catalog: dict[str, StoryIR],
) -> list[SemanticEdit]:
    _ = base_catalog
    edits: list[SemanticEdit] = []
    matched_desired_refs = {
        desired_ref
        for _base_ref, desired_ref in _select_matching_footnote_story_pairs(
            base_sections,
            desired_sections,
        )
    }
    max_sections = max(len(base_sections), len(desired_sections))
    for section_index in range(max_sections):
        base_blocks = (
            base_sections[section_index].blocks if section_index < len(base_sections) else []
        )
        desired_blocks = (
            desired_sections[section_index].blocks
            if section_index < len(desired_sections)
            else []
        )
        max_blocks = max(len(base_blocks), len(desired_blocks))
        for block_index in range(max_blocks):
            base_block = base_blocks[block_index] if block_index < len(base_blocks) else None
            desired_block = desired_blocks[block_index] if block_index < len(desired_blocks) else None
            if not isinstance(desired_block, ParagraphIR):
                continue
            desired_refs = [
                inline.ref for inline in desired_block.inlines if isinstance(inline, FootnoteRefIR)
            ]
            if not desired_refs:
                continue
            if len(desired_refs) != 1:
                raise UnsupportedSpikeError(
                    "reconcile_v2 currently supports only one footnote reference "
                    "per paragraph"
                )
            desired_story = desired_catalog.get(desired_refs[0])
            if desired_story is None:
                continue

            base_refs: list[str] = []
            if isinstance(base_block, ParagraphIR):
                base_refs = [
                    inline.ref for inline in base_block.inlines if isinstance(inline, FootnoteRefIR)
                ]
            if len(base_refs) == 0:
                if desired_refs[0] in matched_desired_refs:
                    continue
                edits.append(
                    CreateFootnoteEdit(
                        tab_id=tab_id,
                        section_index=section_index,
                        block_index=block_index,
                        text_offset_utf16=_footnote_insertion_offset(desired_block),
                        desired_story=desired_story,
                    )
                )
                continue
            if len(base_refs) != 1:
                raise UnsupportedSpikeError(
                    "reconcile_v2 currently supports only simple footnote creation "
                    "or matched-story content edits"
                )
    return edits


def _diff_body_footnote_paragraph_text_changes(
    *,
    tab_id: str,
    base_sections: list[SectionIR],
    desired_sections: list[SectionIR],
) -> list[SemanticEdit]:
    edits: list[SemanticEdit] = []
    for section_index, (base_section, desired_section) in enumerate(
        zip(base_sections, desired_sections, strict=False)
    ):
        for block_index, (base_block, desired_block) in enumerate(
            zip(base_section.blocks, desired_section.blocks, strict=False)
        ):
            if not isinstance(base_block, ParagraphIR) or not isinstance(desired_block, ParagraphIR):
                continue
            if not _paragraphs_share_trailing_single_footnote_ref(base_block, desired_block):
                continue
            if base_block.role != desired_block.role:
                edits.append(
                    UpdateParagraphRoleEdit(
                        tab_id=tab_id,
                        section_index=section_index,
                        block_index=block_index,
                        before_role=base_block.role,
                        after_role=desired_block.role,
                    )
                )
            if _paragraph_text(base_block) != _paragraph_text(desired_block):
                edits.append(
                    ReplaceParagraphTextEdit(
                        tab_id=tab_id,
                        story_id=f"{tab_id}:body",
                        section_index=section_index,
                        block_index=block_index,
                        desired_paragraph=desired_block,
                    )
                )
    return edits


def _select_matching_footnote_story_pairs(
    base_sections: list[SectionIR],
    desired_sections: list[SectionIR],
) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for base_section, desired_section in zip(base_sections, desired_sections, strict=False):
        for base_block, desired_block in zip(base_section.blocks, desired_section.blocks, strict=False):
            if not isinstance(base_block, ParagraphIR) or not isinstance(desired_block, ParagraphIR):
                continue
            base_refs = [inline.ref for inline in base_block.inlines if isinstance(inline, FootnoteRefIR)]
            desired_refs = [
                inline.ref for inline in desired_block.inlines if isinstance(inline, FootnoteRefIR)
            ]
            if len(base_refs) != 1 or len(desired_refs) != 1:
                continue
            pairs.extend(zip(base_refs, desired_refs, strict=True))
    return tuple(pairs)


def _normalize_desired_semantic_ids(base: DocumentIR, desired: DocumentIR) -> DocumentIR:
    normalized = copy.deepcopy(desired)
    desired_tabs = _tabs_by_path(normalized.tabs)
    for path, base_tab in _walk_tabs(base.tabs):
        desired_tab = desired_tabs.get(path)
        if desired_tab is None:
            continue
        _normalize_tab_footnote_ids(base_tab, desired_tab)
    return normalized


def _normalize_tab_footnote_ids(base_tab: TabIR, desired_tab: TabIR) -> None:
    ref_map: dict[str, str] = {}
    for base_ref, desired_ref in _select_matching_footnote_story_pairs(
        base_tab.body.sections,
        desired_tab.body.sections,
    ):
        if base_ref != desired_ref:
            ref_map[desired_ref] = base_ref
    if not ref_map:
        return
    _remap_footnote_refs_in_sections(desired_tab.body.sections, ref_map)
    for story in desired_tab.resource_graph.headers.values():
        _remap_footnote_refs_in_story(story, ref_map)
    for story in desired_tab.resource_graph.footers.values():
        _remap_footnote_refs_in_story(story, ref_map)
    remapped_footnotes: dict[str, StoryIR] = {}
    for story_ref, story in desired_tab.resource_graph.footnotes.items():
        target_ref = ref_map.get(story_ref, story_ref)
        if target_ref != story_ref:
            story.id = f"{desired_tab.id}:footnote:{target_ref}"
        _remap_footnote_refs_in_story(story, ref_map)
        remapped_footnotes[target_ref] = story
    desired_tab.resource_graph.footnotes = remapped_footnotes


def _remap_footnote_refs_in_sections(
    sections: list[SectionIR],
    ref_map: dict[str, str],
) -> None:
    for section in sections:
        for block in section.blocks:
            _remap_footnote_refs_in_block(block, ref_map)


def _remap_footnote_refs_in_story(story: StoryIR, ref_map: dict[str, str]) -> None:
    for block in story.blocks:
        _remap_footnote_refs_in_block(block, ref_map)


def _remap_footnote_refs_in_block(block: BlockIR, ref_map: dict[str, str]) -> None:
    if isinstance(block, ParagraphIR):
        for inline in block.inlines:
            if isinstance(inline, FootnoteRefIR):
                inline.ref = ref_map.get(inline.ref, inline.ref)
        return
    if isinstance(block, ListIR):
        for item in block.items:
            _remap_footnote_refs_in_block(item.paragraph, ref_map)
        return
    if isinstance(block, TableIR):
        for row in block.rows:
            for cell in row.cells:
                _remap_footnote_refs_in_story(cell.content, ref_map)


def _diff_attached_story_catalog(
    tab_id: str,
    base_sections: list[SectionIR],
    desired_sections: list[SectionIR],
    base_catalog: dict[str, StoryIR],
    desired_catalog: dict[str, StoryIR],
    *,
    attachment_kind: str,
) -> list[SemanticEdit]:
    edits: list[SemanticEdit] = []
    seen_pairs: set[tuple[str, str]] = set()
    for base_section, desired_section in zip(base_sections, desired_sections, strict=False):
        base_attachments = getattr(base_section.attachments, attachment_kind)
        desired_attachments = getattr(desired_section.attachments, attachment_kind)
        for slot in sorted(set(base_attachments) & set(desired_attachments)):
            base_ref = base_attachments[slot]
            desired_ref = desired_attachments[slot]
            base_story = base_catalog.get(base_ref)
            desired_story = desired_catalog.get(desired_ref)
            if base_story is None or desired_story is None:
                continue
            if base_ref != desired_ref and (
                _story_signature(base_story) != _story_signature(desired_story)
                and _attachment_ref_counts(base_sections, attachment_kind).get(base_ref, 0) > 1
            ):
                continue
            story_pair = (base_ref, desired_ref)
            if story_pair in seen_pairs:
                continue
            seen_pairs.add(story_pair)
            edit = _diff_story_paragraph_slice(
                tab_id=tab_id,
                story_id=base_story.id,
                section_index=None,
                base_blocks=base_story.blocks,
                desired_blocks=desired_story.blocks,
            )
            if edit is not None:
                edits.append(edit)
    return edits


def _diff_story_catalog(
    tab_id: str,
    base_catalog: dict[str, StoryIR],
    desired_catalog: dict[str, StoryIR],
    *,
    pair_selector: tuple[tuple[str, str], ...] | None = None,
) -> list[SemanticEdit]:
    edits: list[SemanticEdit] = []
    pairs = (
        pair_selector
        if pair_selector is not None
        else tuple((story_ref, story_ref) for story_ref in sorted(set(base_catalog) & set(desired_catalog)))
    )
    for base_story_ref, desired_story_ref in pairs:
        if base_story_ref not in base_catalog or desired_story_ref not in desired_catalog:
            continue
        edit = _diff_story_paragraph_slice(
            tab_id=tab_id,
            story_id=base_catalog[base_story_ref].id,
            section_index=None,
            base_blocks=base_catalog[base_story_ref].blocks,
            desired_blocks=desired_catalog[desired_story_ref].blocks,
        )
        if edit is not None:
            edits.append(edit)
    return edits


def _diff_section_tables(
    *,
    tab_id: str,
    base_tab: TabIR,
    desired_tab: TabIR,
    base_sections: list[SectionIR],
    desired_sections: list[SectionIR],
) -> list[SemanticEdit]:
    edits: list[SemanticEdit] = []
    for section_index, (base_section, desired_section) in enumerate(
        zip(base_sections, desired_sections, strict=False)
    ):
        base_table_positions = [
            index
            for index, block in enumerate(base_section.blocks)
            if isinstance(block, TableIR)
        ]
        desired_table_positions = [
            index
            for index, block in enumerate(desired_section.blocks)
            if isinstance(block, TableIR)
        ]
        for base_block_index, desired_block_index in zip(
            base_table_positions,
            desired_table_positions,
            strict=False,
        ):
            base_block = base_section.blocks[base_block_index]
            desired_block = desired_section.blocks[desired_block_index]
            if not isinstance(base_block, TableIR) or not isinstance(desired_block, TableIR):
                continue
            base_special_kind = _special_table_kind_for_block(
                tab=base_tab,
                section_index=section_index,
                block_index=base_block_index,
            )
            desired_special_kind = _special_table_kind_for_block(
                tab=desired_tab,
                section_index=section_index,
                block_index=desired_block_index,
            )
            if base_special_kind != desired_special_kind and (
                base_special_kind is not None or desired_special_kind is not None
            ):
                edits.append(
                    DeleteTableBlockEdit(
                        tab_id=tab_id,
                        section_index=section_index,
                        block_index=base_block_index,
                    )
                )
                edits.append(
                    InsertTableBlockEdit(
                        tab_id=tab_id,
                        section_index=section_index,
                        block_index=base_block_index,
                        table=desired_block,
                    )
                )
                continue
            if (
                base_special_kind is not None
                and desired_special_kind is not None
                and base_block != desired_block
            ):
                edits.append(
                    DeleteTableBlockEdit(
                        tab_id=tab_id,
                        section_index=section_index,
                        block_index=base_block_index,
                    )
                )
                edits.append(
                    InsertTableBlockEdit(
                        tab_id=tab_id,
                        section_index=section_index,
                        block_index=base_block_index,
                        table=desired_block,
                    )
                )
                continue
            try:
                plan = _plan_table_comparison(
                    tab_id=tab_id,
                    section_index=section_index,
                    block_index=base_block_index,
                    base_table=base_block,
                    desired_table=desired_block,
                )
            except UnsupportedSpikeError:
                edits.append(
                    DeleteTableBlockEdit(
                        tab_id=tab_id,
                        section_index=section_index,
                        block_index=base_block_index,
                    )
                )
                edits.append(
                    InsertTableBlockEdit(
                        tab_id=tab_id,
                        section_index=section_index,
                        block_index=base_block_index,
                        table=desired_block,
                    )
                )
                continue
            if plan is None:
                continue
            if not _same_special_table_kind(
                base_tab=base_tab,
                desired_tab=desired_tab,
                section_index=section_index,
                base_block_index=base_block_index,
                desired_block_index=desired_block_index,
            ):
                edits.extend(
                    _diff_table_properties(
                        tab_id=tab_id,
                        section_index=section_index,
                        block_index=base_block_index,
                        base_table=base_block,
                        desired_table=desired_block,
                        plan=plan,
                    )
                )
            if plan.recurse_cells:
                for base_row_index, desired_row_index in plan.row_pairs:
                    base_row = base_block.rows[base_row_index]
                    desired_row = desired_block.rows[desired_row_index]
                    for base_column_index, desired_column_index in plan.column_pairs:
                        if (
                            base_column_index >= len(base_row.cells)
                            or desired_column_index >= len(desired_row.cells)
                        ):
                            continue
                        base_cell = base_row.cells[base_column_index]
                        desired_cell = desired_row.cells[desired_column_index]
                        edit = _diff_story_paragraph_slice(
                            tab_id=tab_id,
                            story_id=(
                                f"{tab_id}:body:table:{base_block_index}:r{base_row_index}:c{base_column_index}"
                            ),
                            section_index=None,
                            base_blocks=base_cell.content.blocks,
                            desired_blocks=desired_cell.content.blocks,
                        )
                        if edit is not None:
                            edits.append(edit)
            edits.extend(plan.structural_edits)
    return edits


def _same_special_table_kind(
    *,
    base_tab: TabIR,
    desired_tab: TabIR,
    section_index: int,
    base_block_index: int,
    desired_block_index: int,
) -> bool:
    base_kind = _special_table_kind_for_block(
        tab=base_tab,
        section_index=section_index,
        block_index=base_block_index,
    )
    if base_kind is None:
        return False
    desired_kind = _special_table_kind_for_block(
        tab=desired_tab,
        section_index=section_index,
        block_index=desired_block_index,
    )
    return desired_kind == base_kind


def _special_table_kind_for_block(
    *,
    tab: TabIR,
    section_index: int,
    block_index: int,
) -> str | None:
    story_id = f"{tab.id}:body"
    for name, ranges in tab.annotations.named_ranges.items():
        if not name.startswith("extradoc:"):
            continue
        for anchor in ranges:
            start = anchor.start.path
            end = anchor.end.path
            if (
                anchor.start.story_id != story_id
                or anchor.end.story_id != story_id
                or start.section_index != section_index
                or end.section_index != section_index
                or start.block_index != block_index
                or start.node_path
                or end.node_path
                or start.edge.value != "BEFORE"
            ):
                continue
            if start.inline_index is not None or start.text_offset_utf16 is not None:
                continue
            if end.block_index not in {block_index, block_index + 1}:
                continue
            if end.edge.value in {"BEFORE", "AFTER"}:
                if end.inline_index is not None or end.text_offset_utf16 is not None:
                    continue
            elif end.edge.value == "INTERIOR":
                if (
                    end.block_index != block_index + 1
                    or end.inline_index != 0
                    or end.text_offset_utf16 != 0
                ):
                    continue
            else:
                continue
            return name
    return None


def _plan_table_comparison(
    *,
    tab_id: str,
    section_index: int,
    block_index: int,
    base_table: TableIR,
    desired_table: TableIR,
) -> TableComparisonPlan | None:
    base_row_count = len(base_table.rows)
    desired_row_count = len(desired_table.rows)
    base_column_count = max((len(row.cells) for row in base_table.rows), default=0)
    desired_column_count = max((len(row.cells) for row in desired_table.rows), default=0)
    if abs(desired_row_count - base_row_count) > 1 or abs(desired_column_count - base_column_count) > 1:
        raise UnsupportedSpikeError(
            "reconcile_v2 currently supports at most one row or one column structural change"
        )
    if desired_column_count != base_column_count and (
        _table_has_horizontal_merges(base_table) or _table_has_horizontal_merges(desired_table)
    ):
        raise UnsupportedSpikeError(
            "reconcile_v2 does not yet support column structural edits through merged regions"
        )
    shared_row_pairs = tuple((index, index) for index in range(min(base_row_count, desired_row_count)))
    shared_column_pairs = tuple(
        (index, index) for index in range(min(base_column_count, desired_column_count))
    )

    row_plan = _single_row_table_edit(
        tab_id=tab_id,
        section_index=section_index,
        block_index=block_index,
        base_table=base_table,
        desired_table=desired_table,
        base_row_count=base_row_count,
        desired_row_count=desired_row_count,
    )
    column_plan = _single_column_table_edit(
        tab_id=tab_id,
        section_index=section_index,
        block_index=block_index,
        base_table=base_table,
        desired_table=desired_table,
        base_column_count=base_column_count,
        desired_column_count=desired_column_count,
    )
    if row_plan is not None or column_plan is not None:
        structural_edits: list[SemanticEdit] = []
        row_pairs = shared_row_pairs
        column_pairs = shared_column_pairs
        if row_plan is not None:
            structural_edits.append(row_plan[0])
            row_pairs = row_plan[1]
        if column_plan is not None:
            structural_edits.append(column_plan[0])
            column_pairs = column_plan[1]
        return TableComparisonPlan(
            row_pairs=row_pairs,
            column_pairs=column_pairs,
            structural_edits=tuple(structural_edits),
        )

    merge_change = _table_merge_change(base_table, desired_table)
    if (desired_row_count != base_row_count or desired_column_count != base_column_count) and merge_change is not None:
        raise UnsupportedSpikeError(
            "reconcile_v2 does not yet support structural edits intersecting merge-topology changes"
        )
    if merge_change is None:
        return TableComparisonPlan(
            row_pairs=shared_row_pairs,
            column_pairs=shared_column_pairs,
        )

    row_index, column_index, before_span, after_span = merge_change
    if before_span == (1, 1) and after_span != (1, 1):
        return TableComparisonPlan(
            row_pairs=shared_row_pairs,
            column_pairs=shared_column_pairs,
            structural_edits=(
                MergeTableCellsEdit(
                    tab_id=tab_id,
                    section_index=section_index,
                    block_index=block_index,
                    row_index=row_index,
                    column_index=column_index,
                    row_span=after_span[0],
                    column_span=after_span[1],
                ),
            ),
            recurse_cells=False,
        )
    if before_span != (1, 1) and after_span == (1, 1):
        return TableComparisonPlan(
            row_pairs=shared_row_pairs,
            column_pairs=shared_column_pairs,
            structural_edits=(
                UnmergeTableCellsEdit(
                    tab_id=tab_id,
                    section_index=section_index,
                    block_index=block_index,
                    row_index=row_index,
                    column_index=column_index,
                    row_span=before_span[0],
                    column_span=before_span[1],
                ),
            ),
            recurse_cells=False,
        )
    return TableComparisonPlan(
        row_pairs=shared_row_pairs,
        column_pairs=shared_column_pairs,
        recurse_cells=False,
    )


def _single_row_table_edit(
    *,
    tab_id: str,
    section_index: int,
    block_index: int,
    base_table: TableIR,
    desired_table: TableIR,
    base_row_count: int,
    desired_row_count: int,
) -> tuple[SemanticEdit, tuple[tuple[int, int], ...]] | None:
    row_insert_index = _best_single_insertion_index(
        _table_row_signatures(base_table),
        _table_row_signatures(desired_table),
        similarity=_signature_tuple_similarity,
    )
    if row_insert_index is not None:
        inserted_cells = _inserted_row_cell_texts(desired_table, row_insert_index)
        return (
            InsertTableRowEdit(
                tab_id=tab_id,
                section_index=section_index,
                block_index=block_index,
                row_index=max(0, row_insert_index - 1),
                insert_below=row_insert_index > 0,
                inserted_cells=inserted_cells,
            ),
            tuple(
                (index, index if index < row_insert_index else index + 1)
                for index in range(base_row_count)
            ),
        )
    row_delete_index = _best_single_deletion_index(
        _table_row_signatures(base_table),
        _table_row_signatures(desired_table),
        similarity=_signature_tuple_similarity,
    )
    if row_delete_index is not None:
        return (
            DeleteTableRowEdit(
                tab_id=tab_id,
                section_index=section_index,
                block_index=block_index,
                row_index=row_delete_index,
            ),
            tuple(
                (index, index if index < row_delete_index else index - 1)
                for index in range(base_row_count)
                if index != row_delete_index
            ),
        )
    if desired_row_count != base_row_count:
        raise UnsupportedSpikeError(
            "reconcile_v2 could not align the row structural edit"
        )
    return None


def _single_column_table_edit(
    *,
    tab_id: str,
    section_index: int,
    block_index: int,
    base_table: TableIR,
    desired_table: TableIR,
    base_column_count: int,
    desired_column_count: int,
) -> tuple[SemanticEdit, tuple[tuple[int, int], ...]] | None:
    column_insert_index = _best_single_insertion_index(
        _table_column_signatures(base_table),
        _table_column_signatures(desired_table),
        similarity=_signature_tuple_similarity,
    )
    if column_insert_index is not None:
        inserted_cells = _inserted_column_cell_texts(desired_table, column_insert_index)
        return (
            InsertTableColumnEdit(
                tab_id=tab_id,
                section_index=section_index,
                block_index=block_index,
                column_index=max(0, column_insert_index - 1),
                insert_right=column_insert_index > 0,
                inserted_cells=inserted_cells,
            ),
            tuple(
                (index, index if index < column_insert_index else index + 1)
                for index in range(base_column_count)
            ),
        )

    column_delete_index = _best_single_deletion_index(
        _table_column_signatures(base_table),
        _table_column_signatures(desired_table),
        similarity=_signature_tuple_similarity,
    )
    if column_delete_index is not None:
        return (
            DeleteTableColumnEdit(
                tab_id=tab_id,
                section_index=section_index,
                block_index=block_index,
                column_index=column_delete_index,
            ),
            tuple(
                (index, index if index < column_delete_index else index - 1)
                for index in range(base_column_count)
                if index != column_delete_index
            ),
        )
    if desired_column_count != base_column_count:
        raise UnsupportedSpikeError(
            "reconcile_v2 could not align the column structural edit"
        )
    return None


def _diff_table_properties(
    *,
    tab_id: str,
    section_index: int,
    block_index: int,
    base_table: TableIR,
    desired_table: TableIR,
    plan: TableComparisonPlan,
) -> list[SemanticEdit]:
    edits: list[SemanticEdit] = []
    if base_table.pinned_header_rows != desired_table.pinned_header_rows:
        edits.append(
            UpdateTablePinnedHeaderRowsEdit(
                tab_id=tab_id,
                section_index=section_index,
                block_index=block_index,
                pinned_header_rows=desired_table.pinned_header_rows,
            )
        )

    for base_row_index, desired_row_index in plan.row_pairs:
        row_style, row_fields = _style_delta(
            base_table.rows[base_row_index].style,
            desired_table.rows[desired_row_index].style,
        )
        if row_fields and row_style:
            edits.append(
                UpdateTableRowStyleEdit(
                    tab_id=tab_id,
                    section_index=section_index,
                    block_index=block_index,
                    row_index=base_row_index,
                    style=row_style,
                    fields=row_fields,
                )
            )

    for base_column_index, desired_column_index in plan.column_pairs:
        if (
            base_column_index >= len(base_table.column_properties)
            or desired_column_index >= len(desired_table.column_properties)
        ):
            continue
        properties, fields = _style_delta(
            base_table.column_properties[base_column_index],
            desired_table.column_properties[desired_column_index],
        )
        if fields and properties:
            edits.append(
                UpdateTableColumnPropertiesEdit(
                    tab_id=tab_id,
                    section_index=section_index,
                    block_index=block_index,
                    column_index=base_column_index,
                    properties=properties,
                    fields=fields,
                )
            )

    for base_row_index, desired_row_index in plan.row_pairs:
        base_row = base_table.rows[base_row_index]
        desired_row = desired_table.rows[desired_row_index]
        for base_column_index, desired_column_index in plan.column_pairs:
            if (
                base_column_index >= len(base_row.cells)
                or desired_column_index >= len(desired_row.cells)
            ):
                continue
            style, fields = _style_delta(
                _cell_style_payload(base_row.cells[base_column_index].style),
                _cell_style_payload(desired_row.cells[desired_column_index].style),
            )
            if fields and style:
                edits.append(
                    UpdateTableCellStyleEdit(
                        tab_id=tab_id,
                        section_index=section_index,
                        block_index=block_index,
                        row_index=base_row_index,
                        column_index=base_column_index,
                        style=style,
                        fields=fields,
                    )
                )
    return edits


def _diff_story_paragraph_slice(
    *,
    tab_id: str,
    story_id: str,
    section_index: int | None,
    base_blocks: list[BlockIR],
    desired_blocks: list[BlockIR],
    block_offset: int = 0,
    raw_block_offset: int | None = None,
) -> SemanticEdit | None:
    if not _all_paragraphs(base_blocks) or not _all_paragraphs(desired_blocks):
        return None

    if (
        len(base_blocks) == len(desired_blocks)
        and [_paragraph_text(block) for block in base_blocks]
        == [_paragraph_text(block) for block in desired_blocks]
    ):
        return None

    base_signatures = [_paragraph_signature(block) for block in base_blocks]
    desired_signatures = [_paragraph_signature(block) for block in desired_blocks]
    if base_signatures == desired_signatures:
        return None

    prefix = 0
    while (
        prefix < len(base_signatures)
        and prefix < len(desired_signatures)
        and base_signatures[prefix] == desired_signatures[prefix]
    ):
        prefix += 1

    suffix = 0
    while (
        suffix < len(base_signatures) - prefix
        and suffix < len(desired_signatures) - prefix
        and base_signatures[-(suffix + 1)] == desired_signatures[-(suffix + 1)]
    ):
        suffix += 1

    delete_stop = len(base_blocks) - suffix
    insert_stop = len(desired_blocks) - suffix
    if delete_stop <= prefix and insert_stop <= prefix:
        return None

    base_slice = base_blocks[prefix:delete_stop]
    desired_slice = desired_blocks[prefix:insert_stop]
    if (
        len(base_slice) == 1
        and len(desired_slice) == 1
        and isinstance(base_slice[0], ParagraphIR)
        and isinstance(desired_slice[0], ParagraphIR)
        and base_slice[0].role == desired_slice[0].role
        and _non_text_inline_signature(base_slice[0]) == _non_text_inline_signature(desired_slice[0])
        and not _paragraphs_share_trailing_single_footnote_ref(base_slice[0], desired_slice[0])
    ):
        return ReplaceParagraphTextEdit(
            tab_id=tab_id,
            story_id=story_id,
            section_index=section_index,
            block_index=block_offset + prefix,
            desired_paragraph=desired_slice[0],
        )

    return ReplaceParagraphSliceEdit(
        tab_id=tab_id,
        story_id=story_id,
        section_index=section_index,
        start_block_index=block_offset + prefix,
        delete_block_count=max(0, delete_stop - prefix),
        inserted_paragraphs=tuple(
            ParagraphFragment(paragraph=block)
            for block in desired_slice
        ),
        body_anchor_block_index=(
            None if raw_block_offset is None or section_index is None or story_id != f"{tab_id}:body"
            else raw_block_offset + prefix
        ),
    )


def _diff_named_ranges(
    base: TabIR,
    desired: TabIR,
    *,
    content_edits: list[SemanticEdit],
) -> list[SemanticEdit]:
    edits: list[SemanticEdit] = []
    all_names = set(base.annotations.named_ranges) | set(desired.annotations.named_ranges)
    for name in sorted(all_names):
        base_ranges = tuple(base.annotations.named_ranges.get(name, []))
        desired_ranges = tuple(desired.annotations.named_ranges.get(name, []))
        signatures_match = _named_range_signature(name, base_ranges) == _named_range_signature(
            name,
            desired_ranges,
        )
        if signatures_match and not _special_named_range_requires_refresh(
            name=name,
            base_ranges=base_ranges,
            desired_ranges=desired_ranges,
            content_edits=content_edits,
        ):
            continue
        edits.append(
            ReplaceNamedRangesEdit(
                tab_id=base.id,
                name=name,
                before_count=len(base_ranges),
                desired_ranges=desired_ranges,
            )
        )
    return edits


def _section_boundaries(sections: list[SectionIR]) -> list[int]:
    return _section_prefix_counts(sections)[:-1]


def _section_prefix_counts(sections: list[SectionIR]) -> list[int]:
    return list(accumulate(len(section.blocks) for section in sections))


def _locate_split_anchor(sections: list[SectionIR], boundary: int) -> tuple[int, int]:
    consumed = 0
    for section_index, section in enumerate(sections):
        next_consumed = consumed + len(section.blocks)
        if boundary < next_consumed:
            return section_index, boundary - consumed - 1
        consumed = next_consumed
    raise ValueError(f"Cannot locate section split anchor for boundary {boundary}")


def _flatten_section_fingerprints(sections: list[SectionIR]) -> list[str]:
    return [fingerprint for section in sections for fingerprint in _block_fingerprints(section.blocks)]


def _block_fingerprints(blocks: list[BlockIR]) -> list[str]:
    fingerprints: list[str] = []
    for block in blocks:
        if isinstance(block, ParagraphIR):
            fingerprints.append(f"P:{block.role}:{_paragraph_text(block)}")
        elif isinstance(block, ListIR):
            items = "|".join(
                f"{item.level}:{_paragraph_text(item.paragraph)}" for item in block.items
            )
            fingerprints.append(f"L:{block.spec.kind}:{items}")
        else:
            fingerprints.append(type(block).__name__)
    return fingerprints


def _paragraph_text(paragraph: ParagraphIR) -> str:
    return "".join(
        inline.text for inline in paragraph.inlines if isinstance(inline, TextSpanIR)
    )


def _is_empty_paragraph_block(block: BlockIR) -> bool:
    return isinstance(block, ParagraphIR) and _paragraph_text(block) == ""


def _footnote_insertion_offset(paragraph: ParagraphIR) -> int:
    offset = 0
    for inline in paragraph.inlines:
        if isinstance(inline, FootnoteRefIR):
            return offset
        if isinstance(inline, TextSpanIR):
            offset += utf16_len(inline.text)
    return offset


def _all_paragraphs(blocks: list[BlockIR]) -> bool:
    return all(isinstance(block, ParagraphIR) for block in blocks)


def _paragraph_signature(paragraph: ParagraphIR) -> tuple[str, str]:
    trailing_ref = _trailing_single_footnote_ref(paragraph)
    if trailing_ref is not None:
        return ("TRAILING_FOOTNOTE_REF", trailing_ref)
    return paragraph.role, _paragraph_text(paragraph)


def _non_text_inline_signature(paragraph: ParagraphIR) -> tuple[tuple[object, ...], ...]:
    signature: list[tuple[object, ...]] = []
    for inline in paragraph.inlines:
        if isinstance(inline, TextSpanIR):
            continue
        if isinstance(inline, FootnoteRefIR):
            signature.append(("footnote", inline.ref))
            continue
        if isinstance(inline, OpaqueInlineIR):
            signature.append(("opaque", inline.kind, tuple(sorted(inline.payload.items()))))
            continue
        signature.append((type(inline).__name__, repr(inline)))
    return tuple(signature)


def _is_read_only_paragraph(paragraph: ParagraphIR) -> bool:
    opaque_inlines = [inline for inline in paragraph.inlines if isinstance(inline, OpaqueInlineIR)]
    if len(opaque_inlines) != 1:
        return False
    if opaque_inlines[0].kind != "horizontal_rule":
        return False
    return all(not isinstance(inline, TextSpanIR) or inline.text == "" for inline in paragraph.inlines)


def _trailing_single_footnote_ref(paragraph: ParagraphIR) -> str | None:
    refs = [inline.ref for inline in paragraph.inlines if isinstance(inline, FootnoteRefIR)]
    if len(refs) != 1:
        return None
    footnote_seen = False
    for inline in paragraph.inlines:
        if isinstance(inline, TextSpanIR):
            if footnote_seen and inline.text:
                return None
            continue
        if isinstance(inline, FootnoteRefIR):
            if footnote_seen:
                return None
            footnote_seen = True
            continue
        return None
    return refs[0] if footnote_seen else None


def _paragraphs_share_trailing_single_footnote_ref(
    base: ParagraphIR,
    desired: ParagraphIR,
) -> bool:
    base_ref = _trailing_single_footnote_ref(base)
    desired_ref = _trailing_single_footnote_ref(desired)
    return base_ref is not None and base_ref == desired_ref


def _story_signature(story: StoryIR) -> tuple[str, ...]:
    return tuple(_block_fingerprints(story.blocks))


def _attachment_ref_counts(
    sections: list[SectionIR],
    attachment_kind: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for section in sections:
        for story_id in getattr(section.attachments, attachment_kind).values():
            counts[story_id] = counts.get(story_id, 0) + 1
    return counts


def _style_delta(
    base_style: dict[str, object],
    desired_style: dict[str, object],
) -> tuple[dict[str, object], tuple[str, ...]]:
    fields = tuple(
        key
        for key in sorted(set(base_style) | set(desired_style))
        if base_style.get(key) != desired_style.get(key)
    )
    return {key: desired_style[key] for key in fields if key in desired_style}, fields


def _cell_style_payload(style: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in style.items()
        if key not in {"rowSpan", "columnSpan"}
    }


def _named_range_signature(
    name: str,
    ranges: tuple[AnchorRangeIR, ...],
) -> tuple[tuple[str, ...], ...]:
    if name.startswith("extradoc:"):
        return tuple(_special_named_range_signature(anchor) for anchor in ranges)
    return tuple(
        (
            _position_signature(anchor.start),
            _position_signature(anchor.end),
        )
        for anchor in ranges
    )


def _special_named_range_signature(anchor: AnchorRangeIR) -> tuple[str, ...]:
    start = anchor.start.path
    return (
        _position_signature(anchor.start).split("|", 1)[0],
        str(start.section_index),
        str(start.block_index),
    )


def _special_named_range_requires_refresh(
    *,
    name: str,
    base_ranges: tuple[AnchorRangeIR, ...],
    desired_ranges: tuple[AnchorRangeIR, ...],
    content_edits: list[SemanticEdit],
) -> bool:
    if not name.startswith("extradoc:"):
        return False
    ranges = desired_ranges or base_ranges
    return any(
        _content_edit_touches_special_named_range(edit, anchor)
        for anchor in ranges
        for edit in content_edits
    )


def _content_edit_touches_special_named_range(
    edit: SemanticEdit,
    anchor: AnchorRangeIR,
) -> bool:
    story_id = anchor.start.story_id
    path = anchor.start.path
    if not story_id.endswith(":body"):
        return False
    expected_tab_id = story_id[:-5]
    if isinstance(edit, DeleteTableBlockEdit | DeleteListBlockEdit):
        return (
            edit.tab_id == expected_tab_id
            and edit.section_index == path.section_index
            and edit.block_index == path.block_index
        )
    if (
        isinstance(edit, ReplaceParagraphSliceEdit)
        and edit.story_id == story_id
        and edit.section_index == path.section_index
        and edit.delete_block_count > 0
    ):
        delete_stop = edit.start_block_index + edit.delete_block_count
        return edit.start_block_index <= path.block_index < delete_stop
    return False


def _position_signature(position: PositionIR) -> str:
    path = position.path
    return (
        f"{_story_identity_signature(position.story_id)}|"
        f"{path.section_index}|{path.block_index}|{path.node_path}|"
        f"{path.inline_index}|{path.text_offset_utf16}|{path.edge}"
    )


def _story_identity_signature(story_id: str) -> str:
    _, _, suffix = story_id.partition(":")
    return suffix or story_id


def _table_row_signatures(table: TableIR) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(_table_cell_signature(cell) for cell in row.cells) for row in table.rows)


def _table_has_horizontal_merges(table: TableIR) -> bool:
    return any(cell.column_span > 1 for row in table.rows for cell in row.cells)


def _inserted_row_cell_texts(table: TableIR, row_index: int) -> tuple[str, ...]:
    if row_index >= len(table.rows):
        return ()
    return tuple(_simple_cell_text(cell) for cell in table.rows[row_index].cells)


def _inserted_column_cell_texts(table: TableIR, column_index: int) -> tuple[str, ...]:
    texts: list[str] = []
    for row in table.rows:
        if column_index >= len(row.cells):
            raise UnsupportedSpikeError(
                "reconcile_v2 requires rectangular inserted-column fixtures"
            )
        texts.append(_simple_cell_text(row.cells[column_index]))
    return tuple(texts)


def _simple_cell_text(cell: object) -> str:
    if any(not isinstance(block, ParagraphIR) for block in cell.content.blocks):
        raise UnsupportedSpikeError(
            "reconcile_v2 supports inserted row/column content only for paragraph-only cells"
        )
    if len(cell.content.blocks) > 1:
        raise UnsupportedSpikeError(
            "reconcile_v2 supports inserted row/column content only for single-paragraph cells"
        )
    if not cell.content.blocks:
        return ""
    return _paragraph_text(cell.content.blocks[0])


def _table_cell_signature(cell: object) -> str:
    texts = [
        _paragraph_text(block)
        for block in cell.content.blocks
        if isinstance(block, ParagraphIR)
    ]
    return f"{cell.row_span}:{cell.column_span}:{'|'.join(texts)}"


def _table_column_signatures(table: TableIR) -> tuple[tuple[str, ...], ...]:
    if not table.rows:
        return ()
    max_columns = max(len(row.cells) for row in table.rows)
    return tuple(
        tuple(
            _table_cell_signature(row.cells[column_index])
            for row in table.rows
            if column_index < len(row.cells)
        )
        for column_index in range(max_columns)
    )


def _best_single_insertion_index(
    base: tuple[T, ...],
    desired: tuple[T, ...],
    *,
    similarity: Callable[[T, T], int],
) -> int | None:
    if len(desired) != len(base) + 1:
        return None
    exact_index = _exact_single_insertion_index(base, desired)
    if exact_index is not None:
        return exact_index
    best_index: int | None = None
    best_score: int | None = None
    for insert_index in range(len(desired)):
        score = 0
        for base_index, base_item in enumerate(base):
            desired_index = base_index if base_index < insert_index else base_index + 1
            score += similarity(base_item, desired[desired_index])
        if best_score is None or score > best_score:
            best_index = insert_index
            best_score = score
    return best_index


def _best_single_deletion_index(
    base: tuple[T, ...],
    desired: tuple[T, ...],
    *,
    similarity: Callable[[T, T], int],
) -> int | None:
    if len(base) != len(desired) + 1:
        return None
    exact_index = _exact_single_deletion_index(base, desired)
    if exact_index is not None:
        return exact_index
    best_index: int | None = None
    best_score: int | None = None
    for delete_index in range(len(base)):
        score = 0
        for base_index, base_item in enumerate(base):
            if base_index == delete_index:
                continue
            desired_index = base_index if base_index < delete_index else base_index - 1
            score += similarity(base_item, desired[desired_index])
        if best_score is None or score > best_score:
            best_index = delete_index
            best_score = score
    return best_index


def _signature_tuple_similarity(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    score = sum(left_item == right_item for left_item, right_item in zip(left, right, strict=False))
    if len(left) == len(right):
        return score
    return score - abs(len(left) - len(right))


def _exact_single_insertion_index(base: tuple[T, ...], desired: tuple[T, ...]) -> int | None:
    if len(desired) != len(base) + 1:
        return None
    for insert_index in range(len(desired)):
        if desired[:insert_index] == base[:insert_index] and desired[insert_index + 1 :] == base[insert_index:]:
            return insert_index
    return None


def _exact_single_deletion_index(base: tuple[T, ...], desired: tuple[T, ...]) -> int | None:
    if len(base) != len(desired) + 1:
        return None
    for delete_index in range(len(base)):
        if base[:delete_index] == desired[:delete_index] and base[delete_index + 1 :] == desired[delete_index:]:
            return delete_index
    return None


def _table_merge_change(
    base_table: TableIR,
    desired_table: TableIR,
) -> tuple[int, int, tuple[int, int], tuple[int, int]] | None:
    if len(base_table.rows) != len(desired_table.rows):
        return None

    changes: list[tuple[int, int, tuple[int, int], tuple[int, int]]] = []
    for row_index, (base_row, desired_row) in enumerate(
        zip(base_table.rows, desired_table.rows, strict=False)
    ):
        if len(base_row.cells) != len(desired_row.cells):
            return None
        for column_index, (base_cell, desired_cell) in enumerate(
            zip(base_row.cells, desired_row.cells, strict=False)
        ):
            before_span = (base_cell.row_span, base_cell.column_span)
            after_span = (desired_cell.row_span, desired_cell.column_span)
            if before_span != after_span:
                changes.append((row_index, column_index, before_span, after_span))
    if len(changes) != 1:
        return None
    return changes[0]
