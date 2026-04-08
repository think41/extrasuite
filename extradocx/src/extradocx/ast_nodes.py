"""
AST node definitions for the DOCX → GFM Markdown AST.

Design principles:
- Every node carries an `xpath` field that points back to the originating
  element in word/document.xml (or word/numbering.xml, word/styles.xml).
- Text content is always represented as `TextRun` leaf nodes, never bare
  strings.  This preserves run-level formatting (bold, italic, …) and
  traceability.
- The shape of the tree is GFM-centric, not OOXML-centric.  Heading levels,
  lists, tables, etc. map to their GFM equivalents.

Serialization:
  - JSON  — full fidelity (use `node_to_dict`)
  - Markdown — lossy but human-readable (use serializers.to_markdown)

Inspired by Pandoc's Haskell AST (Block / Inline split) but extended with
XPath pointers and text-run granularity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union


# ---------------------------------------------------------------------------
# Inline nodes
# ---------------------------------------------------------------------------


@dataclass
class TextRun:
    """A single OOXML run (<w:r>) turned into a leaf inline node.

    Formatting flags are read from <w:rPr> on the run (or inherited from the
    paragraph / character style).  All formatting is *resolved* — i.e. the
    effective value after style inheritance is applied.
    """

    text: str
    xpath: str  # XPath to the <w:r> element in document.xml
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    code: bool = False  # True when the run uses a monospace / code font
    superscript: bool = False
    subscript: bool = False

    def to_dict(self) -> dict:
        d: dict = {"type": "text_run", "text": self.text, "xpath": self.xpath}
        if self.bold:
            d["bold"] = True
        if self.italic:
            d["italic"] = True
        if self.underline:
            d["underline"] = True
        if self.strikethrough:
            d["strikethrough"] = True
        if self.code:
            d["code"] = True
        if self.superscript:
            d["superscript"] = True
        if self.subscript:
            d["subscript"] = True
        return d


@dataclass
class Link:
    """Hyperlink (<w:hyperlink>) containing inline children."""

    href: str
    children: list[InlineNode] = field(default_factory=list)
    title: str = ""
    xpath: str = ""

    def to_dict(self) -> dict:
        return {
            "type": "link",
            "href": self.href,
            "title": self.title,
            "xpath": self.xpath,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class Image:
    """Inline image (<w:drawing> or <w:pict>)."""

    alt: str
    src: str  # rId resolved to a filename / URL when possible
    xpath: str = ""

    def to_dict(self) -> dict:
        return {"type": "image", "alt": self.alt, "src": self.src, "xpath": self.xpath}


@dataclass
class LineBreak:
    """Explicit line break (<w:br w:type='textWrapping'>)."""

    xpath: str = ""

    def to_dict(self) -> dict:
        return {"type": "line_break", "xpath": self.xpath}


@dataclass
class SoftBreak:
    """Soft (rendered) break — used for <w:br> without an explicit type."""

    xpath: str = ""

    def to_dict(self) -> dict:
        return {"type": "soft_break", "xpath": self.xpath}


# Union of all inline node types
InlineNode = Union[TextRun, Link, Image, LineBreak, SoftBreak]


# ---------------------------------------------------------------------------
# Block nodes
# ---------------------------------------------------------------------------


@dataclass
class Paragraph:
    """A body paragraph (<w:p>) with no heading style."""

    children: list[InlineNode] = field(default_factory=list)
    xpath: str = ""
    # Preserved style name from the source (e.g. "Normal", "Quote")
    style_id: str = ""

    def to_dict(self) -> dict:
        return {
            "type": "paragraph",
            "style_id": self.style_id,
            "xpath": self.xpath,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class Heading:
    """A paragraph with a heading style, mapped to GFM h1–h6."""

    level: int  # 1–6
    children: list[InlineNode] = field(default_factory=list)
    xpath: str = ""
    style_id: str = ""

    def to_dict(self) -> dict:
        return {
            "type": "heading",
            "level": self.level,
            "style_id": self.style_id,
            "xpath": self.xpath,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class CodeBlock:
    """A preformatted / code paragraph."""

    code: str
    language: str = ""
    xpath: str = ""

    def to_dict(self) -> dict:
        return {
            "type": "code_block",
            "language": self.language,
            "code": self.code,
            "xpath": self.xpath,
        }


@dataclass
class BlockQuote:
    """A block quote.  DOCX doesn't have a native equivalent; mapped from
    style names like 'Quote', 'Intense Quote', 'Block Text'."""

    children: list[BlockNode] = field(default_factory=list)
    xpath: str = ""

    def to_dict(self) -> dict:
        return {
            "type": "block_quote",
            "xpath": self.xpath,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class ListItem:
    """A single list item.  May contain nested blocks (continuation paragraphs
    and sub-lists are represented as children)."""

    children: list[BlockNode] = field(default_factory=list)
    xpath: str = ""
    # The depth at which this item appears (0 = top level)
    depth: int = 0

    def to_dict(self) -> dict:
        return {
            "type": "list_item",
            "depth": self.depth,
            "xpath": self.xpath,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class BulletList:
    """An unordered list."""

    items: list[ListItem] = field(default_factory=list)
    xpath: str = ""

    def to_dict(self) -> dict:
        return {
            "type": "bullet_list",
            "xpath": self.xpath,
            "items": [i.to_dict() for i in self.items],
        }


@dataclass
class OrderedList:
    """An ordered list."""

    items: list[ListItem] = field(default_factory=list)
    start: int = 1
    xpath: str = ""

    def to_dict(self) -> dict:
        return {
            "type": "ordered_list",
            "start": self.start,
            "xpath": self.xpath,
            "items": [i.to_dict() for i in self.items],
        }


@dataclass
class TableCell:
    """A single table cell (<w:tc>)."""

    children: list[BlockNode] = field(default_factory=list)
    xpath: str = ""
    colspan: int = 1
    rowspan: int = 1
    is_header: bool = False

    def to_dict(self) -> dict:
        return {
            "type": "table_cell",
            "is_header": self.is_header,
            "colspan": self.colspan,
            "rowspan": self.rowspan,
            "xpath": self.xpath,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class TableRow:
    """A table row (<w:tr>)."""

    cells: list[TableCell] = field(default_factory=list)
    xpath: str = ""
    is_header: bool = False

    def to_dict(self) -> dict:
        return {
            "type": "table_row",
            "is_header": self.is_header,
            "xpath": self.xpath,
            "cells": [c.to_dict() for c in self.cells],
        }


@dataclass
class Table:
    """A table (<w:tbl>)."""

    rows: list[TableRow] = field(default_factory=list)
    xpath: str = ""

    def to_dict(self) -> dict:
        return {
            "type": "table",
            "xpath": self.xpath,
            "rows": [r.to_dict() for r in self.rows],
        }


@dataclass
class ThematicBreak:
    """A horizontal rule — mapped from page-break paragraphs or explicit HR
    styles."""

    xpath: str = ""

    def to_dict(self) -> dict:
        return {"type": "thematic_break", "xpath": self.xpath}


@dataclass
class RawBlock:
    """A block that couldn't be mapped to a GFM construct.  The original XML
    is preserved verbatim so it can be round-tripped."""

    xml: str
    xpath: str = ""

    def to_dict(self) -> dict:
        return {"type": "raw_block", "xml": self.xml, "xpath": self.xpath}


# Union of all block node types
BlockNode = Union[
    Paragraph,
    Heading,
    CodeBlock,
    BlockQuote,
    BulletList,
    OrderedList,
    Table,
    ThematicBreak,
    RawBlock,
]


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------


@dataclass
class Document:
    """The root of the AST.  Represents the full word/document.xml body."""

    children: list[BlockNode] = field(default_factory=list)
    # XPath to <w:body>
    xpath: str = "/w:document/w:body"
    # Source metadata
    source_path: str = ""

    def to_dict(self) -> dict:
        return {
            "type": "document",
            "source_path": self.source_path,
            "xpath": self.xpath,
            "children": [c.to_dict() for c in self.children],
        }
