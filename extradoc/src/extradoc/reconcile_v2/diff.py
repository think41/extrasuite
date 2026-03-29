"""Compute a narrow semantic diff over the spike IR.

This is intentionally a confidence-sprint slice. The goal is not a complete
edit script, but a small set of semantic edits that test whether the revised
model can describe real Docs changes without collapsing back into transport
indices and carrier-paragraph hacks.
"""

from __future__ import annotations

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
    | AppendListItemsEdit
    | ReplaceListSpecEdit
    | RelevelListItemsEdit
    | ReplaceParagraphSliceEdit
    | InsertListBlockEdit
    | DeleteListBlockEdit
    | InsertTableBlockEdit
    | DeleteTableBlockEdit
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
    """Return a small semantic edit list for confidence-sprint scenarios."""
    return diff_document_irs(parse_document(base), parse_document(desired))


def diff_document_irs(base: DocumentIR, desired: DocumentIR) -> list[SemanticEdit]:
    """Diff parsed IR values, normalizing away transport carrier paragraphs."""
    base = canonicalize_document_ir(base)
    desired = canonicalize_document_ir(desired)
    edits: list[SemanticEdit] = []
    desired_tabs = _tabs_by_path(desired.tabs)
    for path, base_tab in _walk_tabs(base.tabs):
        desired_tab = desired_tabs.get(path)
        if desired_tab is None:
            continue
        edits.extend(_diff_tab(base_tab, desired_tab))
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


def _diff_tab(base: TabIR, desired: TabIR) -> list[SemanticEdit]:
    base_sections = base.body.sections
    desired_sections = desired.body.sections
    _ensure_read_only_blocks_unchanged(base_sections, desired_sections)
    edits: list[SemanticEdit] = []
    edits.extend(_diff_named_ranges(base, desired))
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
        base_sections=base_sections,
        desired_sections=desired_sections,
    )

    base_flat = _flatten_section_fingerprints(base_sections)
    desired_flat = _flatten_section_fingerprints(desired_sections)
    if base_flat == desired_flat:
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
            )
        )
    edits.extend(_filter_conflicting_table_edits(table_edits, block_edits))
    edits.extend(block_edits)
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
        if isinstance(edit, DeleteListBlockEdit | DeleteTableBlockEdit):
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
    return isinstance(block, TocIR | OpaqueBlockIR)


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
) -> list[SemanticEdit]:
    base_read_only = _read_only_block_positions(base_section.blocks)
    desired_read_only = _read_only_block_positions(desired_section.blocks)
    if not base_read_only and not desired_read_only:
        return _diff_editable_block_span(
            tab_id=tab_id,
            section_index=section_index,
            base_blocks=base_section.blocks,
            desired_blocks=desired_section.blocks,
            block_offset=0,
            raw_block_offset=0,
        )

    spans: list[tuple[list[BlockIR], list[BlockIR], int, int]] = []
    base_start = 0
    desired_start = 0
    editable_offset = 0
    for (base_index, _base_block), (desired_index, _desired_block) in zip(
        base_read_only,
        desired_read_only,
        strict=True,
    ):
        spans.append(
            (
                base_section.blocks[base_start:base_index],
                desired_section.blocks[desired_start:desired_index],
                editable_offset,
                base_start,
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
            base_start,
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


def _diff_editable_block_span(
    *,
    tab_id: str,
    section_index: int,
    base_blocks: list[BlockIR],
    desired_blocks: list[BlockIR],
    block_offset: int,
    raw_block_offset: int,
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
            if base_block.spec.signature != desired_block.spec.signature:
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
    return edits


def _diff_section_block_slice(
    *,
    tab_id: str,
    section_index: int,
    base_blocks: list[BlockIR],
    desired_blocks: list[BlockIR],
    block_offset: int,
    raw_block_offset: int,
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

    if _all_paragraphs(base_slice) and _all_paragraphs(desired_slice):
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
                body_anchor_block_index=raw_block_offset + prefix,
            )
        ]

    if (
        len(base_slice) == len(desired_slice) == 1
        and (
            (isinstance(base_slice[0], ListIR) and isinstance(desired_slice[0], ListIR))
            or (isinstance(base_slice[0], TableIR) and isinstance(desired_slice[0], TableIR))
        )
    ):
        return []

    return _plan_mixed_body_block_slice(
        tab_id=tab_id,
        section_index=section_index,
        block_index=block_offset + prefix,
        raw_block_index=raw_block_offset + prefix,
        base_slice=base_slice,
        desired_slice=desired_slice,
    )


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
    raw_start_block_index: int,
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
                    body_anchor_block_index=raw_start_block_index + start,
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
                    body_anchor_block_index=raw_start_block_index + index,
                )
            )
        elif isinstance(block, TableIR):
            edits.append(
                DeleteTableBlockEdit(
                    tab_id=tab_id,
                    section_index=section_index,
                    block_index=start_block_index + index,
                    body_anchor_block_index=raw_start_block_index + index,
                )
            )
        index -= 1
    return edits


def _insert_body_block_sequence(
    *,
    tab_id: str,
    section_index: int,
    block_index: int,
    raw_block_index: int,
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
    edits: list[SemanticEdit] = []
    for section_index, (base_section, desired_section) in enumerate(
        zip(base_sections, desired_sections, strict=False)
    ):
        for block_index, (base_block, desired_block) in enumerate(
            zip(base_section.blocks, desired_section.blocks, strict=False)
        ):
            if not isinstance(base_block, ParagraphIR) or not isinstance(desired_block, ParagraphIR):
                continue
            if _paragraph_text(base_block) != _paragraph_text(desired_block):
                continue
            base_refs = [inline.ref for inline in base_block.inlines if isinstance(inline, FootnoteRefIR)]
            desired_refs = [
                inline.ref for inline in desired_block.inlines if isinstance(inline, FootnoteRefIR)
            ]
            if len(base_refs) == 0 and len(desired_refs) == 1:
                desired_story = desired_catalog.get(desired_refs[0])
                if desired_story is None:
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
            if len(base_refs) != len(desired_refs):
                raise UnsupportedSpikeError(
                    "reconcile_v2 footnote spike supports only simple footnote creation "
                    "or matched-story content edits"
                )
            for base_ref, desired_ref in zip(base_refs, desired_refs, strict=True):
                if base_ref not in base_catalog or desired_ref not in desired_catalog:
                    continue
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
            if _paragraph_text(base_block) != _paragraph_text(desired_block):
                continue
            base_refs = [inline.ref for inline in base_block.inlines if isinstance(inline, FootnoteRefIR)]
            desired_refs = [
                inline.ref for inline in desired_block.inlines if isinstance(inline, FootnoteRefIR)
            ]
            if len(base_refs) != len(desired_refs):
                continue
            pairs.extend(zip(base_refs, desired_refs, strict=True))
    return tuple(pairs)


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
            if not isinstance(base_block, TableIR) or not isinstance(desired_block, TableIR):
                continue
            plan = _plan_table_comparison(
                tab_id=tab_id,
                section_index=section_index,
                block_index=block_index,
                base_table=base_block,
                desired_table=desired_block,
            )
            if plan is None:
                continue
            edits.extend(
                _diff_table_properties(
                    tab_id=tab_id,
                    section_index=section_index,
                    block_index=block_index,
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
                                f"{tab_id}:body:table:{block_index}:r{base_row_index}:c{base_column_index}"
                            ),
                            section_index=None,
                            base_blocks=base_cell.content.blocks,
                            desired_blocks=desired_cell.content.blocks,
                        )
                        if edit is not None:
                            edits.append(edit)
            edits.extend(plan.structural_edits)
    return edits


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
            "reconcile_v2 table spike supports at most one row or one column structural change"
        )
    if desired_column_count != base_column_count and (
        _table_has_horizontal_merges(base_table) or _table_has_horizontal_merges(desired_table)
    ):
        raise UnsupportedSpikeError(
            "reconcile_v2 table spike does not yet support column structural edits through merged regions"
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
            "reconcile_v2 table spike does not yet support structural edits intersecting merge-topology changes"
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
            "reconcile_v2 table spike could not align the row structural edit"
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
            "reconcile_v2 table spike could not align the column structural edit"
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
        if row_fields:
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
        if fields:
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
            if fields:
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
) -> ReplaceParagraphSliceEdit | None:
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

    return ReplaceParagraphSliceEdit(
        tab_id=tab_id,
        story_id=story_id,
        section_index=section_index,
        start_block_index=block_offset + prefix,
        delete_block_count=max(0, delete_stop - prefix),
        inserted_paragraphs=tuple(
            ParagraphFragment(paragraph=block)
            for block in desired_blocks[prefix:insert_stop]
        ),
        body_anchor_block_index=(
            None if raw_block_offset is None or section_index is None or story_id != f"{tab_id}:body"
            else raw_block_offset + prefix
        ),
    )


def _diff_named_ranges(base: TabIR, desired: TabIR) -> list[SemanticEdit]:
    edits: list[SemanticEdit] = []
    all_names = set(base.annotations.named_ranges) | set(desired.annotations.named_ranges)
    for name in sorted(all_names):
        base_ranges = tuple(base.annotations.named_ranges.get(name, []))
        desired_ranges = tuple(desired.annotations.named_ranges.get(name, []))
        if _named_range_signature(base_ranges) == _named_range_signature(desired_ranges):
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
    return paragraph.role, _paragraph_text(paragraph)


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


def _named_range_signature(ranges: tuple[AnchorRangeIR, ...]) -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            _position_signature(anchor.start),
            _position_signature(anchor.end),
        )
        for anchor in ranges
    )


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
                "reconcile_v2 table spike requires rectangular inserted-column fixtures"
            )
        texts.append(_simple_cell_text(row.cells[column_index]))
    return tuple(texts)


def _simple_cell_text(cell: object) -> str:
    if any(not isinstance(block, ParagraphIR) for block in cell.content.blocks):
        raise UnsupportedSpikeError(
            "reconcile_v2 table spike supports inserted row/column content only for paragraph-only cells"
        )
    if len(cell.content.blocks) > 1:
        raise UnsupportedSpikeError(
            "reconcile_v2 table spike supports inserted row/column content only for single-paragraph cells"
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
