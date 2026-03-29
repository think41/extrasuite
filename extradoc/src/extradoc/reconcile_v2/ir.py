"""Semantic intermediate representation for the second-generation reconciler.

This models the top-level architectural decisions used by the production
reconciler. Some transport boundaries are still rejected explicitly where the
Google Docs API path is not supported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StoryKind(str, Enum):
    BODY = "BODY"
    HEADER = "HEADER"
    FOOTER = "FOOTER"
    FOOTNOTE = "FOOTNOTE"
    TABLE_CELL = "TABLE_CELL"


class PositionEdge(str, Enum):
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    INTERIOR = "INTERIOR"


@dataclass(frozen=True, slots=True)
class CapabilitySet:
    text: bool
    table: bool
    page_break: bool
    section_break: bool


BODY_CAPABILITIES = CapabilitySet(
    text=True,
    table=True,
    page_break=True,
    section_break=True,
)
HEADER_CAPABILITIES = CapabilitySet(
    text=True,
    table=True,
    page_break=False,
    section_break=False,
)
FOOTER_CAPABILITIES = CapabilitySet(
    text=True,
    table=True,
    page_break=False,
    section_break=False,
)
FOOTNOTE_CAPABILITIES = CapabilitySet(
    text=True,
    table=False,
    page_break=False,
    section_break=False,
)
TABLE_CELL_CAPABILITIES = CapabilitySet(
    text=True,
    table=False,
    page_break=False,
    section_break=False,
)


StylePayload = dict[str, Any]


@dataclass(slots=True)
class DocumentIR:
    revision_id: str | None
    tabs: list[TabIR]


@dataclass(slots=True)
class TabIR:
    id: str
    parent_tab_id: str | None
    title: str
    index: int
    icon_emoji: str | None
    style_env: StyleEnvironmentIR
    body: BodyStoryIR
    resource_graph: ResourceGraphIR
    annotations: AnnotationCatalogIR
    child_tabs: list[TabIR] = field(default_factory=list)


@dataclass(slots=True)
class BodyStoryIR:
    id: str
    kind: StoryKind
    sections: list[SectionIR]


@dataclass(slots=True)
class SectionIR:
    id: str
    style: StylePayload
    attachments: SectionAttachmentsIR
    blocks: list[BlockIR]
    eos: str = "EOS"


@dataclass(slots=True)
class SectionAttachmentsIR:
    headers: dict[str, str] = field(default_factory=dict)
    footers: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class StyleEnvironmentIR:
    document_style: StylePayload
    named_styles: StylePayload
    list_catalog: dict[str, StylePayload]


@dataclass(slots=True)
class ResourceGraphIR:
    headers: dict[str, StoryIR] = field(default_factory=dict)
    footers: dict[str, StoryIR] = field(default_factory=dict)
    footnotes: dict[str, StoryIR] = field(default_factory=dict)
    inline_objects: dict[str, StylePayload] = field(default_factory=dict)
    positioned_objects: dict[str, StylePayload] = field(default_factory=dict)


@dataclass(slots=True)
class StoryIR:
    id: str
    kind: StoryKind
    capabilities: CapabilitySet
    blocks: list[BlockIR]
    eos: str = "EOS"


@dataclass(slots=True)
class AnnotationCatalogIR:
    named_ranges: dict[str, list[AnchorRangeIR]] = field(default_factory=dict)


@dataclass(slots=True)
class AnchorRangeIR:
    start: PositionIR
    end: PositionIR
    name: str


@dataclass(slots=True)
class FlowPathIR:
    section_index: int | None
    block_index: int
    node_path: tuple[int, ...] = ()
    inline_index: int | None = None
    text_offset_utf16: int | None = None
    edge: PositionEdge = PositionEdge.INTERIOR


@dataclass(slots=True)
class PositionIR:
    story_id: str
    path: FlowPathIR


@dataclass(slots=True)
class ParagraphIR:
    role: str
    explicit_style: StylePayload
    inlines: list[InlineIR]
    eop: str = "EOP"


@dataclass(slots=True)
class ListLevelSpecIR:
    glyph_kind: str | None
    glyph_symbol: str | None
    start_number: int | None
    indent_start: StylePayload | None
    indent_first_line: StylePayload | None
    text_style: StylePayload


@dataclass(slots=True)
class ListSpecIR:
    signature: str
    kind: str
    levels: list[ListLevelSpecIR]


@dataclass(slots=True)
class ListItemIR:
    level: int
    paragraph: ParagraphIR


@dataclass(slots=True)
class ListIR:
    spec: ListSpecIR
    items: list[ListItemIR]


@dataclass(slots=True)
class CellIR:
    style: StylePayload
    row_span: int
    column_span: int
    merge_head: tuple[int, int] | None
    content: StoryIR


@dataclass(slots=True)
class RowIR:
    style: StylePayload
    cells: list[CellIR]


@dataclass(slots=True)
class TableIR:
    style: StylePayload
    pinned_header_rows: int
    column_properties: list[StylePayload]
    merge_regions: list[StylePayload]
    rows: list[RowIR]


@dataclass(slots=True)
class PageBreakIR:
    pass


@dataclass(slots=True)
class TocIR:
    style: StylePayload


@dataclass(slots=True)
class OpaqueBlockIR:
    kind: str
    payload: StylePayload


@dataclass(slots=True)
class TextSpanIR:
    text: str
    explicit_text_style: StylePayload


@dataclass(slots=True)
class FootnoteRefIR:
    ref: str


@dataclass(slots=True)
class InlineObjectRefIR:
    ref: str


@dataclass(slots=True)
class AutoTextIR:
    kind: str
    payload: StylePayload


@dataclass(slots=True)
class OpaqueInlineIR:
    kind: str
    payload: StylePayload


InlineIR = TextSpanIR | FootnoteRefIR | InlineObjectRefIR | AutoTextIR | OpaqueInlineIR
BlockIR = ParagraphIR | ListIR | TableIR | PageBreakIR | TocIR | OpaqueBlockIR
