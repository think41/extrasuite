"""Content alignment algorithm for reconcile_v2.

This module implements a DP-based alignment algorithm that determines how to
reconcile two Google Docs content sequences (base → desired) with minimum edit
cost, without ever deleting and reinserting identical content.

Design Principles
-----------------
- No Google API calls; pure in-memory computation.
- Standalone: does NOT import from diff.py, lower.py, or any reconciler module.
- May import from ir.py (data-only types).
- Deterministic: same input → same output.
- The output is a ``ContentAlignment`` — a set of matched pairs, unmatched
  base indices (to delete), and unmatched desired indices (to insert).

Algorithm Overview
------------------
Given two sequences ``base[0..m-1]`` and ``desired[0..n-1]``, the DP finds
the minimum-cost pairing using three transitions per cell:

    dp[i][j] = min cost to reconcile base[0..i-1] with desired[0..j-1]

    Match(i,j):  dp[i-1][j-1] + edit_cost(base[i-1], desired[j-1])
                 only when matchable(base[i-1], desired[j-1])
    Delete(i):   dp[i-1][j] + delete_penalty(base[i-1])
    Insert(j):   dp[i][j-1] + insert_penalty(desired[j-1])

Terminal constraint: the last element of each sequence is always matched
(never deleted/inserted), because:
1. The Google Docs API rejects deletion of the terminal paragraph.
2. Editing in place preserves comments and formatting on the final element.

The terminal match is enforced by pre-matching the two terminal elements and
running the main DP on ``base[:-1]`` / ``desired[:-1]``.

Cost Model
----------
Higher penalty → the algorithm prefers to match rather than delete+insert.
- Characters carry a per-char penalty (PARA_PENALTY_PER_CHAR).
- Non-text inline objects (images, footnote refs) carry a flat penalty each.
- Tables carry a per-cell penalty.
- Structural elements (SectionBreak, PageBreak, TOC) carry a fixed penalty.
- The terminal element of each sequence is protected with INFINITE_PENALTY.

``edit_cost`` estimates the cost of transforming a matched base element into
the desired element.  For paragraphs, it is proportional to textual
dissimilarity.  For tables, it uses ``table_similarity`` from table_diff.py.

``matchable`` gates whether two elements can be matched at all:
- Must be the same broad kind (paragraph, list, table, structural).
- Paragraphs must share at least MIN_PARA_MATCH_SIMILARITY token-Jaccard.
- Tables must have non-zero similarity.
- Lists must be the same kind (BULLETED/NUMBERED) OR have similarity > threshold.
- Structural singletons (PageBreak, SectionBreak, TOC) always match their kind.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from extradoc.api_types._generated import (
        Paragraph,
        StructuralElement,
        Table,
    )

# ---------------------------------------------------------------------------
# Tunable constants (all in one place)
# ---------------------------------------------------------------------------

PARA_PENALTY_PER_CHAR: float = 2.0
"""Cost per character of text when a paragraph is deleted or inserted."""

PARA_INLINE_ELEMENT_PENALTY: float = 50.0
"""Additional cost per non-text inline element (image, footnote ref, etc.)."""

TABLE_CELL_PENALTY: float = 10.0
"""Cost per cell when a table is deleted or inserted."""

FIXED_STRUCTURAL_PENALTY: float = 20.0
"""Cost for deleting/inserting a structural element (PageBreak, SectionBreak, TOC)."""

MIN_PARA_MATCH_SIMILARITY: float = 0.3
"""Minimum token-Jaccard similarity for two paragraphs to be matchable."""

MIN_LIST_MATCH_SIMILARITY: float = 0.3
"""Minimum item-text similarity for two lists of different kinds to be matchable."""

INFINITE_PENALTY: float = math.inf
"""Penalty applied to the terminal element so it is never deleted/inserted."""


# ---------------------------------------------------------------------------
# ContentNode: simplified view of a document content element
# ---------------------------------------------------------------------------


class NodeKind:
    """String constants for broad element kinds used by the alignment algorithm."""

    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    PAGE_BREAK = "page_break"
    SECTION_BREAK = "section_break"
    TOC = "toc"
    OPAQUE = "opaque"


@dataclass
class ContentNode:
    """Simplified view of one content element for alignment purposes.

    Wraps the original element (BlockIR or raw JSON dict) so callers can
    recover the original from the alignment result.

    Parameters
    ----------
    kind:
        One of the ``NodeKind`` constants.
    text:
        Concatenated plain text (paragraphs and lists).  Empty for tables
        and structural elements.
    num_cells:
        For tables: total number of cells.  0 for non-tables.
    inline_element_count:
        Count of non-text inline objects (images, footnote refs, etc.).
    list_kind:
        For lists: the kind string (e.g. ``"BULLETED"`` or ``"NUMBERED"``).
        ``None`` for non-lists.
    table_cell_texts:
        For tables: flat list of cell text strings (used for similarity).
        Empty for non-tables.
    is_terminal:
        Set by the caller to mark the last element of the sequence.  The
        algorithm never deletes or inserts a terminal element.
    original:
        The original element (IR object or raw JSON dict).
    """

    kind: str
    text: str = ""
    num_cells: int = 0
    inline_element_count: int = 0
    list_kind: str | None = None
    table_cell_texts: list[str] = field(default_factory=list)
    is_terminal: bool = False
    original: StructuralElement | object = None


# ---------------------------------------------------------------------------
# Building ContentNode from raw Google Docs API JSON
# ---------------------------------------------------------------------------


def _extract_para_text(para: Paragraph) -> str:
    """Return concatenated text from a Paragraph model."""
    return "".join(
        (e.text_run.content if e.text_run and e.text_run.content else "")
        for e in (para.elements or [])
    )


def _count_para_inline_objects(para: Paragraph) -> int:
    """Count non-text inline elements in a Paragraph model."""
    return sum(
        1
        for e in (para.elements or [])
        if e.inline_object_element is not None or e.footnote_reference is not None
    )


def _extract_table_cell_texts(table: Table) -> list[str]:
    """Extract flat list of cell texts from a Table model."""
    texts: list[str] = []
    for row in table.table_rows or []:
        for cell in row.table_cells or []:
            cell_text = ""
            for content_el in cell.content or []:
                if content_el.paragraph is not None:
                    cell_text += _extract_para_text(content_el.paragraph)
            texts.append(cell_text.rstrip("\n"))
    return texts


def content_node_from_element(
    element: StructuralElement,
    *,
    is_terminal: bool = False,
) -> ContentNode:
    """Build a ``ContentNode`` from a typed ``StructuralElement`` model.

    This is used by fixture and golden-file tests that work directly with
    API models rather than going through the full IR pipeline.
    """
    if element.paragraph is not None:
        para = element.paragraph
        text = _extract_para_text(para)
        has_bullet = para.bullet is not None
        list_id = para.bullet.list_id if has_bullet and para.bullet else None
        inline_count = _count_para_inline_objects(para)
        if has_bullet and list_id is not None:
            # Bullet paragraphs are represented as single-item lists when
            # consecutive; but here each raw element may be a bullet paragraph.
            # We treat each individually as a PARAGRAPH to keep the raw→node
            # mapping 1:1.  The list grouping is not needed for alignment.
            return ContentNode(
                kind=NodeKind.PARAGRAPH,
                text=text,
                inline_element_count=inline_count,
                is_terminal=is_terminal,
                original=element,
            )
        return ContentNode(
            kind=NodeKind.PARAGRAPH,
            text=text,
            inline_element_count=inline_count,
            is_terminal=is_terminal,
            original=element,
        )
    elif element.table is not None:
        table = element.table
        rows = table.table_rows or []
        num_cells = sum(len(row.table_cells or []) for row in rows)
        cell_texts = _extract_table_cell_texts(table)
        return ContentNode(
            kind=NodeKind.TABLE,
            num_cells=num_cells,
            table_cell_texts=cell_texts,
            is_terminal=is_terminal,
            original=element,
        )
    elif element.section_break is not None:
        return ContentNode(
            kind=NodeKind.SECTION_BREAK,
            is_terminal=is_terminal,
            original=element,
        )
    elif element.table_of_contents is not None:
        return ContentNode(
            kind=NodeKind.TOC,
            is_terminal=is_terminal,
            original=element,
        )
    else:
        return ContentNode(
            kind=NodeKind.OPAQUE,
            is_terminal=is_terminal,
            original=element,
        )


# ---------------------------------------------------------------------------
# Building ContentNode from BlockIR (for integration with reconcile_v2)
# ---------------------------------------------------------------------------


def content_node_from_ir(block: object, *, is_terminal: bool = False) -> ContentNode:
    """Build a ``ContentNode`` from a ``BlockIR`` instance."""
    from extradoc.reconcile_v2.ir import (  # noqa: PLC0415
        ListIR,
        OpaqueBlockIR,
        PageBreakIR,
        ParagraphIR,
        TableIR,
        TextSpanIR,
        TocIR,
    )

    if isinstance(block, ParagraphIR):
        text_parts: list[str] = []
        inline_count = 0
        for inline in block.inlines:
            if isinstance(inline, TextSpanIR):
                text_parts.append(inline.text)
            else:
                inline_count += 1
        text = "".join(text_parts)
        return ContentNode(
            kind=NodeKind.PARAGRAPH,
            text=text,
            inline_element_count=inline_count,
            is_terminal=is_terminal,
            original=block,
        )
    elif isinstance(block, ListIR):
        text_parts = []
        inline_count = 0
        for item in block.items:
            for inline in item.paragraph.inlines:
                if isinstance(inline, TextSpanIR):
                    text_parts.append(inline.text)
                else:
                    inline_count += 1
        text = " ".join(text_parts)
        list_kind = block.spec.kind if block.spec else None
        return ContentNode(
            kind=NodeKind.LIST,
            text=text,
            inline_element_count=inline_count,
            list_kind=list_kind,
            is_terminal=is_terminal,
            original=block,
        )
    elif isinstance(block, TableIR):
        from extradoc.reconcile_v2.table_diff import cell_text_hash  # noqa: PLC0415

        num_cells = sum(len(row.cells) for row in block.rows)
        cell_texts = [cell_text_hash(cell) for row in block.rows for cell in row.cells]
        return ContentNode(
            kind=NodeKind.TABLE,
            num_cells=num_cells,
            table_cell_texts=cell_texts,
            is_terminal=is_terminal,
            original=block,
        )
    elif isinstance(block, PageBreakIR):
        return ContentNode(
            kind=NodeKind.PAGE_BREAK,
            is_terminal=is_terminal,
            original=block,
        )
    elif isinstance(block, TocIR):
        return ContentNode(
            kind=NodeKind.TOC,
            is_terminal=is_terminal,
            original=block,
        )
    elif isinstance(block, OpaqueBlockIR):
        return ContentNode(
            kind=NodeKind.OPAQUE,
            is_terminal=is_terminal,
            original=block,
        )
    else:
        return ContentNode(
            kind=NodeKind.OPAQUE,
            is_terminal=is_terminal,
            original=block,
        )


# ---------------------------------------------------------------------------
# Text similarity (token/word Jaccard)
# ---------------------------------------------------------------------------


def text_similarity(a: str, b: str) -> float:
    """Return word-level Jaccard similarity in [0.0, 1.0].

    Identical strings → 1.0.  Both empty → 1.0 (vacuously identical).
    One empty, one not → 0.0.
    """
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    return intersection / union if union > 0 else 0.0


# ---------------------------------------------------------------------------
# Table similarity (cell-text Jaccard against base)
# ---------------------------------------------------------------------------


def _table_sim(base: ContentNode, desired: ContentNode) -> float:
    """Return similarity of two table nodes based on their cell texts.

    Computed as |intersection of cell text multiset| / |base cell count|.
    Empty base → 1.0.
    """
    if not base.table_cell_texts:
        return 1.0
    desired_set = set(desired.table_cell_texts)
    intersection = sum(1 for t in base.table_cell_texts if t in desired_set)
    return intersection / len(base.table_cell_texts)


# ---------------------------------------------------------------------------
# List similarity
# ---------------------------------------------------------------------------


def _list_sim(base: ContentNode, desired: ContentNode) -> float:
    """Return item-text Jaccard similarity for two list nodes."""
    return text_similarity(base.text, desired.text)


# ---------------------------------------------------------------------------
# matchable
# ---------------------------------------------------------------------------


def matchable(base: ContentNode, desired: ContentNode) -> bool:
    """Return True if base and desired can be aligned (same broad kind).

    Rules
    -----
    - Kinds must be identical (paragraph↔paragraph, table↔table, …).
    - Paragraphs: token Jaccard ≥ MIN_PARA_MATCH_SIMILARITY.
    - Tables: cell-text similarity > 0.
    - Lists: same list_kind, OR item-text similarity > MIN_LIST_MATCH_SIMILARITY.
    - SectionBreak, PageBreak, TOC, Opaque: always matchable with the same kind.
    """
    if base.kind != desired.kind:
        return False
    if base.kind == NodeKind.PARAGRAPH:
        return text_similarity(base.text, desired.text) >= MIN_PARA_MATCH_SIMILARITY
    if base.kind == NodeKind.TABLE:
        return _table_sim(base, desired) > 0.0
    if base.kind == NodeKind.LIST:
        if base.list_kind == desired.list_kind:
            return True
        return _list_sim(base, desired) > MIN_LIST_MATCH_SIMILARITY
    # SectionBreak, PageBreak, TOC, Opaque — always matchable with same kind
    return True


# ---------------------------------------------------------------------------
# Cost functions
# ---------------------------------------------------------------------------


def delete_penalty(node: ContentNode) -> float:
    """Cost of removing a base element without matching it to anything desired.

    The terminal element is assigned INFINITE_PENALTY so the DP never deletes it.
    """
    if node.is_terminal:
        return INFINITE_PENALTY
    if node.kind == NodeKind.PARAGRAPH:
        cost = len(node.text) * PARA_PENALTY_PER_CHAR
        cost += node.inline_element_count * PARA_INLINE_ELEMENT_PENALTY
        return cost
    if node.kind == NodeKind.LIST:
        cost = len(node.text) * PARA_PENALTY_PER_CHAR
        cost += node.inline_element_count * PARA_INLINE_ELEMENT_PENALTY
        return cost
    if node.kind == NodeKind.TABLE:
        return node.num_cells * TABLE_CELL_PENALTY
    # SectionBreak, PageBreak, TOC, Opaque
    return FIXED_STRUCTURAL_PENALTY


def insert_penalty(node: ContentNode) -> float:
    """Cost of inserting a desired element without matching it to any base element.

    The terminal element is assigned INFINITE_PENALTY so the DP never inserts it
    as a new element (it must be matched to the base terminal).
    """
    if node.is_terminal:
        return INFINITE_PENALTY
    return delete_penalty(node)  # same formula


def edit_cost(base: ContentNode, desired: ContentNode) -> float:
    """Estimated cost of transforming matched base into desired.

    Only called when matchable(base, desired) is True.
    """
    if base.kind == NodeKind.PARAGRAPH:
        sim = text_similarity(base.text, desired.text)
        max_len = max(len(base.text), len(desired.text))
        return (1.0 - sim) * max_len
    if base.kind == NodeKind.LIST:
        sim = _list_sim(base, desired)
        max_len = max(len(base.text), len(desired.text))
        return (1.0 - sim) * max_len
    if base.kind == NodeKind.TABLE:
        sim = _table_sim(base, desired)
        return (1.0 - sim) * max(base.num_cells, 1)
    # Structural elements: cost 0 if same kind (nothing to edit)
    return 0.0


# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------


@dataclass
class ContentMatch:
    """A matched pair of (base_idx, desired_idx) indices."""

    base_idx: int
    desired_idx: int


@dataclass
class ContentAlignment:
    """Result of aligning two content sequences.

    Attributes
    ----------
    matches:
        Order-preserving list of matched (base_idx, desired_idx) pairs.
        Indices reference the original sequence positions (including the
        terminal element, which is always the last match).
    base_deletes:
        Unmatched base indices (sorted ascending).
    desired_inserts:
        Unmatched desired indices (sorted ascending).
    total_cost:
        Total DP cost (for debugging and testing).
    """

    matches: list[ContentMatch]
    base_deletes: list[int]
    desired_inserts: list[int]
    total_cost: float


# ---------------------------------------------------------------------------
# Main DP alignment
# ---------------------------------------------------------------------------

_INF = math.inf


def align_content(
    base: list[ContentNode],
    desired: list[ContentNode],
) -> ContentAlignment:
    """Align two content sequences to minimise reconciliation cost.

    Parameters
    ----------
    base:
        Content nodes from the base (current) document.
    desired:
        Content nodes from the desired (target) document.

    Returns
    -------
    ContentAlignment
        Matched pairs, unmatched base indices (delete), unmatched desired
        indices (insert), and total cost.

    Notes
    -----
    Terminal handling
    ~~~~~~~~~~~~~~~~~
    The last element of each non-empty sequence is always matched.  This is
    enforced by pre-matching them and running the main DP on the prefixes
    ``base[:-1]`` and ``desired[:-1]``.

    If either sequence is empty the algorithm handles it as a degenerate case.

    Infinity handling
    ~~~~~~~~~~~~~~~~~
    When ``delete_penalty`` or ``insert_penalty`` returns ``INFINITE_PENALTY``
    (for terminal elements) the DP explicitly avoids adding to infinity.
    """
    m = len(base)
    n = len(desired)

    # ------------------------------------------------------------------
    # Degenerate cases
    # ------------------------------------------------------------------
    if m == 0 and n == 0:
        return ContentAlignment(
            matches=[], base_deletes=[], desired_inserts=[], total_cost=0.0
        )

    if m == 0:
        # Nothing in base; insert everything from desired except terminal.
        # But desired[-1] must also be matched — we have nothing to match it to.
        # Treat all desired as inserts; cost = sum of insert_penalties.
        inserts = list(range(n))
        cost = sum(insert_penalty(desired[j]) for j in inserts)
        return ContentAlignment(
            matches=[], base_deletes=[], desired_inserts=inserts, total_cost=cost
        )

    if n == 0:
        deletes = list(range(m))
        cost = sum(delete_penalty(base[i]) for i in deletes)
        return ContentAlignment(
            matches=[], base_deletes=deletes, desired_inserts=[], total_cost=cost
        )

    # ------------------------------------------------------------------
    # Pre-match terminals
    # ------------------------------------------------------------------
    # The terminals are base[m-1] and desired[n-1].
    terminal_match = ContentMatch(base_idx=m - 1, desired_idx=n - 1)

    # Run DP on prefixes base[0..m-2] and desired[0..n-2].
    prefix_base = base[: m - 1]
    prefix_desired = desired[: n - 1]

    prefix_alignment = _dp_align(prefix_base, prefix_desired)

    # Combine prefix result with terminal match.
    all_matches = [*prefix_alignment.matches, terminal_match]
    total_cost = (
        prefix_alignment.total_cost
    )  # terminal edit_cost is excluded (terminals are paired by definition)

    return ContentAlignment(
        matches=all_matches,
        base_deletes=prefix_alignment.base_deletes,
        desired_inserts=prefix_alignment.desired_inserts,
        total_cost=total_cost,
    )


def _dp_align(
    base: list[ContentNode],
    desired: list[ContentNode],
) -> ContentAlignment:
    """Run the core DP alignment on two sequences (no terminal constraint here).

    Used internally by ``align_content`` on the prefix sequences (after
    the terminal elements have been pre-matched).
    """
    m = len(base)
    n = len(desired)

    if m == 0 and n == 0:
        return ContentAlignment(
            matches=[], base_deletes=[], desired_inserts=[], total_cost=0.0
        )

    if m == 0:
        inserts = list(range(n))
        cost = sum(insert_penalty(desired[j]) for j in inserts)
        return ContentAlignment(
            matches=[], base_deletes=[], desired_inserts=inserts, total_cost=cost
        )

    if n == 0:
        deletes = list(range(m))
        cost = sum(delete_penalty(base[i]) for i in deletes)
        return ContentAlignment(
            matches=[], base_deletes=deletes, desired_inserts=[], total_cost=cost
        )

    # dp[i][j] = minimum cost to reconcile base[0..i-1] with desired[0..j-1]
    # Use flat arrays for memory efficiency.
    # Shape: (m+1) x (n+1)
    dp: list[list[float]] = [[_INF] * (n + 1) for _ in range(m + 1)]
    dp[0][0] = 0.0

    # Fill first row: insert all desired[0..j-1]
    for j in range(1, n + 1):
        pen = insert_penalty(desired[j - 1])
        if dp[0][j - 1] == _INF or pen == _INF:
            dp[0][j] = _INF
        else:
            dp[0][j] = dp[0][j - 1] + pen

    # Fill first column: delete all base[0..i-1]
    for i in range(1, m + 1):
        pen = delete_penalty(base[i - 1])
        if dp[i - 1][0] == _INF or pen == _INF:
            dp[i][0] = _INF
        else:
            dp[i][0] = dp[i - 1][0] + pen

    # Fill rest of the table
    for i in range(1, m + 1):
        b = base[i - 1]
        for j in range(1, n + 1):
            d = desired[j - 1]

            best = _INF

            # Transition 1: Delete base[i-1]
            del_pen = delete_penalty(b)
            if dp[i - 1][j] != _INF and del_pen != _INF:
                candidate = dp[i - 1][j] + del_pen
                if candidate < best:
                    best = candidate

            # Transition 2: Insert desired[j-1]
            ins_pen = insert_penalty(d)
            if dp[i][j - 1] != _INF and ins_pen != _INF:
                candidate = dp[i][j - 1] + ins_pen
                if candidate < best:
                    best = candidate

            # Transition 3: Match base[i-1] with desired[j-1]
            if matchable(b, d):
                ec = edit_cost(b, d)
                if dp[i - 1][j - 1] != _INF:
                    candidate = dp[i - 1][j - 1] + ec
                    if candidate < best:
                        best = candidate

            dp[i][j] = best

    # ------------------------------------------------------------------
    # Backtrack to recover the alignment
    # ------------------------------------------------------------------
    matches: list[ContentMatch] = []
    base_deletes: list[int] = []
    desired_inserts: list[int] = []

    i, j = m, n
    while i > 0 or j > 0:
        if i == 0:
            # Must insert all remaining desired
            desired_inserts.append(j - 1)
            j -= 1
        elif j == 0:
            # Must delete all remaining base
            base_deletes.append(i - 1)
            i -= 1
        else:
            b = base[i - 1]
            d = desired[j - 1]

            # Determine which transition was used at dp[i][j]
            current = dp[i][j]

            # Check match first (prefer match over delete/insert on tie)
            matched = False
            if matchable(b, d):
                ec = edit_cost(b, d)
                if (
                    dp[i - 1][j - 1] != _INF
                    and abs(dp[i - 1][j - 1] + ec - current) < 1e-9
                ):
                    matches.append(ContentMatch(base_idx=i - 1, desired_idx=j - 1))
                    i -= 1
                    j -= 1
                    matched = True

            if not matched:
                # Check delete vs insert; prefer delete on tie
                del_pen = delete_penalty(b)
                used_delete = False
                if (
                    dp[i - 1][j] != _INF
                    and del_pen != _INF
                    and abs(dp[i - 1][j] + del_pen - current) < 1e-9
                ):
                    base_deletes.append(i - 1)
                    i -= 1
                    used_delete = True

                if not used_delete:
                    desired_inserts.append(j - 1)
                    j -= 1

    matches.reverse()
    base_deletes.sort()
    desired_inserts.sort()

    return ContentAlignment(
        matches=matches,
        base_deletes=base_deletes,
        desired_inserts=desired_inserts,
        total_cost=dp[m][n],
    )


# ---------------------------------------------------------------------------
# Convenience: build sequences from raw Google Docs API JSON
# ---------------------------------------------------------------------------
