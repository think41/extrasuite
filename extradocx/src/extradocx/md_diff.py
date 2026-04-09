"""
Markdown AST diff algorithm.

Compares a **base** AST (produced by the DOCX parser, carrying xpaths) against
a **derived** AST (produced by parsing the user-edited markdown, no xpaths)
and emits a list of ``DiffOp`` describing the edits.

Each operation reads: "Take this node in the base AST and perform this edit."

The algorithm has two layers:

1. **Block-level alignment** — a DP (dynamic programming) sequence alignment
   that matches base blocks to derived blocks, detecting insertions, deletions,
   and modifications.  Inspired by ``extradoc/diffmerge/content_align.py``.

2. **Per-block diffing** — for each matched pair, compare the block content
   and emit the appropriate operation type (ReplaceHeading, ReplaceParagraph,
   etc.) only if content actually changed.

Public API:

    diff(base: Document, derived: Document) -> list[DiffOp]
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from extradocx.ast_nodes import (
    BlockNode,
    BlockQuote,
    BulletList,
    CodeBlock,
    Document,
    Heading,
    InlineNode,
    ListItem,
    OrderedList,
    Paragraph,
    Table,
    TextRun,
    ThematicBreak,
)
from extradocx.diff_ops import (
    DeleteBlock,
    DeleteListItem,
    DiffOp,
    InsertBlock,
    InsertListItem,
    ListItemOp,
    ReplaceBlockQuote,
    ReplaceCodeBlock,
    ReplaceHeading,
    ReplaceList,
    ReplaceListItem,
    ReplaceParagraph,
    ReplaceTable,
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def diff(base: Document, derived: Document) -> list[DiffOp]:
    """Diff two document ASTs and return a list of edit operations.

    ``base`` is the original AST (from DOCX, with xpaths).
    ``derived`` is the AST parsed from the user-edited markdown.

    Returns a list of ``DiffOp`` that, when conceptually applied to ``base``,
    would produce ``derived``.
    """
    alignment = _align_blocks(base.children, derived.children)
    return _alignment_to_ops(base.children, derived.children, alignment)


# ---------------------------------------------------------------------------
# Block alignment (DP)
# ---------------------------------------------------------------------------

# Cost constants
_PARA_COST_PER_CHAR = 2.0
_TABLE_CELL_COST = 10.0
_FIXED_COST = 20.0
_MIN_SIMILARITY = 0.3


@dataclass
class _BlockAlignment:
    """Result of aligning two block sequences."""

    matches: list[tuple[int, int]]  # (base_idx, derived_idx) pairs
    base_deletes: list[int]  # base indices with no derived match
    derived_inserts: list[int]  # derived indices with no base match


def _align_blocks(base: list[BlockNode], derived: list[BlockNode]) -> _BlockAlignment:
    """DP-based alignment of two block sequences."""
    m = len(base)
    n = len(derived)

    # dp[i][j] = min cost to align base[0..i-1] with derived[0..j-1]
    INF = math.inf
    dp = [[INF] * (n + 1) for _ in range(m + 1)]
    # choice[i][j]: 0 = match, 1 = delete base[i-1], 2 = insert derived[j-1]
    choice = [[0] * (n + 1) for _ in range(m + 1)]

    dp[0][0] = 0.0
    for i in range(1, m + 1):
        dp[i][0] = dp[i - 1][0] + _delete_cost(base[i - 1])
        choice[i][0] = 1
    for j in range(1, n + 1):
        dp[0][j] = dp[0][j - 1] + _insert_cost(derived[j - 1])
        choice[0][j] = 2

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            # Option 1: delete base[i-1]
            del_cost = dp[i - 1][j] + _delete_cost(base[i - 1])
            # Option 2: insert derived[j-1]
            ins_cost = dp[i][j - 1] + _insert_cost(derived[j - 1])
            # Option 3: match
            match_cost = INF
            if _matchable(base[i - 1], derived[j - 1]):
                match_cost = dp[i - 1][j - 1] + _edit_cost(base[i - 1], derived[j - 1])

            best = min(match_cost, del_cost, ins_cost)
            dp[i][j] = best
            if best == match_cost:
                choice[i][j] = 0
            elif best == del_cost:
                choice[i][j] = 1
            else:
                choice[i][j] = 2

    # Traceback
    matches: list[tuple[int, int]] = []
    base_deletes: list[int] = []
    derived_inserts: list[int] = []

    i, j = m, n
    while i > 0 or j > 0:
        if i > 0 and j > 0 and choice[i][j] == 0:
            matches.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif i > 0 and choice[i][j] == 1:
            base_deletes.append(i - 1)
            i -= 1
        else:
            derived_inserts.append(j - 1)
            j -= 1

    matches.reverse()
    base_deletes.reverse()
    derived_inserts.reverse()

    return _BlockAlignment(
        matches=matches,
        base_deletes=base_deletes,
        derived_inserts=derived_inserts,
    )


# ---------------------------------------------------------------------------
# Cost functions
# ---------------------------------------------------------------------------


def _block_text(block: BlockNode) -> str:
    """Extract plain text from a block for similarity comparison."""
    if isinstance(block, (Paragraph, Heading)):
        return _inlines_text(block.children)
    elif isinstance(block, CodeBlock):
        return block.code
    elif isinstance(block, (BulletList, OrderedList)):
        parts = []
        for item in block.items:
            for child in item.children:
                parts.append(_block_text(child))
        return " ".join(parts)
    elif isinstance(block, Table):
        parts = []
        for row in block.rows:
            for cell in row.cells:
                for child in cell.children:
                    parts.append(_block_text(child))
        return " ".join(parts)
    elif isinstance(block, BlockQuote):
        return " ".join(_block_text(c) for c in block.children)
    elif isinstance(block, ThematicBreak):
        return "---"
    return ""


def _inlines_text(inlines: list[InlineNode]) -> str:
    """Extract plain text from inline nodes."""
    parts = []
    for node in inlines:
        if isinstance(node, TextRun):
            parts.append(node.text)
        elif hasattr(node, "children"):
            parts.append(_inlines_text(node.children))
    return "".join(parts)


def _word_jaccard(a: str, b: str) -> float:
    """Token-level Jaccard similarity."""
    if not a and not b:
        return 1.0
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _block_kind(block: BlockNode) -> str:
    """Return a coarse kind string for matchability gating."""
    if isinstance(block, Heading):
        return "heading"
    elif isinstance(block, Paragraph):
        return "paragraph"
    elif isinstance(block, CodeBlock):
        return "code_block"
    elif isinstance(block, BulletList):
        return "bullet_list"
    elif isinstance(block, OrderedList):
        return "ordered_list"
    elif isinstance(block, Table):
        return "table"
    elif isinstance(block, BlockQuote):
        return "block_quote"
    elif isinstance(block, ThematicBreak):
        return "thematic_break"
    return "other"


def _matchable(base: BlockNode, derived: BlockNode) -> bool:
    """Can these two blocks be matched (same kind + sufficient similarity)?"""
    bk = _block_kind(base)
    dk = _block_kind(derived)

    # Headings and paragraphs can cross-match (a heading can become a paragraph
    # and vice versa) — but with a higher cost.
    text_kinds = {"heading", "paragraph"}
    if bk in text_kinds and dk in text_kinds:
        sim = _word_jaccard(_block_text(base), _block_text(derived))
        return sim >= _MIN_SIMILARITY

    if bk != dk:
        return False

    if bk == "thematic_break":
        return True

    sim = _word_jaccard(_block_text(base), _block_text(derived))
    return sim >= _MIN_SIMILARITY


def _delete_cost(block: BlockNode) -> float:
    text = _block_text(block)
    if isinstance(block, Table):
        n_cells = sum(len(r.cells) for r in block.rows)
        return n_cells * _TABLE_CELL_COST
    if isinstance(block, ThematicBreak):
        return _FIXED_COST
    return max(len(text) * _PARA_COST_PER_CHAR, _FIXED_COST)


def _insert_cost(block: BlockNode) -> float:
    return _delete_cost(block)


def _edit_cost(base: BlockNode, derived: BlockNode) -> float:
    """Estimated cost of transforming base into derived."""
    text_b = _block_text(base)
    text_d = _block_text(derived)

    # Exact match — zero cost
    if text_b == text_d:
        # But check structural properties too
        if isinstance(base, Heading) and isinstance(derived, Heading):
            if base.level != derived.level:
                return 1.0  # tiny cost for level change
            return 0.0
        if type(base) is type(derived):
            return 0.0
        return 1.0  # kind change but same text (e.g. paragraph ↔ heading)

    sim = _word_jaccard(text_b, text_d)
    max_len = max(len(text_b), len(text_d), 1)
    return (1.0 - sim) * max_len


# ---------------------------------------------------------------------------
# Convert alignment to operations
# ---------------------------------------------------------------------------


def _alignment_to_ops(
    base: list[BlockNode],
    derived: list[BlockNode],
    alignment: _BlockAlignment,
) -> list[DiffOp]:
    """Convert a block alignment into a list of DiffOp."""
    ops: list[DiffOp] = []

    # Deletions (iterate in reverse index order so positions are stable)
    for bi in reversed(alignment.base_deletes):
        ops.append(
            DeleteBlock(
                base_index=bi,
                base_xpath=getattr(base[bi], "xpath", ""),
            )
        )

    # Insertions
    for di in alignment.derived_inserts:
        ops.append(InsertBlock(position=di, block=derived[di]))

    # Matched pairs — emit replace ops only if content changed
    for bi, di in alignment.matches:
        block_ops = _diff_matched_blocks(base[bi], derived[di], bi)
        ops.extend(block_ops)

    # Sort: deletes first (reversed), then replaces/inserts by position
    # This gives a predictable ordering for consumers.
    def _sort_key(op: DiffOp) -> tuple[int, int]:
        if isinstance(op, DeleteBlock):
            return (0, op.base_index)
        if isinstance(op, InsertBlock):
            return (2, op.position)
        # Replace ops
        idx = getattr(op, "base_index", 0)
        return (1, idx)

    ops.sort(key=_sort_key)
    return ops


def _diff_matched_blocks(base: BlockNode, derived: BlockNode, base_index: int) -> list[DiffOp]:
    """Diff a matched pair of blocks. Returns empty list if identical."""
    # Heading
    if isinstance(base, Heading) and isinstance(derived, Heading):
        return _diff_heading(base, derived, base_index)

    # Heading ↔ Paragraph (kind change)
    if isinstance(base, Heading) and isinstance(derived, Paragraph):
        new_text = _inlines_text(derived.children)
        old_text = _inlines_text(base.children)
        if old_text == new_text:
            return []
        return [
            ReplaceParagraph(
                base_index=base_index,
                base_xpath=base.xpath,
                old_text=old_text,
                new_text=new_text,
                new_children=derived.children,
            )
        ]

    if isinstance(base, Paragraph) and isinstance(derived, Heading):
        old_text = _inlines_text(base.children)
        new_text = _inlines_text(derived.children)
        return [
            ReplaceHeading(
                base_index=base_index,
                base_xpath=base.xpath,
                old_level=0,
                new_level=derived.level,
                old_text=old_text,
                new_text=new_text,
                new_children=derived.children,
            )
        ]

    # Paragraph
    if isinstance(base, Paragraph) and isinstance(derived, Paragraph):
        return _diff_paragraph(base, derived, base_index)

    # CodeBlock
    if isinstance(base, CodeBlock) and isinstance(derived, CodeBlock):
        return _diff_codeblock(base, derived, base_index)

    # Table
    if isinstance(base, Table) and isinstance(derived, Table):
        return _diff_table(base, derived, base_index)

    # Lists
    if isinstance(base, BulletList) and isinstance(derived, BulletList):
        return _diff_list(base.items, derived.items, base_index, base.xpath, "bullet")
    if isinstance(base, OrderedList) and isinstance(derived, OrderedList):
        return _diff_list(base.items, derived.items, base_index, base.xpath, "ordered")

    # BlockQuote
    if isinstance(base, BlockQuote) and isinstance(derived, BlockQuote):
        return _diff_blockquote(base, derived, base_index)

    # ThematicBreak — no content to diff
    if isinstance(base, ThematicBreak) and isinstance(derived, ThematicBreak):
        return []

    return []


# ---------------------------------------------------------------------------
# Per-block diff helpers
# ---------------------------------------------------------------------------


def _diff_heading(base: Heading, derived: Heading, base_index: int) -> list[DiffOp]:
    old_text = _inlines_text(base.children)
    new_text = _inlines_text(derived.children)
    if base.level == derived.level and old_text == new_text:
        # Check inline formatting too
        if _inlines_equal(base.children, derived.children):
            return []
    return [
        ReplaceHeading(
            base_index=base_index,
            base_xpath=base.xpath,
            old_level=base.level,
            new_level=derived.level,
            old_text=old_text,
            new_text=new_text,
            new_children=derived.children,
        )
    ]


def _diff_paragraph(base: Paragraph, derived: Paragraph, base_index: int) -> list[DiffOp]:
    old_text = _inlines_text(base.children)
    new_text = _inlines_text(derived.children)
    if old_text == new_text and _inlines_equal(base.children, derived.children):
        return []
    return [
        ReplaceParagraph(
            base_index=base_index,
            base_xpath=base.xpath,
            old_text=old_text,
            new_text=new_text,
            new_children=derived.children,
        )
    ]


def _diff_codeblock(base: CodeBlock, derived: CodeBlock, base_index: int) -> list[DiffOp]:
    if base.code == derived.code and base.language == derived.language:
        return []
    return [
        ReplaceCodeBlock(
            base_index=base_index,
            base_xpath=base.xpath,
            old_code=base.code,
            new_code=derived.code,
            old_language=base.language,
            new_language=derived.language,
        )
    ]


def _diff_table(base: Table, derived: Table, base_index: int) -> list[DiffOp]:
    # Compare cell text grids
    def _cell_grid(tbl: Table) -> list[list[str]]:
        grid = []
        for row in tbl.rows:
            row_texts = []
            for cell in row.cells:
                text = " ".join(_block_text(c) for c in cell.children)
                row_texts.append(text)
            grid.append(row_texts)
        return grid

    bg = _cell_grid(base)
    dg = _cell_grid(derived)
    if bg == dg:
        return []

    return [
        ReplaceTable(
            base_index=base_index,
            base_xpath=base.xpath,
            new_rows=derived.rows,
        )
    ]


def _diff_list(
    base_items: list[ListItem],
    derived_items: list[ListItem],
    base_index: int,
    base_xpath: str,
    list_type: str,
) -> list[DiffOp]:
    """Diff two lists using item-level DP alignment."""
    alignment = _align_list_items(base_items, derived_items)

    # Check if anything actually changed
    if (
        not alignment.base_deletes
        and not alignment.derived_inserts
        and all(
            _item_text(base_items[bi]) == _item_text(derived_items[di])
            for bi, di in alignment.matches
        )
    ):
        return []

    item_ops: list[ListItemOp] = []

    for bi in reversed(alignment.base_deletes):
        item_ops.append(
            DeleteListItem(
                base_item_index=bi,
                base_xpath=base_items[bi].xpath,
            )
        )

    for di in alignment.derived_inserts:
        item_ops.append(InsertListItem(position=di, item=derived_items[di]))

    for bi, di in alignment.matches:
        old_text = _item_text(base_items[bi])
        new_text = _item_text(derived_items[di])
        if old_text != new_text:
            item_ops.append(
                ReplaceListItem(
                    base_item_index=bi,
                    base_xpath=base_items[bi].xpath,
                    old_text=old_text,
                    new_text=new_text,
                )
            )

    if not item_ops:
        return []

    return [
        ReplaceList(
            base_index=base_index,
            base_xpath=base_xpath,
            list_type=list_type,
            item_ops=item_ops,
            new_items=derived_items,
        )
    ]


def _item_text(item: ListItem) -> str:
    parts = []
    for child in item.children:
        parts.append(_block_text(child))
    return " ".join(parts)


def _align_list_items(base: list[ListItem], derived: list[ListItem]) -> _BlockAlignment:
    """Simple DP alignment for list items (same algorithm as blocks)."""
    m = len(base)
    n = len(derived)
    INF = math.inf

    dp = [[INF] * (n + 1) for _ in range(m + 1)]
    choice = [[0] * (n + 1) for _ in range(m + 1)]
    dp[0][0] = 0.0

    for i in range(1, m + 1):
        dp[i][0] = dp[i - 1][0] + _FIXED_COST
        choice[i][0] = 1
    for j in range(1, n + 1):
        dp[0][j] = dp[0][j - 1] + _FIXED_COST
        choice[0][j] = 2

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            bt = _item_text(base[i - 1])
            dt = _item_text(derived[j - 1])
            sim = _word_jaccard(bt, dt)

            del_cost = dp[i - 1][j] + _FIXED_COST
            ins_cost = dp[i][j - 1] + _FIXED_COST
            match_cost = INF
            if sim >= _MIN_SIMILARITY:
                if bt == dt:
                    match_cost = dp[i - 1][j - 1]
                else:
                    match_cost = dp[i - 1][j - 1] + (1.0 - sim) * max(len(bt), len(dt), 1)

            best = min(match_cost, del_cost, ins_cost)
            dp[i][j] = best
            if best == match_cost:
                choice[i][j] = 0
            elif best == del_cost:
                choice[i][j] = 1
            else:
                choice[i][j] = 2

    matches: list[tuple[int, int]] = []
    base_deletes: list[int] = []
    derived_inserts: list[int] = []
    i, j = m, n
    while i > 0 or j > 0:
        if i > 0 and j > 0 and choice[i][j] == 0:
            matches.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif i > 0 and choice[i][j] == 1:
            base_deletes.append(i - 1)
            i -= 1
        else:
            derived_inserts.append(j - 1)
            j -= 1

    matches.reverse()
    base_deletes.reverse()
    derived_inserts.reverse()

    return _BlockAlignment(
        matches=matches,
        base_deletes=base_deletes,
        derived_inserts=derived_inserts,
    )


def _diff_blockquote(base: BlockQuote, derived: BlockQuote, base_index: int) -> list[DiffOp]:
    """Recursively diff block quote contents."""
    inner_alignment = _align_blocks(base.children, derived.children)
    inner_ops = _alignment_to_ops(base.children, derived.children, inner_alignment)
    if not inner_ops:
        return []
    return [
        ReplaceBlockQuote(
            base_index=base_index,
            base_xpath=base.xpath,
            inner_ops=inner_ops,
        )
    ]


# ---------------------------------------------------------------------------
# Inline comparison
# ---------------------------------------------------------------------------


def _inlines_equal(a: list[InlineNode], b: list[InlineNode]) -> bool:
    """Check if two inline node lists are structurally equal (ignoring xpath)."""
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if type(x) is not type(y):
            return False
        if isinstance(x, TextRun) and isinstance(y, TextRun):
            if (
                x.text != y.text
                or x.bold != y.bold
                or x.italic != y.italic
                or x.underline != y.underline
                or x.strikethrough != y.strikethrough
                or x.code != y.code
                or x.superscript != y.superscript
                or x.subscript != y.subscript
            ):
                return False
        elif hasattr(x, "children") and hasattr(y, "children"):
            if not _inlines_equal(x.children, y.children):
                return False
    return True
