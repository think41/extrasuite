"""Content alignment algorithm for reconcile_v3.

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

Table-flanking invariant
~~~~~~~~~~~~~~~~~~~~~~~~
In every Google Docs segment, a table element is always immediately preceded
AND immediately followed by a paragraph.

This invariant is structural — it is enforced by the Google Docs API itself:

- ``InsertTableRequest`` inserts a new table at a location AND inserts a
  bracketing paragraph immediately before the table (if needed) and a
  required trailing paragraph immediately after the table (always). See
  ``docs/googledocs/api/InsertTableRequest.md``.
- ``DeleteContentRangeRequest`` rejects any range whose deletion would leave
  a table without its bracketing paragraphs. See
  ``docs/googledocs/api/DeleteContentRangeRequest.md`` and
  ``docs/googledocs/rules-behavior.md``.
- Empirical investigation confirms the bracketing paragraphs are physically
  present and indexed in every base document. See
  ``docs/insert-table-investigation.md``.

Consequences for content alignment
..................................
When a table is present at the same *semantic* position in both ``base`` and
``desired``, the paragraphs immediately before and after it in each sequence
must, by the invariant, refer to the *same* structural slots — even when
their textual content is completely rewritten. The raw-text DP cost model
does not know about this invariant: if a flank paragraph's text is
completely replaced (Jaccard = 0), the DP may prefer to delete the old flank
and insert a new one rather than match them. Doing so produces

1. spurious delete+insert churn that defeats in-place editing, and
2. (more seriously) invalid edit plans: deleting a table-adjacent paragraph
   is rejected by the API because it would violate the flanking invariant.

Post-DP flank pinning
.....................
After the main DP runs on the stripped prefix, ``_pin_table_flanks``
post-processes the alignment to enforce the invariant:

*For every matched table pair* ``(bi, di)``, *pin* ``(bi-1, di-1)`` *and*
``(bi+1, di+1)`` *if both positions are in range and both elements are
paragraphs.*

Conflicts between pins (where two table pairs disagree on the same base or
desired index) are resolved by dropping the lower-similarity table pair.
After anchors are finalised, the sub-ranges (gaps) between consecutive
anchors are re-DP'd to avoid any match that would straddle a pin.

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

MIN_TABLE_MATCH_SIMILARITY: float = 0.25
"""Minimum fuzzy cell-text similarity for two tables to be matchable.

Set slightly below the paragraph threshold (0.3) because table similarity
is diluted across multiple cells.  Must be high enough to avoid matching
completely unrelated tables (e.g. callout with fully rewritten text) yet
low enough to match tables where cells share structural markers like
footnote reference placeholders."""

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
    """Return concatenated text from a Paragraph model.

    Non-textRun elements (footnote refs, rich links, inline objects, etc.)
    are represented as type-specific placeholder tokens so that paragraphs
    sharing the same non-text elements have higher word-level Jaccard
    similarity and are more likely to be matched by the DP aligner.
    """
    parts: list[str] = []
    for e in para.elements or []:
        if e.text_run and e.text_run.content:
            parts.append(e.text_run.content)
        elif e.footnote_reference is not None:
            parts.append(" FOOTNOTE_REF ")
        elif e.rich_link is not None:
            parts.append(" RICH_LINK ")
        elif e.inline_object_element is not None:
            parts.append(" INLINE_OBJ ")
        elif e.person is not None:
            parts.append(" PERSON ")
        elif e.auto_text is not None:
            parts.append(" AUTO_TEXT ")
        elif e.equation is not None:
            parts.append(" EQUATION ")
        elif e.page_break is not None:
            parts.append(" PAGE_BREAK ")
        elif e.column_break is not None:
            parts.append(" COLUMN_BREAK ")
        elif e.horizontal_rule is not None:
            parts.append(" HORIZONTAL_RULE ")
    return "".join(parts)


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


def shared_affix_ratio(a: str, b: str) -> float:
    """Return (shared_prefix + shared_suffix) / max(len(a), len(b)).

    This is a character-level "near-identical" heuristic used to catch
    paragraph pairs that differ by a small localised edit (e.g. insert a
    space inside a CamelCase word, replace a date, append a trailing
    clause). Such pairs can score 0.0 on word-level Jaccard yet still be
    obviously the same paragraph.

    Unrelated strings return ~0.0 because they share no common prefix or
    suffix.
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # Common prefix length
    prefix = 0
    max_prefix = min(len(a), len(b))
    while prefix < max_prefix and a[prefix] == b[prefix]:
        prefix += 1
    # Common suffix length (bounded so prefix + suffix <= min length)
    suffix = 0
    max_suffix = min(len(a), len(b)) - prefix
    while suffix < max_suffix and a[len(a) - 1 - suffix] == b[len(b) - 1 - suffix]:
        suffix += 1
    return (prefix + suffix) / max(len(a), len(b))


#: Minimum shared-prefix+suffix ratio (character-level) above which two
#: paragraphs are considered "near-identical" even if their word-level
#: Jaccard similarity falls below ``MIN_PARA_MATCH_SIMILARITY``. Set high
#: enough that unrelated paragraphs never trigger it.
MIN_PARA_NEAR_IDENTICAL_RATIO: float = 0.4


# ---------------------------------------------------------------------------
# Table similarity (cell-text Jaccard against base)
# ---------------------------------------------------------------------------


def _table_sim(base: ContentNode, desired: ContentNode) -> float:
    """Return similarity of two table nodes based on their cell texts.

    For each base cell, we find the best word-Jaccard match among desired
    cells (consumed greedily).  The score is the average of per-cell best
    similarities, so minor text edits inside a cell still yield a high
    overall score and allow the tables to be matched.

    Empty base → 1.0.
    """
    if not base.table_cell_texts:
        return 1.0

    # Build a pool of desired cell texts (allow each desired cell to be
    # consumed at most once via greedy best-match).
    remaining_desired = list(desired.table_cell_texts)
    total_sim = 0.0

    for b_text in base.table_cell_texts:
        best_sim = 0.0
        best_idx = -1
        for idx, d_text in enumerate(remaining_desired):
            sim = text_similarity(b_text, d_text)
            if sim > best_sim:
                best_sim = sim
                best_idx = idx
        total_sim += best_sim
        if best_idx >= 0:
            remaining_desired.pop(best_idx)

    return total_sim / len(base.table_cell_texts)


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
    - Tables: fuzzy cell-text similarity ≥ MIN_TABLE_MATCH_SIMILARITY.
    - Lists: same list_kind, OR item-text similarity > MIN_LIST_MATCH_SIMILARITY.
    - SectionBreak, PageBreak, TOC, Opaque: always matchable with the same kind.
    """
    if base.kind != desired.kind:
        return False
    if base.kind == NodeKind.PARAGRAPH:
        if text_similarity(base.text, desired.text) >= MIN_PARA_MATCH_SIMILARITY:
            return True
        # Fallback: near-identical paragraphs (one-character edits in the
        # middle of a CamelCase word, appended trailing clauses, etc.) score
        # 0 on word-Jaccard but share a long common prefix+suffix. Accept
        # them so the reconciler emits a surgical text diff instead of
        # delete+insert.
        return (
            shared_affix_ratio(base.text, desired.text) >= MIN_PARA_NEAR_IDENTICAL_RATIO
        )
    if base.kind == NodeKind.TABLE:
        return _table_sim(base, desired) >= MIN_TABLE_MATCH_SIMILARITY
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
        # For near-identical paragraphs whose word-Jaccard is artificially
        # low (CamelCase edits, appended clauses), use the shared
        # prefix+suffix ratio as the similarity estimate instead. This
        # keeps edit_cost below delete_penalty + insert_penalty so the DP
        # actually picks the match.
        affix_sim = shared_affix_ratio(base.text, desired.text)
        if affix_sim > sim:
            sim = affix_sim
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


# ---------------------------------------------------------------------------
# API-uncreatable element kinds
# ---------------------------------------------------------------------------

#: Element kinds that cannot be created via the Google Docs batchUpdate API.
#: If such an element exists in base, it must never appear in base_deletes —
#: the user could not have removed and re-added it.
_UNCREATABLE_KINDS: frozenset[str] = frozenset(
    [NodeKind.TOC, NodeKind.OPAQUE, NodeKind.SECTION_BREAK]
)


def _pre_pin_stable_anchors(
    base: list[ContentNode],
    desired: list[ContentNode],
) -> list[tuple[int, int]]:
    """Collect stable anchors to establish before running the DP.

    Returns a sorted, non-conflicting list of ``(base_idx, desired_idx)``
    anchor pairs. Two sources are used:

    1. **Exact-text matches** — paragraphs/lists whose text content appears
       exactly once in base AND exactly once in desired (unambiguous).
       Paragraphs must also share the same kind.

    2. **API-uncreatable elements** — ``TOC``, ``OPAQUE``, and
       ``SectionBreak`` nodes that appear in both base and desired in
       positional order.  If a TOC exists in base but NOT in desired it is
       intentionally omitted from the anchor list (it will be handled as a
       forced carry-through by the caller, not a deletion).

    The returned list is sorted by ``base_idx`` and is guaranteed to be
    monotonic in ``desired_idx`` as well (no conflicts).
    """
    # -----------------------------------------------------------------------
    # Source 1: Exact-text matches (unambiguous — appears exactly once each
    # side).  Only text-bearing kinds (PARAGRAPH, LIST) participate.
    # -----------------------------------------------------------------------
    base_text_counts: dict[str, int] = {}
    desired_text_counts: dict[str, int] = {}

    for node in base:
        if node.kind in (NodeKind.PARAGRAPH, NodeKind.LIST) and node.text.strip():
            key = f"{node.kind}:{node.text}"
            base_text_counts[key] = base_text_counts.get(key, 0) + 1

    for node in desired:
        if node.kind in (NodeKind.PARAGRAPH, NodeKind.LIST) and node.text.strip():
            key = f"{node.kind}:{node.text}"
            desired_text_counts[key] = desired_text_counts.get(key, 0) + 1

    # Index of each unambiguous text in base and desired.
    base_text_to_idx: dict[str, int] = {}
    for i, node in enumerate(base):
        if node.kind in (NodeKind.PARAGRAPH, NodeKind.LIST) and node.text.strip():
            key = f"{node.kind}:{node.text}"
            if (
                base_text_counts.get(key, 0) == 1
                and desired_text_counts.get(key, 0) == 1
            ):
                base_text_to_idx[key] = i

    desired_text_to_idx: dict[str, int] = {}
    for j, node in enumerate(desired):
        if node.kind in (NodeKind.PARAGRAPH, NodeKind.LIST) and node.text.strip():
            key = f"{node.kind}:{node.text}"
            if (
                base_text_counts.get(key, 0) == 1
                and desired_text_counts.get(key, 0) == 1
            ):
                desired_text_to_idx[key] = j

    exact_anchors: list[tuple[int, int]] = []
    for key, bi in base_text_to_idx.items():
        di = desired_text_to_idx.get(key)
        if di is not None:
            exact_anchors.append((bi, di))

    # -----------------------------------------------------------------------
    # Source 2: API-uncreatable elements — match them in positional order
    # (first TOC in base ↔ first TOC in desired, etc.).
    # -----------------------------------------------------------------------
    uncreatable_anchors: list[tuple[int, int]] = []

    for kind in _UNCREATABLE_KINDS:
        base_indices = [i for i, n in enumerate(base) if n.kind == kind]
        desired_indices = [j for j, n in enumerate(desired) if n.kind == kind]
        # Match positionally; extras on either side are left unmatched.
        for bi, di in zip(base_indices, desired_indices, strict=False):
            uncreatable_anchors.append((bi, di))

    # -----------------------------------------------------------------------
    # Merge and de-conflict: keep only anchors that form a strictly monotonic
    # sequence in both indices (no two anchors share a base_idx or desired_idx,
    # and sorted by base_idx is also sorted by desired_idx).
    # -----------------------------------------------------------------------
    all_candidates = sorted(
        set(exact_anchors + uncreatable_anchors), key=lambda p: (p[0], p[1])
    )

    # Greedy monotonic-subsequence filter (patience-sort variant): keep the
    # longest prefix that is strictly increasing in both axes.
    # Simple O(n²) approach — anchor lists are tiny in practice.
    result: list[tuple[int, int]] = []
    used_base: set[int] = set()
    used_desired: set[int] = set()

    for bi, di in all_candidates:
        if bi in used_base or di in used_desired:
            continue
        # Ensure monotonicity: new anchor must be > all current anchors in
        # BOTH dimensions.
        if result:
            last_bi, last_di = result[-1]
            if bi <= last_bi or di <= last_di:
                # Conflict with last anchor — skip this candidate.
                continue
        result.append((bi, di))
        used_base.add(bi)
        used_desired.add(di)

    return result


def _apply_anchors_to_alignment(
    anchors: list[tuple[int, int]],
    base: list[ContentNode],
    desired: list[ContentNode],
) -> ContentAlignment:
    """Run the DP within each gap defined by the given anchors and merge.

    This is the same gap-based approach used by ``_pin_table_flanks``.

    Parameters
    ----------
    anchors:
        Sorted, monotonic ``(base_idx, desired_idx)`` pairs to use as fixed
        match points.  Must be strictly increasing in both dimensions.
    base, desired:
        The prefix sequences (terminals already stripped by the caller).
    """
    m = len(base)
    n = len(desired)

    # Boundaries: (-1,-1), anchors..., (m, n)
    boundaries: list[tuple[int, int]] = [(-1, -1), *anchors, (m, n)]

    final_matches: list[ContentMatch] = []
    total_cost = 0.0

    # Add anchor matches themselves.
    for bi, di in anchors:
        final_matches.append(ContentMatch(base_idx=bi, desired_idx=di))
        total_cost += edit_cost(base[bi], desired[di])

    anchor_base_set = {bi for bi, _ in anchors}
    anchor_desired_set = {di for _, di in anchors}

    for k in range(len(boundaries) - 1):
        b_lo, d_lo = boundaries[k]
        b_hi, d_hi = boundaries[k + 1]

        gap_base_indices = [
            i for i in range(b_lo + 1, b_hi) if i not in anchor_base_set
        ]
        gap_desired_indices = [
            j for j in range(d_lo + 1, d_hi) if j not in anchor_desired_set
        ]

        if not gap_base_indices and not gap_desired_indices:
            continue

        sub_base = [base[i] for i in gap_base_indices]
        sub_desired = [desired[j] for j in gap_desired_indices]
        sub_alignment = _dp_align(sub_base, sub_desired)

        for sub_m in sub_alignment.matches:
            final_matches.append(
                ContentMatch(
                    base_idx=gap_base_indices[sub_m.base_idx],
                    desired_idx=gap_desired_indices[sub_m.desired_idx],
                )
            )
        total_cost += sub_alignment.total_cost

    final_matches.sort(key=lambda m: (m.base_idx, m.desired_idx))
    matched_base = {m.base_idx for m in final_matches}
    matched_desired = {m.desired_idx for m in final_matches}
    base_deletes = sorted(i for i in range(m) if i not in matched_base)
    desired_inserts = sorted(j for j in range(n) if j not in matched_desired)

    # Add delete/insert penalties to cost.
    for i in base_deletes:
        total_cost += delete_penalty(base[i])
    for j in desired_inserts:
        total_cost += insert_penalty(desired[j])

    return ContentAlignment(
        matches=final_matches,
        base_deletes=base_deletes,
        desired_inserts=desired_inserts,
        total_cost=total_cost,
    )


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

    # Pre-pin stable anchors before the DP: exact-text matches and
    # API-uncreatable elements (TOC, OPAQUE, SectionBreak).
    pre_pins = _pre_pin_stable_anchors(prefix_base, prefix_desired)

    if pre_pins:
        prefix_alignment = _apply_anchors_to_alignment(
            pre_pins, prefix_base, prefix_desired
        )
    else:
        prefix_alignment = _dp_align(prefix_base, prefix_desired)

    # Table-flank pinning: force the paragraphs immediately adjacent to each
    # matched table pair to be matched (see module docstring).
    prefix_alignment = _pin_table_flanks(prefix_alignment, prefix_base, prefix_desired)

    # Positional fallback: promote unmatched same-kind elements in 1:1 gaps
    prefix_alignment = _positional_fallback(
        prefix_alignment, prefix_base, prefix_desired
    )

    # Remove API-uncreatable elements from base_deletes.  They cannot be
    # re-created by the reconciler so they must never be scheduled for
    # deletion — the caller (apply_ops / reconciler) will carry them through.
    filtered_base_deletes = [
        i
        for i in prefix_alignment.base_deletes
        if prefix_base[i].kind not in _UNCREATABLE_KINDS
    ]
    filtered_cost = prefix_alignment.total_cost
    if len(filtered_base_deletes) < len(prefix_alignment.base_deletes):
        # Subtract the delete penalties that we're dropping.
        removed = set(prefix_alignment.base_deletes) - set(filtered_base_deletes)
        for i in removed:
            filtered_cost -= delete_penalty(prefix_base[i])

    # Combine prefix result with terminal match.
    all_matches = [*prefix_alignment.matches, terminal_match]
    total_cost = filtered_cost  # terminal edit_cost excluded (always paired)

    return ContentAlignment(
        matches=all_matches,
        base_deletes=filtered_base_deletes,
        desired_inserts=prefix_alignment.desired_inserts,
        total_cost=total_cost,
    )


def _tables_share_content(a: ContentNode, b: ContentNode) -> bool:
    """Return True if two table nodes share at least one non-empty cell text.

    Used by the positional fallback to allow matching tables with large size
    differentials (e.g., 5x5→1x1) where _table_sim falls below the threshold
    but the smaller table's content is a subset of the larger table's.
    """
    a_texts = {t.strip() for t in a.table_cell_texts if t.strip()}
    b_texts = {t.strip() for t in b.table_cell_texts if t.strip()}
    if not a_texts or not b_texts:
        # If either table has no non-empty cells, allow match (both empty)
        return not a_texts and not b_texts
    return bool(a_texts & b_texts)


def _pin_table_flanks(
    alignment: ContentAlignment,
    base: list[ContentNode],
    desired: list[ContentNode],
) -> ContentAlignment:
    """Post-process a DP alignment to enforce the table-flanking invariant.

    Google Docs guarantees that every table is immediately preceded AND
    immediately followed by a paragraph. When a matched table pair
    ``(bi, di)`` sits between paragraphs on both sides, the pre- and
    post-flank paragraphs in the two sequences must refer to the *same*
    structural slots — even when their textual content is completely
    rewritten. The DP's text-similarity cost model doesn't know this, so
    it may delete+insert rewritten flanks, producing an invalid edit plan
    (the API rejects deletion of a table-adjacent paragraph) and
    unnecessary churn.

    This function:

    1. Collects the existing table pairs from the DP alignment.
    2. For each pair, forces pins on the pre- and post-flank paragraphs
       (when in range and both paragraphs).
    3. Resolves conflicts (pins disagreeing on the same base or desired
       index) by dropping the lower-similarity table pair.
    4. Ensures anchors are monotonic in both base and desired indices.
    5. Re-runs the DP on each gap between consecutive anchors when an
       existing match would straddle an anchor; otherwise keeps the
       existing gap matches.
    6. Rebuilds the final alignment (matches + deletes + inserts + cost).
    """
    # Fast path: no tables at all.
    table_pairs_all: list[tuple[int, int]] = [
        (m.base_idx, m.desired_idx)
        for m in alignment.matches
        if base[m.base_idx].kind == NodeKind.TABLE
        and desired[m.desired_idx].kind == NodeKind.TABLE
    ]
    if not table_pairs_all:
        return alignment

    m_len = len(base)
    n_len = len(desired)

    # Build similarity map for tie-breaking when pins conflict.
    def _pair_sim(bi: int, di: int) -> float:
        return _table_sim(base[bi], desired[di])

    # Iteratively resolve conflicts by dropping the lowest-similarity table pair.
    active_pairs: list[tuple[int, int]] = list(table_pairs_all)
    # Bounded by O(#tables) iterations.
    for _ in range(len(table_pairs_all) + 1):
        # Compute anchors = table_pairs union flank_pins.
        anchors_set: set[tuple[int, int]] = set()
        for bi, di in active_pairs:
            anchors_set.add((bi, di))
            # Pre-flank
            if (
                bi - 1 >= 0
                and di - 1 >= 0
                and base[bi - 1].kind == NodeKind.PARAGRAPH
                and desired[di - 1].kind == NodeKind.PARAGRAPH
            ):
                anchors_set.add((bi - 1, di - 1))
            # Post-flank
            if (
                bi + 1 < m_len
                and di + 1 < n_len
                and base[bi + 1].kind == NodeKind.PARAGRAPH
                and desired[di + 1].kind == NodeKind.PARAGRAPH
            ):
                anchors_set.add((bi + 1, di + 1))

        # Detect conflicts: same bi with different di, or same di with different bi.
        by_base: dict[int, set[int]] = {}
        by_desired: dict[int, set[int]] = {}
        for bi, di in anchors_set:
            by_base.setdefault(bi, set()).add(di)
            by_desired.setdefault(di, set()).add(bi)

        conflict_pairs: set[tuple[int, int]] = set()
        for bi, dis in by_base.items():
            if len(dis) > 1:
                for di in dis:
                    conflict_pairs.add((bi, di))
        for di, bis in by_desired.items():
            if len(bis) > 1:
                for bi in bis:
                    conflict_pairs.add((bi, di))

        if not conflict_pairs:
            # Also need to verify monotonicity (sorted by bi also sorted by di).
            sorted_anchors = sorted(anchors_set, key=lambda p: (p[0], p[1]))
            monotonic = True
            for k in range(len(sorted_anchors) - 1):
                if sorted_anchors[k][1] >= sorted_anchors[k + 1][1]:
                    monotonic = False
                    break
            if monotonic:
                break
            # Not monotonic: drop lowest-similarity table pair and retry.

        # Identify which active_pairs contributed to a conflict (directly or
        # via their flanks). Drop the one with the lowest similarity.
        pair_contributes: dict[tuple[int, int], bool] = dict.fromkeys(
            active_pairs, False
        )
        for bi, di in active_pairs:
            cand_anchors = {(bi, di)}
            if (
                bi - 1 >= 0
                and di - 1 >= 0
                and base[bi - 1].kind == NodeKind.PARAGRAPH
                and desired[di - 1].kind == NodeKind.PARAGRAPH
            ):
                cand_anchors.add((bi - 1, di - 1))
            if (
                bi + 1 < m_len
                and di + 1 < n_len
                and base[bi + 1].kind == NodeKind.PARAGRAPH
                and desired[di + 1].kind == NodeKind.PARAGRAPH
            ):
                cand_anchors.add((bi + 1, di + 1))
            if cand_anchors & conflict_pairs:
                pair_contributes[(bi, di)] = True

        # If no conflict (only monotonicity failure), mark ALL active pairs as
        # candidates for dropping.
        if not any(pair_contributes.values()):
            for p in active_pairs:
                pair_contributes[p] = True

        # Drop the contributing pair with the lowest similarity.
        candidates = [p for p, v in pair_contributes.items() if v]
        candidates.sort(key=lambda p: (_pair_sim(*p), p[0], p[1]))
        to_drop = candidates[0]
        active_pairs = [p for p in active_pairs if p != to_drop]

        if not active_pairs:
            # No table pairs to pin — nothing to do.
            return alignment
    else:
        # Failsafe: if we couldn't converge, fall through with current pairs.
        pass

    if not active_pairs:
        return alignment

    # Final anchors, sorted by base index (monotonic in both axes by construction).
    anchors_set = set()
    for bi, di in active_pairs:
        anchors_set.add((bi, di))
        if (
            bi - 1 >= 0
            and di - 1 >= 0
            and base[bi - 1].kind == NodeKind.PARAGRAPH
            and desired[di - 1].kind == NodeKind.PARAGRAPH
        ):
            anchors_set.add((bi - 1, di - 1))
        if (
            bi + 1 < m_len
            and di + 1 < n_len
            and base[bi + 1].kind == NodeKind.PARAGRAPH
            and desired[di + 1].kind == NodeKind.PARAGRAPH
        ):
            anchors_set.add((bi + 1, di + 1))

    sorted_anchors = sorted(anchors_set, key=lambda p: (p[0], p[1]))

    # Check whether any existing match straddles a new anchor boundary. If so,
    # we need to re-DP the affected gaps.
    existing_matches_by_base: dict[int, int] = {
        m.base_idx: m.desired_idx for m in alignment.matches
    }

    # Build gap boundaries: (-1, -1), anchors..., (m_len, n_len)
    boundaries: list[tuple[int, int]] = [
        (-1, -1),
        *sorted_anchors,
        (m_len, n_len),
    ]

    final_matches: list[ContentMatch] = []
    for bi, di in sorted_anchors:
        final_matches.append(ContentMatch(base_idx=bi, desired_idx=di))

    anchor_base_set = {bi for bi, _ in sorted_anchors}
    anchor_desired_set = {di for _, di in sorted_anchors}

    for k in range(len(boundaries) - 1):
        b_lo, d_lo = boundaries[k]
        b_hi, d_hi = boundaries[k + 1]

        gap_base_indices = list(range(b_lo + 1, b_hi))
        gap_desired_indices = list(range(d_lo + 1, d_hi))

        if not gap_base_indices and not gap_desired_indices:
            continue

        # Check if the original gap's matches are still consistent with this gap.
        # A match is consistent if both endpoints fall inside this gap.
        gap_needs_redp = False
        for gi_base in gap_base_indices:
            existing_di = existing_matches_by_base.get(gi_base)
            if existing_di is None:
                continue
            # existing_di must be within (d_lo, d_hi) for consistency.
            if not (d_lo < existing_di < d_hi):
                gap_needs_redp = True
                break
        if not gap_needs_redp:
            # Also check from desired side: a desired in this gap matched to
            # a base outside this gap?
            existing_matches_by_desired: dict[int, int] = {
                m.desired_idx: m.base_idx for m in alignment.matches
            }
            for gi_desired in gap_desired_indices:
                existing_bi = existing_matches_by_desired.get(gi_desired)
                if existing_bi is None:
                    continue
                if not (b_lo < existing_bi < b_hi):
                    gap_needs_redp = True
                    break

        if gap_needs_redp:
            # Re-DP this gap.
            sub_base = [base[i] for i in gap_base_indices]
            sub_desired = [desired[j] for j in gap_desired_indices]
            sub_alignment = _dp_align(sub_base, sub_desired)
            for sub_m in sub_alignment.matches:
                final_matches.append(
                    ContentMatch(
                        base_idx=gap_base_indices[sub_m.base_idx],
                        desired_idx=gap_desired_indices[sub_m.desired_idx],
                    )
                )
        else:
            # Keep original gap matches that are fully inside this gap, and
            # whose endpoints are not pinned to anchors.
            for m_orig in alignment.matches:
                bi = m_orig.base_idx
                di = m_orig.desired_idx
                if bi in anchor_base_set or di in anchor_desired_set:
                    continue
                if b_lo < bi < b_hi and d_lo < di < d_hi:
                    final_matches.append(ContentMatch(base_idx=bi, desired_idx=di))

    final_matches.sort(key=lambda m: (m.base_idx, m.desired_idx))
    matched_base = {m.base_idx for m in final_matches}
    matched_desired = {m.desired_idx for m in final_matches}
    new_base_deletes = sorted(i for i in range(m_len) if i not in matched_base)
    new_desired_inserts = sorted(j for j in range(n_len) if j not in matched_desired)

    # Recompute total cost.
    new_cost = 0.0
    for m_final in final_matches:
        new_cost += edit_cost(base[m_final.base_idx], desired[m_final.desired_idx])
    for i in new_base_deletes:
        new_cost += delete_penalty(base[i])
    for j in new_desired_inserts:
        new_cost += insert_penalty(desired[j])

    return ContentAlignment(
        matches=final_matches,
        base_deletes=new_base_deletes,
        desired_inserts=new_desired_inserts,
        total_cost=new_cost,
    )


def _positional_fallback(
    alignment: ContentAlignment,
    base: list[ContentNode],
    desired: list[ContentNode],
) -> ContentAlignment:
    """Promote unmatched elements to matches when they are the sole same-kind
    pair in a gap between consecutive matched anchors.

    This handles the "complete text rewrite" case: when a paragraph's text is
    100% different (Jaccard = 0), the DP can't match it. But if it's the only
    unmatched paragraph in a gap (structurally pinned), it should be matched
    for in-place surgical editing rather than delete + reinsert.

    A "gap" is the region between two consecutive matched pairs (or the
    start/end of the sequence and the first/last match). Within each gap,
    if there is exactly one unmatched base element and one unmatched desired
    element of the same kind, promote them to a match.
    """
    if not alignment.base_deletes or not alignment.desired_inserts:
        return alignment

    deleted_set = set(alignment.base_deletes)
    inserted_set = set(alignment.desired_inserts)

    # Build sorted list of match anchors as (base_idx, desired_idx)
    anchors = [(m.base_idx, m.desired_idx) for m in alignment.matches]

    # Add sentinel boundaries: (-1, -1) before and (len, len) after
    boundaries = [(-1, -1), *anchors, (len(base), len(desired))]

    new_matches: list[ContentMatch] = []

    for k in range(len(boundaries) - 1):
        b_lo, d_lo = boundaries[k]
        b_hi, d_hi = boundaries[k + 1]

        # Unmatched base indices in this gap
        gap_base = [i for i in range(b_lo + 1, b_hi) if i in deleted_set]
        # Unmatched desired indices in this gap
        gap_desired = [j for j in range(d_lo + 1, d_hi) if j in inserted_set]

        # Only promote when there's exactly 1 unmatched on each side and same kind.
        # Paragraphs: always promote (handles complete text rewrites).
        # Tables: promote only when they share at least some cell content,
        # so large contractions (5x5→1x1) are matched for structural ops
        # rather than delete+reinsert, while completely unrelated tables
        # (e.g., callout with fully rewritten text) are not matched.
        if len(gap_base) == 1 and len(gap_desired) == 1:
            bi = gap_base[0]
            di = gap_desired[0]
            if base[bi].kind == desired[di].kind:
                if base[bi].kind == NodeKind.PARAGRAPH:
                    new_matches.append(ContentMatch(base_idx=bi, desired_idx=di))
                elif base[bi].kind == NodeKind.TABLE and _tables_share_content(
                    base[bi], desired[di]
                ):
                    # For tables, require that the smaller table's cells are
                    # a subset of the larger table's cells (at least one
                    # non-empty cell text in common).
                    new_matches.append(ContentMatch(base_idx=bi, desired_idx=di))

    if not new_matches:
        return alignment

    # Merge new matches into the alignment
    promoted_base = {m.base_idx for m in new_matches}
    promoted_desired = {m.desired_idx for m in new_matches}

    all_matches = sorted(
        [*alignment.matches, *new_matches],
        key=lambda m: (m.base_idx, m.desired_idx),
    )
    new_base_deletes = sorted(
        i for i in alignment.base_deletes if i not in promoted_base
    )
    new_desired_inserts = sorted(
        j for j in alignment.desired_inserts if j not in promoted_desired
    )

    return ContentAlignment(
        matches=all_matches,
        base_deletes=new_base_deletes,
        desired_inserts=new_desired_inserts,
        total_cost=alignment.total_cost,  # approximate — cost doesn't change much
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
