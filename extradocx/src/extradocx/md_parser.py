"""
GFM Markdown → AST parser.

Parses GFM markdown text back into the same AST node types produced by the
DOCX parser (`ast_nodes.py`).  Nodes created here carry **no** xpath — the
xpath field is left empty because these nodes originate from markdown, not
from a DOCX XML tree.

The parser is deliberately simple: it handles the GFM subset that the
markdown serializer can produce (ATX headings, emphasis, strong, strikethrough,
code spans, fenced code blocks, bullet/ordered lists, pipe tables, block
quotes, thematic breaks, links, images).

Public API:

    parse_markdown(text: str) -> Document
"""

from __future__ import annotations

import re

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
    Table,
    TableCell,
    TableRow,
    TextRun,
    ThematicBreak,
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_markdown(text: str) -> Document:
    """Parse a GFM markdown string into a Document AST."""
    lines = text.split("\n")
    children = _parse_blocks(lines, 0, len(lines))
    return Document(children=children)


# ---------------------------------------------------------------------------
# Block-level parsing
# ---------------------------------------------------------------------------

# Patterns
_ATX_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)(?:\s+#+\s*)?$")
_THEMATIC_BREAK_RE = re.compile(r"^(?:---|\*\*\*|___)\s*$")
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})(.*)$")
_BULLET_RE = re.compile(r"^(\s*)[-*+]\s+(.*)")
_ORDERED_RE = re.compile(r"^(\s*)(\d+)\.\s+(.*)")
_BLOCKQUOTE_RE = re.compile(r"^>\s?(.*)")
_TABLE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|$")
_TABLE_ROW_RE = re.compile(r"^\|(.+)\|$")


def _parse_blocks(lines: list[str], start: int, end: int) -> list[BlockNode]:
    """Parse lines[start:end] into a list of block nodes."""
    blocks: list[BlockNode] = []
    i = start
    while i < end:
        line = lines[i]

        # Blank line — skip
        if not line.strip():
            i += 1
            continue

        # Thematic break
        if _THEMATIC_BREAK_RE.match(line):
            blocks.append(ThematicBreak())
            i += 1
            continue

        # ATX heading
        m = _ATX_HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            inlines = _parse_inlines(m.group(2))
            blocks.append(Heading(level=level, children=inlines))
            i += 1
            continue

        # Fenced code block
        m = _FENCE_RE.match(line)
        if m:
            fence_char = m.group(1)[0]
            fence_len = len(m.group(1))
            language = m.group(2).strip()
            code_lines: list[str] = []
            i += 1
            while i < end:
                close_m = re.match(rf"^{re.escape(fence_char)}{{{fence_len},}}$", lines[i])
                if close_m:
                    i += 1
                    break
                code_lines.append(lines[i])
                i += 1
            blocks.append(CodeBlock(code="\n".join(code_lines), language=language))
            continue

        # Block quote
        if _BLOCKQUOTE_RE.match(line):
            bq_lines: list[str] = []
            while i < end:
                bq_m = _BLOCKQUOTE_RE.match(lines[i])
                if bq_m:
                    bq_lines.append(bq_m.group(1))
                    i += 1
                else:
                    break
            inner = _parse_blocks(bq_lines, 0, len(bq_lines))
            blocks.append(BlockQuote(children=inner))
            continue

        # Bullet list
        if _BULLET_RE.match(line):
            items, i = _parse_list_items(lines, i, end, ordered=False)
            blocks.append(BulletList(items=items))
            continue

        # Ordered list
        if _ORDERED_RE.match(line):
            items, i = _parse_list_items(lines, i, end, ordered=True)
            # Extract start number from the first item
            m_start = _ORDERED_RE.match(line)
            start_num = int(m_start.group(2)) if m_start else 1
            blocks.append(OrderedList(items=items, start=start_num))
            continue

        # Table (pipe table)
        if _TABLE_ROW_RE.match(line):
            tbl, i = _parse_table(lines, i, end)
            if tbl is not None:
                blocks.append(tbl)
            else:
                # Not a valid table — treat as paragraph
                inlines = _parse_inlines(line)
                if inlines:
                    blocks.append(Paragraph(children=inlines))
                i += 1
            continue

        # Plain paragraph
        para_lines: list[str] = []
        while i < end and lines[i].strip():
            # Stop at block-level constructs
            if _ATX_HEADING_RE.match(lines[i]):
                break
            if _THEMATIC_BREAK_RE.match(lines[i]):
                break
            if _FENCE_RE.match(lines[i]):
                break
            if _BLOCKQUOTE_RE.match(lines[i]):
                break
            if _BULLET_RE.match(lines[i]):
                break
            if _ORDERED_RE.match(lines[i]):
                break
            if _TABLE_ROW_RE.match(lines[i]):
                break
            para_lines.append(lines[i])
            i += 1
        if para_lines:
            text_content = " ".join(para_lines)
            inlines = _parse_inlines(text_content)
            if inlines:
                blocks.append(Paragraph(children=inlines))

    return blocks


def _parse_list_items(
    lines: list[str], start: int, end: int, *, ordered: bool
) -> tuple[list[ListItem], int]:
    """Parse consecutive list items. Returns (items, next_line_index)."""
    items: list[ListItem] = []
    pattern = _ORDERED_RE if ordered else _BULLET_RE
    i = start

    while i < end:
        m = pattern.match(lines[i])
        if not m:
            break

        indent = len(m.group(1))
        depth = indent // 2
        if ordered:
            first_line_text = m.group(3)
        else:
            first_line_text = m.group(2)

        # Collect continuation lines for this item
        item_lines = [first_line_text]
        i += 1
        # Continuation lines are indented more than the bullet
        while i < end and lines[i].strip():
            # Check if next line is a new list item at same or lower depth
            next_m = pattern.match(lines[i])
            if next_m:
                break
            # Check for other bullet type starting a new list
            other_pattern = _BULLET_RE if ordered else _ORDERED_RE
            if other_pattern.match(lines[i]):
                break
            item_lines.append(lines[i].strip())
            i += 1

        # Parse the item content as blocks
        item_text = " ".join(item_lines)
        children: list[BlockNode] = []
        if item_text:
            inlines = _parse_inlines(item_text)
            if inlines:
                children.append(Paragraph(children=inlines))
        items.append(ListItem(children=children, depth=depth))

    return items, i


def _parse_table(lines: list[str], start: int, end: int) -> tuple[Table | None, int]:
    """Parse a GFM pipe table starting at `start`. Returns (Table, next_line) or (None, start)."""
    # Need at least header row + separator
    if start + 1 >= end:
        return None, start

    header_line = lines[start]
    sep_line = lines[start + 1]

    if not _TABLE_ROW_RE.match(header_line):
        return None, start
    if not _TABLE_SEP_RE.match(sep_line):
        return None, start

    rows: list[TableRow] = []

    # Parse header row
    header_cells = _split_table_row(header_line)
    header_row = TableRow(
        cells=[
            TableCell(children=[Paragraph(children=_parse_inlines(c))], is_header=True)
            for c in header_cells
        ],
        is_header=True,
    )
    rows.append(header_row)

    # Parse data rows
    i = start + 2
    while i < end:
        if not _TABLE_ROW_RE.match(lines[i]):
            break
        cell_texts = _split_table_row(lines[i])
        data_row = TableRow(
            cells=[TableCell(children=[Paragraph(children=_parse_inlines(c))]) for c in cell_texts],
        )
        rows.append(data_row)
        i += 1

    return Table(rows=rows), i


def _split_table_row(line: str) -> list[str]:
    """Split a pipe-table row into cell text strings."""
    # Strip outer pipes and split
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    # Split on unescaped pipes
    parts: list[str] = []
    current: list[str] = []
    escaped = False
    for ch in inner:
        if escaped:
            current.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
            current.append(ch)
        elif ch == "|":
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    parts.append("".join(current).strip())
    return parts


# ---------------------------------------------------------------------------
# Inline-level parsing
# ---------------------------------------------------------------------------

# Inline patterns — order matters for greedy matching
_INLINE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Image must come before link (![...] vs [...])
    ("image", re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")),
    # Link
    ("link", re.compile(r"\[([^\]]*)\]\(([^)]*?)(?:\s+\"([^\"]*)\")?\)")),
    # Code span (double backtick)
    ("code2", re.compile(r"``\s(.+?)\s``")),
    # Code span (single backtick)
    ("code1", re.compile(r"`([^`]+)`")),
    # Bold + italic
    ("bold_italic", re.compile(r"\*\*\*(.+?)\*\*\*")),
    # Bold
    ("bold", re.compile(r"\*\*(.+?)\*\*")),
    # Strikethrough
    ("strike", re.compile(r"~~(.+?)~~")),
    # Italic
    ("italic", re.compile(r"\*(.+?)\*")),
    # Hard line break (two spaces + newline) — rare in single-line context
    ("linebreak", re.compile(r"  \n")),
]


def _parse_inlines(text: str) -> list[InlineNode]:
    """Parse inline markdown into a list of InlineNode."""
    if not text:
        return []
    return _parse_inlines_recursive(text)


def _parse_inlines_recursive(text: str) -> list[InlineNode]:
    """Recursively parse inline elements, finding the earliest match."""
    if not text:
        return []

    # Find the earliest matching pattern
    best_match = None
    best_kind = ""
    best_start = len(text)

    for kind, pattern in _INLINE_PATTERNS:
        m = pattern.search(text)
        if m and m.start() < best_start:
            best_match = m
            best_kind = kind
            best_start = m.start()

    if best_match is None:
        # No inline markup — everything is plain text
        return [TextRun(text=_unescape(text), xpath="")] if text else []

    result: list[InlineNode] = []

    # Text before the match
    before = text[: best_match.start()]
    if before:
        result.append(TextRun(text=_unescape(before), xpath=""))

    # The matched element
    if best_kind == "image":
        result.append(Image(alt=best_match.group(1), src=best_match.group(2)))
    elif best_kind == "link":
        link_text = best_match.group(1)
        href = best_match.group(2)
        title = best_match.group(3) or ""
        children = _parse_inlines_recursive(link_text)
        result.append(Link(href=href, title=title, children=children))
    elif best_kind in ("code1", "code2"):
        result.append(TextRun(text=best_match.group(1), xpath="", code=True))
    elif best_kind == "bold_italic":
        inner = _unescape(best_match.group(1))
        result.append(TextRun(text=inner, xpath="", bold=True, italic=True))
    elif best_kind == "bold":
        inner = _unescape(best_match.group(1))
        result.append(TextRun(text=inner, xpath="", bold=True))
    elif best_kind == "strike":
        inner = _unescape(best_match.group(1))
        result.append(TextRun(text=inner, xpath="", strikethrough=True))
    elif best_kind == "italic":
        inner = _unescape(best_match.group(1))
        result.append(TextRun(text=inner, xpath="", italic=True))
    elif best_kind == "linebreak":
        result.append(LineBreak())

    # Text after the match
    after = text[best_match.end() :]
    if after:
        result.extend(_parse_inlines_recursive(after))

    return result


# GFM escape sequences
_UNESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()|])")


def _unescape(text: str) -> str:
    """Remove GFM backslash escapes."""
    return _UNESCAPE_RE.sub(r"\1", text)
