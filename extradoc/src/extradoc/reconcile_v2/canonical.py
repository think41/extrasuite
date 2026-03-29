"""Canonicalization helpers for the confidence-sprint semantic IR."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING

from extradoc.reconcile_v2.ir import ListIR, ParagraphIR, StoryKind, TableIR, TextSpanIR
from extradoc.reconcile_v2.parse import parse_document

if TYPE_CHECKING:
    from extradoc.api_types._generated import Document
    from extradoc.reconcile_v2.ir import (
        AnnotationCatalogIR,
        BlockIR,
        DocumentIR,
        PositionIR,
        StoryIR,
    )


def canonicalize_document(document: Document) -> DocumentIR:
    """Parse and canonicalize a transport document."""
    return canonicalize_document_ir(parse_document(document))


def canonicalize_document_ir(document: DocumentIR) -> DocumentIR:
    """Return a deep-copied canonical IR with transport carrier blocks removed."""
    canonical = copy.deepcopy(document)
    for tab in canonical.tabs:
        for section_index, section in enumerate(tab.body.sections):
            keep_mask = _transport_block_keep_mask(section.blocks)
            section.blocks = [block for block, keep in zip(section.blocks, keep_mask, strict=True) if keep]
            _remap_body_named_range_positions(
                annotations=tab.annotations,
                story_id=f"{tab.id}:body",
                section_index=section_index,
                keep_mask=keep_mask,
            )
        for story in tab.resource_graph.headers.values():
            story.blocks = _strip_transport_carrier_paragraphs(story.blocks)
        for story in tab.resource_graph.footers.values():
            story.blocks = _strip_transport_carrier_paragraphs(story.blocks)
        for story in tab.resource_graph.footnotes.values():
            story.blocks = _strip_transport_carrier_paragraphs(story.blocks)
            _strip_footnote_carrier_space(story)
        for story in _iter_table_cell_stories(tab.body.sections):
            story.blocks = _strip_transport_carrier_paragraphs(story.blocks)
    return canonical


def canonical_signature(document: DocumentIR) -> CanonicalDocumentSignature:
    """Return a comparison-friendly semantic signature."""
    canonical = canonicalize_document_ir(document)
    return CanonicalDocumentSignature(
        tabs=tuple(CanonicalTabSignature.from_tab(tab) for tab in canonical.tabs)
    )


def _strip_transport_carrier_paragraphs(blocks: list[BlockIR]) -> list[BlockIR]:
    keep_mask = _transport_block_keep_mask(blocks)
    return [block for block, keep in zip(blocks, keep_mask, strict=True) if keep]


def _transport_block_keep_mask(blocks: list[BlockIR]) -> list[bool]:
    keep_mask = [True] * len(blocks)
    for index, block in enumerate(blocks):
        if not _is_transport_carrier_paragraph(block):
            continue
        prev_is_table = index > 0 and isinstance(blocks[index - 1], TableIR)
        next_is_table = index + 1 < len(blocks) and isinstance(blocks[index + 1], TableIR)
        if prev_is_table or next_is_table:
            keep_mask[index] = False
    for index in range(len(blocks) - 1, -1, -1):
        if not keep_mask[index] or not _is_transport_carrier_paragraph(blocks[index]):
            break
        keep_mask[index] = False
    return keep_mask


def _is_transport_carrier_paragraph(block: BlockIR) -> bool:
    return isinstance(block, ParagraphIR) and block.role == "NORMAL_TEXT" and not block.inlines


def _remap_body_named_range_positions(
    *,
    annotations: AnnotationCatalogIR,
    story_id: str,
    section_index: int,
    keep_mask: list[bool],
) -> None:
    for ranges in annotations.named_ranges.values():
        for anchor in ranges:
            _remap_body_position(anchor.start, story_id=story_id, section_index=section_index, keep_mask=keep_mask)
            _remap_body_position(anchor.end, story_id=story_id, section_index=section_index, keep_mask=keep_mask)


def _remap_body_position(
    position: PositionIR,
    *,
    story_id: str,
    section_index: int,
    keep_mask: list[bool],
) -> None:
    if position.story_id != story_id or position.path.section_index != section_index:
        return
    original_index = position.path.block_index
    if position.path.edge.value == "BEFORE":
        position.path.block_index = sum(1 for keep in keep_mask[:original_index] if keep)
        return
    position.path.block_index = max(sum(1 for keep in keep_mask[: original_index + 1] if keep) - 1, 0)


def _iter_table_cell_stories(sections: list[object]) -> list[StoryIR]:
    stories: list[StoryIR] = []
    for section in sections:
        for block in section.blocks:
            stories.extend(_iter_table_cell_stories_from_block(block))
    return stories


def _iter_table_cell_stories_from_block(block: BlockIR) -> list[StoryIR]:
    if isinstance(block, ListIR):
        return []
    if not isinstance(block, TableIR):
        return []
    stories: list[StoryIR] = []
    for row in block.rows:
        for cell in row.cells:
            stories.append(cell.content)
            for nested_block in cell.content.blocks:
                stories.extend(_iter_table_cell_stories_from_block(nested_block))
    return stories


def _strip_footnote_carrier_space(story: StoryIR) -> None:
    if story.kind != StoryKind.FOOTNOTE or not story.blocks:
        return
    last_block = story.blocks[-1]
    if not isinstance(last_block, ParagraphIR):
        return
    if not last_block.inlines or not isinstance(last_block.inlines[-1], TextSpanIR):
        return
    last_span = last_block.inlines[-1]
    if not last_span.text.endswith(" ") or last_span.text == " ":
        return
    last_span.text = last_span.text[:-1]


@dataclass(frozen=True, slots=True)
class CanonicalParagraphSignature:
    role: str
    text: str

    @classmethod
    def from_paragraph(cls, paragraph: ParagraphIR) -> CanonicalParagraphSignature:
        return cls(
            role=paragraph.role,
            text="".join(
                inline.text
                for inline in paragraph.inlines
                if isinstance(inline, TextSpanIR)
            ),
        )


@dataclass(frozen=True, slots=True)
class CanonicalListSignature:
    kind: str
    items: tuple[tuple[int, str], ...]

    @classmethod
    def from_list(cls, block: ListIR) -> CanonicalListSignature:
        return cls(
            kind=block.spec.kind,
            items=tuple(
                (item.level, CanonicalParagraphSignature.from_paragraph(item.paragraph).text)
                for item in block.items
            ),
        )


@dataclass(frozen=True, slots=True)
class CanonicalSectionSignature:
    attachments: tuple[tuple[str, str], ...]
    blocks: tuple[object, ...]

    @classmethod
    def from_section(cls, section: object) -> CanonicalSectionSignature:
        attachments = tuple(
            sorted(section.attachments.headers.items())
            + sorted(section.attachments.footers.items())
        )
        blocks: list[object] = []
        for block in section.blocks:
            if isinstance(block, ParagraphIR):
                blocks.append(CanonicalParagraphSignature.from_paragraph(block))
            elif isinstance(block, ListIR):
                blocks.append(CanonicalListSignature.from_list(block))
            else:
                blocks.append(type(block).__name__)
        return cls(attachments=attachments, blocks=tuple(blocks))


@dataclass(frozen=True, slots=True)
class CanonicalTabSignature:
    id: str
    body: tuple[CanonicalSectionSignature, ...]

    @classmethod
    def from_tab(cls, tab: object) -> CanonicalTabSignature:
        return cls(
            id=tab.id,
            body=tuple(CanonicalSectionSignature.from_section(section) for section in tab.body.sections),
        )


@dataclass(frozen=True, slots=True)
class CanonicalDocumentSignature:
    tabs: tuple[CanonicalTabSignature, ...]
