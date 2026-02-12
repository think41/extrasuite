"""Data types for ExtraDoc v2 diff/push pipeline.

Defines all enums and dataclasses used throughout the v2 module.
No logic — just types.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

_COMMENT_REF_OPEN = re.compile(r"<comment-ref[^>]*>")
_COMMENT_REF_CLOSE = re.compile(r"</comment-ref>")

# --- Enums ---


class SegmentType(Enum):
    """Types of document segments (each has its own index space)."""

    BODY = "body"
    HEADER = "header"
    FOOTER = "footer"
    FOOTNOTE = "footnote"


class ChangeOp(Enum):
    """Change operations detected during diff."""

    UNCHANGED = "unchanged"
    ADDED = "added"
    DELETED = "deleted"
    MODIFIED = "modified"


class NodeType(Enum):
    """Types of nodes in the change tree."""

    DOCUMENT = "document"
    TAB = "tab"
    SEGMENT = "segment"
    CONTENT_BLOCK = "content_block"
    TABLE = "table"
    TABLE_ROW = "table_row"
    TABLE_COLUMN = "table_column"
    TABLE_CELL = "table_cell"


# --- Block tree types (output of parser, input to differ) ---


@dataclass
class ParagraphBlock:
    """A paragraph element in the document tree.

    Attributes:
        tag: The XML tag (p, h1, h2, ..., h6, title, subtitle, li)
        xml: The full XML string for this paragraph
        start_index: UTF-16 start index (set by indexer)
        end_index: UTF-16 end index (set by indexer)
        footnotes: Inline footnote blocks within this paragraph
    """

    tag: str
    xml: str
    start_index: int = 0
    end_index: int = 0
    footnotes: list[FootnoteRef] = field(default_factory=list)

    def content_hash(self) -> str:
        """Content hash for exact matching.

        Strips <comment-ref> tags before comparison so that adding or
        removing comment annotations doesn't cause spurious diffs.
        Comment-refs are purely annotations that don't affect text,
        styles, or indexing.
        """
        xml = _COMMENT_REF_OPEN.sub("", self.xml)
        xml = _COMMENT_REF_CLOSE.sub("", xml)
        return xml

    def structural_key(self) -> str:
        """Key for structural matching (type-based)."""
        return f"para:{self.tag}"


@dataclass
class FootnoteRef:
    """An inline footnote reference within a paragraph."""

    footnote_id: str
    xml: str
    children_xml: list[str] = field(default_factory=list)


@dataclass
class ColumnDef:
    """A column definition from <col> elements in a table."""

    col_id: str
    width: str = ""
    index: int = 0


@dataclass
class TableCellBlock:
    """A table cell."""

    cell_id: str
    col_index: int
    xml: str
    children: list[StructuralBlock] = field(default_factory=list)
    start_index: int = 0
    end_index: int = 0


@dataclass
class TableRowBlock:
    """A table row."""

    row_id: str
    row_index: int
    xml: str
    cells: list[TableCellBlock] = field(default_factory=list)
    start_index: int = 0
    end_index: int = 0


@dataclass
class TableBlock:
    """A table element in the document tree."""

    table_id: str
    xml: str
    columns: list[ColumnDef] = field(default_factory=list)
    rows: list[TableRowBlock] = field(default_factory=list)
    start_index: int = 0
    end_index: int = 0

    def content_hash(self) -> str:
        """Content hash for exact matching."""
        return self.xml

    def structural_key(self) -> str:
        """Key for structural matching — match tables by type only."""
        return "table"


@dataclass
class TocBlock:
    """A table of contents element in the document tree.

    TOCs are read-only but occupy real index space that must be tracked
    for correct index calculations.

    Attributes:
        xml: The full XML string for this TOC
        start_index: UTF-16 start index (set by indexer)
        end_index: UTF-16 end index (set by indexer)
    """

    xml: str
    start_index: int = 0
    end_index: int = 0

    def content_hash(self) -> str:
        """Content hash for exact matching."""
        return self.xml

    def structural_key(self) -> str:
        """Key for structural matching."""
        return "toc"


# Type alias for structural elements
StructuralBlock = ParagraphBlock | TableBlock | TocBlock


@dataclass
class SegmentBlock:
    """A document segment (body, header, footer, footnote).

    Each segment has its own index space.
    """

    segment_type: SegmentType
    segment_id: str
    children: list[StructuralBlock] = field(default_factory=list)
    start_index: int = 0
    end_index: int = 0


@dataclass
class TabBlock:
    """A document tab containing segments."""

    tab_id: str
    title: str
    xml: str = ""  # full <tab>...</tab> XML for add/delete
    segments: list[SegmentBlock] = field(default_factory=list)


@dataclass
class DocumentBlock:
    """Root of the block tree."""

    doc_id: str
    tabs: list[TabBlock] = field(default_factory=list)


# --- Change tree types (output of differ, input to walker) ---


@dataclass
class ChangeNode:
    """A node in the change tree.

    The change tree mirrors the document structure but only contains
    nodes with changes (or that are ancestors of changed nodes).
    """

    node_type: NodeType
    op: ChangeOp
    node_id: str = ""

    before_xml: str | None = None
    after_xml: str | None = None

    pristine_start: int = 0
    pristine_end: int = 0

    children: list[ChangeNode] = field(default_factory=list)

    # TAB-only fields
    tab_id: str | None = None
    tab_title: str | None = None

    # SEGMENT-only fields
    segment_type: SegmentType | None = None
    segment_id: str | None = None
    segment_end: int = 0

    # Set by the differ when this content block immediately precedes a
    # non-deleted table (or TOC/section-break) in document order.
    before_structural_element: bool = False

    # TABLE-only fields
    table_start: int = 0

    # ROW/COL/CELL fields
    row_index: int = 0
    col_index: int = 0


# --- Helper types ---


@dataclass(frozen=True)
class AlignedPair:
    """A pair of aligned indices from pristine and current lists.

    - (i, None) means pristine[i] was deleted
    - (None, j) means current[j] was added
    - (i, j) means pristine[i] matches current[j]
    """

    pristine_idx: int | None
    current_idx: int | None


@dataclass
class SegmentContext:
    """Context for request generation within a segment."""

    segment_id: str | None
    segment_end: int
    tab_id: str
    segment_end_consumed: bool = False
    followed_by_added_table: bool = False
    before_structural_element: bool = False
    inside_table_cell: bool = False
