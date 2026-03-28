"""Canonicalization helpers for the confidence-sprint semantic IR."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING

from extradoc.reconcile_v2.ir import ListIR, ParagraphIR, TableIR, TextSpanIR
from extradoc.reconcile_v2.parse import parse_document

if TYPE_CHECKING:
    from extradoc.api_types._generated import Document
    from extradoc.reconcile_v2.ir import BlockIR, DocumentIR, StoryIR


def canonicalize_document(document: Document) -> DocumentIR:
    """Parse and canonicalize a transport document."""
    return canonicalize_document_ir(parse_document(document))


def canonicalize_document_ir(document: DocumentIR) -> DocumentIR:
    """Return a deep-copied canonical IR with transport carrier blocks removed."""
    canonical = copy.deepcopy(document)
    for tab in canonical.tabs:
        for section in tab.body.sections:
            section.blocks = _strip_transport_carrier_paragraphs(section.blocks)
        for story in tab.resource_graph.headers.values():
            story.blocks = _strip_transport_carrier_paragraphs(story.blocks)
        for story in tab.resource_graph.footers.values():
            story.blocks = _strip_transport_carrier_paragraphs(story.blocks)
        for story in tab.resource_graph.footnotes.values():
            story.blocks = _strip_transport_carrier_paragraphs(story.blocks)
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
    trimmed = list(blocks)
    while (
        len(trimmed) >= 2
        and _is_transport_carrier_paragraph(trimmed[0])
        and isinstance(trimmed[1], TableIR)
    ):
        trimmed.pop(0)
    while trimmed and _is_transport_carrier_paragraph(trimmed[-1]):
        trimmed.pop()
    return trimmed


def _is_transport_carrier_paragraph(block: BlockIR) -> bool:
    return isinstance(block, ParagraphIR) and block.role == "NORMAL_TEXT" and not block.inlines


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
