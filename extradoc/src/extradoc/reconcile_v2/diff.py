"""Compute a narrow semantic diff over the spike IR.

This is intentionally a confidence-sprint slice. The goal is not a complete
edit script, but a small set of semantic edits that test whether the revised
model can describe real Docs changes without collapsing back into transport
indices and carrier-paragraph hacks.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import accumulate
from typing import TYPE_CHECKING

from extradoc.reconcile_v2.canonical import canonicalize_document_ir
from extradoc.reconcile_v2.ir import (
    AnchorRangeIR,
    ListIR,
    ParagraphIR,
    PositionIR,
    SectionIR,
    StoryIR,
    TableIR,
    TextSpanIR,
)
from extradoc.reconcile_v2.parse import parse_document

if TYPE_CHECKING:
    from collections.abc import Iterable

    from extradoc.api_types._generated import Document
    from extradoc.reconcile_v2.ir import (
        BlockIR,
        DocumentIR,
        TabIR,
    )


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


@dataclass(frozen=True, slots=True)
class ParagraphFragment:
    role: str
    text: str


@dataclass(slots=True)
class ReplaceParagraphSliceEdit:
    tab_id: str
    story_id: str
    section_index: int | None
    start_block_index: int
    delete_block_count: int
    inserted_paragraphs: tuple[ParagraphFragment, ...]


@dataclass(slots=True)
class ReplaceNamedRangesEdit:
    tab_id: str
    name: str
    before_count: int
    desired_ranges: tuple[AnchorRangeIR, ...]


@dataclass(frozen=True, slots=True)
class ListItemFragment:
    level: int
    text: str


SemanticEdit = (
    InsertSectionEdit
    | DeleteSectionEdit
    | UpdateParagraphRoleEdit
    | AppendListItemsEdit
    | ReplaceListSpecEdit
    | ReplaceParagraphSliceEdit
    | ReplaceNamedRangesEdit
)


def diff_documents(base: Document, desired: Document) -> list[SemanticEdit]:
    """Return a small semantic edit list for confidence-sprint scenarios."""
    return diff_document_irs(parse_document(base), parse_document(desired))


def diff_document_irs(base: DocumentIR, desired: DocumentIR) -> list[SemanticEdit]:
    """Diff parsed IR values, normalizing away transport carrier paragraphs."""
    base = canonicalize_document_ir(base)
    desired = canonicalize_document_ir(desired)
    edits: list[SemanticEdit] = []
    desired_tabs = {tab.id: tab for tab in desired.tabs}
    for base_tab in base.tabs:
        desired_tab = desired_tabs.get(base_tab.id)
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
        elif isinstance(edit, ReplaceParagraphSliceEdit):
            lines.append(
                f"tab {edit.tab_id}: story {edit.story_id} replace "
                f"{edit.delete_block_count} paragraph block(s) at {edit.start_block_index} "
                f"with {len(edit.inserted_paragraphs)} paragraph(s)"
            )
        elif isinstance(edit, ReplaceNamedRangesEdit):
            lines.append(
                f"tab {edit.tab_id}: named range {edit.name} replace "
                f"{edit.before_count} range(s) with {len(edit.desired_ranges)} range(s)"
            )
    return lines


def _diff_tab(base: TabIR, desired: TabIR) -> list[SemanticEdit]:
    base_sections = base.body.sections
    desired_sections = desired.body.sections
    edits: list[SemanticEdit] = []
    edits.extend(_diff_named_ranges(base, desired))
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
        _diff_section_tables(
            tab_id=base.id,
            base_sections=base_sections,
            desired_sections=desired_sections,
        )
    )

    base_flat = _flatten_section_fingerprints(base_sections)
    desired_flat = _flatten_section_fingerprints(desired_sections)
    if base_flat == desired_flat:
        edits.extend(
            _diff_section_boundaries(
                tab_id=base.id,
                base_sections=base_sections,
                desired_sections=desired_sections,
            )
        )
        return edits

    for section_index, (base_section, desired_section) in enumerate(
        zip(base_sections, desired_sections, strict=False)
    ):
        edits.extend(
            _diff_section_blocks(
                tab_id=base.id,
                section_index=section_index,
                base_section=base_section,
                desired_section=desired_section,
            )
        )
    return edits


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
    edits: list[SemanticEdit] = []
    paragraph_slice = _diff_story_paragraph_slice(
        tab_id=tab_id,
        story_id=f"{tab_id}:body",
        section_index=section_index,
        base_blocks=base_section.blocks,
        desired_blocks=desired_section.blocks,
    )
    if paragraph_slice is not None:
        edits.append(paragraph_slice)
        return edits

    for block_index, (base_block, desired_block) in enumerate(
        zip(base_section.blocks, desired_section.blocks, strict=False)
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
                        block_index=block_index,
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
                        block_index=block_index,
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
                        block_index=block_index,
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
    return edits


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
            story_pair = (base_attachments[slot], desired_attachments[slot])
            if story_pair in seen_pairs:
                continue
            seen_pairs.add(story_pair)
            base_story = base_catalog.get(story_pair[0])
            desired_story = desired_catalog.get(story_pair[1])
            if base_story is None or desired_story is None:
                continue
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
) -> list[SemanticEdit]:
    edits: list[SemanticEdit] = []
    for story_ref in sorted(set(base_catalog) & set(desired_catalog)):
        edit = _diff_story_paragraph_slice(
            tab_id=tab_id,
            story_id=base_catalog[story_ref].id,
            section_index=None,
            base_blocks=base_catalog[story_ref].blocks,
            desired_blocks=desired_catalog[story_ref].blocks,
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
    for _section_index, (base_section, desired_section) in enumerate(
        zip(base_sections, desired_sections, strict=False)
    ):
        for block_index, (base_block, desired_block) in enumerate(
            zip(base_section.blocks, desired_section.blocks, strict=False)
        ):
            if not isinstance(base_block, TableIR) or not isinstance(desired_block, TableIR):
                continue
            if len(base_block.rows) != len(desired_block.rows):
                continue
            for row_index, (base_row, desired_row) in enumerate(
                zip(base_block.rows, desired_block.rows, strict=False)
            ):
                if len(base_row.cells) != len(desired_row.cells):
                    continue
                for column_index, (base_cell, desired_cell) in enumerate(
                    zip(base_row.cells, desired_row.cells, strict=False)
                ):
                    edit = _diff_story_paragraph_slice(
                        tab_id=tab_id,
                        story_id=(
                            f"{tab_id}:body:table:{block_index}:r{row_index}:c{column_index}"
                        ),
                        section_index=None,
                        base_blocks=base_cell.content.blocks,
                        desired_blocks=desired_cell.content.blocks,
                    )
                    if edit is not None:
                        edits.append(edit)
    return edits


def _diff_story_paragraph_slice(
    *,
    tab_id: str,
    story_id: str,
    section_index: int | None,
    base_blocks: list[BlockIR],
    desired_blocks: list[BlockIR],
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
        start_block_index=prefix,
        delete_block_count=max(0, delete_stop - prefix),
        inserted_paragraphs=tuple(
            ParagraphFragment(role=block.role, text=_paragraph_text(block))
            for block in desired_blocks[prefix:insert_stop]
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
            items = "|".join(_paragraph_text(item.paragraph) for item in block.items)
            fingerprints.append(f"L:{block.spec.kind}:{items}")
        else:
            fingerprints.append(type(block).__name__)
    return fingerprints


def _paragraph_text(paragraph: ParagraphIR) -> str:
    return "".join(
        inline.text for inline in paragraph.inlines if isinstance(inline, TextSpanIR)
    )


def _all_paragraphs(blocks: list[BlockIR]) -> bool:
    return bool(blocks) and all(isinstance(block, ParagraphIR) for block in blocks)


def _paragraph_signature(paragraph: ParagraphIR) -> tuple[str, str]:
    return paragraph.role, _paragraph_text(paragraph)


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
        f"{position.story_id}|{path.section_index}|{path.block_index}|{path.node_path}|"
        f"{path.inline_index}|{path.text_offset_utf16}|{path.edge}"
    )
