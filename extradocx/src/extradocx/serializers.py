"""
AST serializers: JSON and GFM Markdown.

Two public functions:

    to_json(doc: Document) -> str
        Full-fidelity JSON serialization preserving all XPath pointers,
        formatting flags, and node types.

    to_markdown(doc: Document) -> str
        Lossy but human-readable GFM markdown.  Formatting information that
        has no GFM equivalent (e.g. underline, superscript) is silently dropped.

Both accept the root `Document` node from `ast_nodes.py`.
"""

from __future__ import annotations

import json
import re
from typing import Union

from extradocx.ast_nodes import (
    BlockNode,
    BlockQuote,
    BulletList,
    CodeBlock,
    Document,
    Heading,
    Image,
    InlineNode,
    LineBreak,
    Link,
    ListItem,
    OrderedList,
    Paragraph,
    RawBlock,
    SoftBreak,
    Table,
    TableCell,
    TableRow,
    TextRun,
    ThematicBreak,
)

# ---------------------------------------------------------------------------
# JSON serializer
# ---------------------------------------------------------------------------


def to_json(doc: Document, *, indent: int = 2) -> str:
    """Serialize the AST to a JSON string.

    The JSON is fully self-describing: every node carries a ``type`` key and
    an ``xpath`` key.  The output can be used to reconstruct the AST or to
    trace any node back to the source DOCX XML.
    """
    return json.dumps(doc.to_dict(), ensure_ascii=False, indent=indent)


# ---------------------------------------------------------------------------
# Markdown serializer
# ---------------------------------------------------------------------------

# Characters that need escaping in GFM inline context.
# Only escape chars that alter rendering mid-sentence.
# NOT escaping: - . + ! # (only meaningful at line start)
_MD_ESCAPE_RE = re.compile(r"([\\`*_{}\[\]()|])")


def _escape(text: str) -> str:
    """Escape GFM special characters in plain text (inline context)."""
    return _MD_ESCAPE_RE.sub(r"\\\1", text)


def to_markdown(doc: Document) -> str:
    """Serialize the AST to GFM markdown.

    Conventions:
      - Headings:        ATX style (``# Heading``)
      - Bold:            ``**text**``
      - Italic:          ``*text*``
      - Strikethrough:   ``~~text~~``
      - Code spans:      `` `text` ``
      - Links:           ``[text](href)``
      - Images:          ``![alt](src)``
      - Bullet lists:    ``- item``
      - Ordered lists:   ``1. item``
      - Tables:          GFM pipe tables
      - Code blocks:     fenced (``` ``` ```)
      - Thematic break:  ``---``
      - Block quote:     ``> text``
    """
    lines = _blocks_to_lines(doc.children, depth=0)
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Block rendering
# ---------------------------------------------------------------------------


def _blocks_to_lines(blocks: list[BlockNode], depth: int) -> list[str]:
    """Render a list of block nodes to a list of text lines."""
    out: list[str] = []
    for i, block in enumerate(blocks):
        block_lines = _block_to_lines(block, depth)
        if block_lines:
            if out:  # blank line between blocks
                out.append("")
            out.extend(block_lines)
    return out


def _block_to_lines(block: BlockNode, depth: int) -> list[str]:
    if isinstance(block, Heading):
        return _heading_to_lines(block)
    elif isinstance(block, Paragraph):
        return _paragraph_to_lines(block)
    elif isinstance(block, CodeBlock):
        return _codeblock_to_lines(block)
    elif isinstance(block, BlockQuote):
        return _blockquote_to_lines(block, depth)
    elif isinstance(block, BulletList):
        return _bulletlist_to_lines(block, depth)
    elif isinstance(block, OrderedList):
        return _orderedlist_to_lines(block, depth)
    elif isinstance(block, Table):
        return _table_to_lines(block)
    elif isinstance(block, ThematicBreak):
        return ["---"]
    elif isinstance(block, RawBlock):
        # Wrap in a comment so it's visible but doesn't break rendering
        return [f"<!-- raw: {block.xml[:80]} -->"]
    else:
        return []


def _heading_to_lines(h: Heading) -> list[str]:
    level = max(1, min(6, h.level))
    prefix = "#" * level
    text = _inlines_to_md(h.children)
    return [f"{prefix} {text}"]


def _paragraph_to_lines(p: Paragraph) -> list[str]:
    text = _inlines_to_md(p.children)
    if not text.strip():
        return []
    # Wrap long paragraphs at 100 chars (soft wrap, preserve words)
    return [text]


def _codeblock_to_lines(cb: CodeBlock) -> list[str]:
    fence = "```"
    lang = cb.language or ""
    lines = cb.code.split("\n")
    return [f"{fence}{lang}"] + lines + [fence]


def _blockquote_to_lines(bq: BlockQuote, depth: int) -> list[str]:
    inner = _blocks_to_lines(bq.children, depth + 1)
    return [f"> {line}" for line in inner]


def _bulletlist_to_lines(bl: BulletList, depth: int) -> list[str]:
    lines: list[str] = []
    indent = "  " * depth
    for item in bl.items:
        item_lines = _listitem_to_lines(item, depth, ordered=False, number=0)
        for i, line in enumerate(item_lines):
            if i == 0:
                lines.append(f"{indent}- {line}")
            else:
                lines.append(f"{indent}  {line}")
    return lines


def _orderedlist_to_lines(ol: OrderedList, depth: int) -> list[str]:
    lines: list[str] = []
    indent = "  " * depth
    for n, item in enumerate(ol.items, start=ol.start):
        item_lines = _listitem_to_lines(item, depth, ordered=True, number=n)
        for i, line in enumerate(item_lines):
            if i == 0:
                lines.append(f"{indent}{n}. {line}")
            else:
                lines.append(f"{indent}   {line}")
    return lines


def _listitem_to_lines(
    item: ListItem, depth: int, ordered: bool, number: int
) -> list[str]:
    """Render list item content (without the bullet/number prefix)."""
    lines: list[str] = []
    for block in item.children:
        block_lines = _block_to_lines(block, depth + 1)
        lines.extend(block_lines)
    return lines if lines else [""]


def _table_to_lines(tbl: Table) -> list[str]:
    if not tbl.rows:
        return []

    # Collect cell texts
    cell_texts: list[list[str]] = []
    for row in tbl.rows:
        row_texts: list[str] = []
        for cell in row.cells:
            # Flatten cell content to a single-line string
            text = _blocks_to_cell_text(cell.children)
            row_texts.append(text.replace("|", "\\|").replace("\n", " "))
        cell_texts.append(row_texts)

    if not cell_texts:
        return []

    # Determine column count
    col_count = max(len(row) for row in cell_texts)

    # Pad rows
    for row in cell_texts:
        while len(row) < col_count:
            row.append("")

    # Column widths
    col_widths = [
        max(len(cell_texts[r][c]) for r in range(len(cell_texts)))
        for c in range(col_count)
    ]
    col_widths = [max(w, 3) for w in col_widths]  # min width 3 for separator

    def fmt_row(cells: list[str]) -> str:
        parts = [cell.ljust(col_widths[i]) for i, cell in enumerate(cells)]
        return "| " + " | ".join(parts) + " |"

    lines: list[str] = []
    lines.append(fmt_row(cell_texts[0]))
    # Separator row
    sep = ["-" * w for w in col_widths]
    lines.append("| " + " | ".join(sep) + " |")
    for row in cell_texts[1:]:
        lines.append(fmt_row(row))

    return lines


def _blocks_to_cell_text(blocks: list[BlockNode]) -> str:
    """Flatten block content to a single string for table cells."""
    parts: list[str] = []
    for block in blocks:
        if isinstance(block, Paragraph):
            parts.append(_inlines_to_md(block.children))
        elif isinstance(block, Heading):
            parts.append(_inlines_to_md(block.children))
        elif isinstance(block, CodeBlock):
            parts.append(f"`{block.code}`")
        else:
            sub = _block_to_lines(block, 0)
            parts.extend(sub)
    return " ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Inline rendering
# ---------------------------------------------------------------------------


def _inlines_to_md(inlines: list[InlineNode]) -> str:
    """Render a list of inline nodes to a markdown string."""
    return "".join(_inline_to_md(n) for n in inlines)


def _inline_to_md(node: InlineNode) -> str:
    if isinstance(node, TextRun):
        return _textrun_to_md(node)
    elif isinstance(node, Link):
        inner = _inlines_to_md(node.children)
        href = node.href
        if node.title:
            return f'[{inner}]({href} "{node.title}")'
        return f"[{inner}]({href})"
    elif isinstance(node, Image):
        return f"![{node.alt}]({node.src})"
    elif isinstance(node, LineBreak):
        return "  \n"
    elif isinstance(node, SoftBreak):
        return "\n"
    else:
        return ""


def _textrun_to_md(run: TextRun) -> str:
    """Apply GFM markup for bold / italic / strikethrough / code."""
    text = run.text

    # Tab → spaces
    text = text.replace("\t", "    ")

    if run.code:
        # Inline code — no further escaping or wrapping
        # Use double backtick if text contains a backtick
        if "`" in text:
            return f"`` {text} ``"
        return f"`{text}`"

    text = _escape(text)

    if run.strikethrough:
        text = f"~~{text}~~"
    if run.bold and run.italic:
        text = f"***{text}***"
    elif run.bold:
        text = f"**{text}**"
    elif run.italic:
        text = f"*{text}*"

    return text
