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
from extradoc.reconcile_v2.ir import ListIR, ParagraphIR, SectionIR, TextSpanIR
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
class ListItemFragment:
    level: int
    text: str


SemanticEdit = (
    InsertSectionEdit
    | DeleteSectionEdit
    | UpdateParagraphRoleEdit
    | AppendListItemsEdit
    | ReplaceListSpecEdit
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
    return lines


def _diff_tab(base: TabIR, desired: TabIR) -> list[SemanticEdit]:
    base_sections = base.body.sections
    desired_sections = desired.body.sections

    base_flat = _flatten_section_fingerprints(base_sections)
    desired_flat = _flatten_section_fingerprints(desired_sections)
    if base_flat == desired_flat:
        return _diff_section_boundaries(
            tab_id=base.id,
            base_sections=base_sections,
            desired_sections=desired_sections,
        )

    edits: list[SemanticEdit] = []
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
