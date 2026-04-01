"""Heuristic table identity matching and structural diff for reconcile_v2.

This module implements:
- cell_text_hash: extract plain text from a CellIR for use as a hash key
- table_similarity: 0.0-1.0 measure of how similar two tables are
- match_tables: greedy bipartite match of base vs desired tables
- diff_tables: minimal sequence of row/column structural + cell content edits

Design principles:
- No Google API calls; pure in-memory computation over IR objects.
- May import from ir.py but NOT from diff.py or lower.py.
- Deterministic: same input → same output.
- Handles multi-row and multi-column changes (unlimited, unlike the existing
  _plan_table_comparison which raises UnsupportedReconcileV2Error beyond ±1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

# ---------------------------------------------------------------------------
# Re-use edit dataclasses from diff.py (data-only; no algorithmic imports).
# ---------------------------------------------------------------------------
from extradoc.reconcile_v2.diff import (
    DeleteTableColumnEdit,
    DeleteTableRowEdit,
    InsertTableColumnEdit,
    InsertTableRowEdit,
    ParagraphFragment,
    ReplaceParagraphSliceEdit,
    SemanticEdit,
)
from extradoc.reconcile_v2.ir import (
    TABLE_CELL_CAPABILITIES,
    CellIR,
    ParagraphIR,
    RowIR,
    StoryIR,
    StoryKind,
    TableIR,
    TextSpanIR,
)

# ---------------------------------------------------------------------------
# Cell text extraction
# ---------------------------------------------------------------------------


def cell_text_hash(cell: CellIR) -> str:
    """Return a normalized plain-text string for a cell's content.

    Formatting is ignored; only text content is used.  The result is suitable
    as a dictionary key for set-intersection comparisons.
    """
    parts: list[str] = []
    for block in cell.content.blocks:
        if isinstance(block, ParagraphIR):
            for inline in block.inlines:
                if isinstance(inline, TextSpanIR):
                    parts.append(inline.text)
            parts.append("\n")
    return "".join(parts).rstrip("\n")


# ---------------------------------------------------------------------------
# Similarity metric
# ---------------------------------------------------------------------------


def table_similarity(base: TableIR, desired: TableIR) -> float:
    """Return a similarity score in [0.0, 1.0].

    Computed as:  |intersection of cell text hashes| / |base cell count|

    Empty base → 1.0.
    """
    base_hashes: list[str] = [
        cell_text_hash(cell) for row in base.rows for cell in row.cells
    ]
    if not base_hashes:
        return 1.0
    desired_hashes: set[str] = {
        cell_text_hash(cell) for row in desired.rows for cell in row.cells
    }
    intersection = sum(1 for h in base_hashes if h in desired_hashes)
    return intersection / len(base_hashes)


# ---------------------------------------------------------------------------
# Table identity matching (greedy bipartite)
# ---------------------------------------------------------------------------


def match_tables(
    base_tables: list[TableIR],
    desired_tables: list[TableIR],
) -> list[tuple[int, int]]:
    """Match base tables to desired tables using greedy similarity.

    Returns a sorted list of (base_idx, desired_idx) pairs.
    """
    if not base_tables or not desired_tables:
        return []

    scores: list[tuple[float, int, int]] = []
    for b_idx, base in enumerate(base_tables):
        for d_idx, desired in enumerate(desired_tables):
            scores.append((table_similarity(base, desired), b_idx, d_idx))

    scores.sort(key=lambda t: -t[0])

    matched_base: set[int] = set()
    matched_desired: set[int] = set()
    pairs: list[tuple[int, int]] = []

    for _sim, b_idx, d_idx in scores:
        if b_idx in matched_base or d_idx in matched_desired:
            continue
        matched_base.add(b_idx)
        matched_desired.add(d_idx)
        pairs.append((b_idx, d_idx))

    pairs.sort()
    return pairs


# ---------------------------------------------------------------------------
# IR construction helpers (used by tests and internally)
# ---------------------------------------------------------------------------


def make_cell(text: str = "") -> CellIR:
    """Build a minimal CellIR containing a single paragraph with the given text."""
    paragraph = ParagraphIR(
        role="NORMAL_TEXT",
        explicit_style={},
        inlines=[TextSpanIR(text=text, explicit_text_style={})],
    )
    story = StoryIR(
        id="cell",
        kind=StoryKind.TABLE_CELL,
        capabilities=TABLE_CELL_CAPABILITIES,
        blocks=[paragraph],
    )
    return CellIR(
        style={},
        row_span=1,
        column_span=1,
        merge_head=None,
        content=story,
    )


def make_row(cell_texts: list[str]) -> RowIR:
    """Build a RowIR with cells containing the given texts."""
    return RowIR(style={}, cells=[make_cell(t) for t in cell_texts])


def make_table(rows: list[list[str]]) -> TableIR:
    """Build a TableIR from a 2-D list of cell texts."""
    return TableIR(
        style={},
        pinned_header_rows=0,
        column_properties=[{} for _ in (rows[0] if rows else [])],
        merge_regions=[],
        rows=[make_row(row) for row in rows],
    )


# ---------------------------------------------------------------------------
# Core diff algorithm
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TableDiffContext:
    """Carries the location identifiers needed to construct edit objects."""

    tab_id: str
    section_index: int
    block_index: int


# ---------------------------------------------------------------------------
# LCS helpers
# ---------------------------------------------------------------------------


def _lcs_indices(base_seq: list[str], desired_seq: list[str]) -> list[tuple[int, int]]:
    """Standard LCS returning (base_idx, desired_idx) pairs in order."""
    m, n = len(base_seq), len(desired_seq)
    dp: list[list[int]] = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if base_seq[i - 1] == desired_seq[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    pairs: list[tuple[int, int]] = []
    i, j = m, n
    while i > 0 and j > 0:
        if base_seq[i - 1] == desired_seq[j - 1]:
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs


def _fuzzy_lcs_indices(
    base_rows: list[RowIR],
    desired_rows: list[RowIR],
    *,
    match_threshold: float = 0.5,
) -> list[tuple[int, int]]:
    """Fuzzy LCS: rows match if cell-text RECALL (overlap/base_size) >= threshold.

    Recall rather than Jaccard is used so that adding columns to a row does not
    prevent it from matching its base counterpart.

    For example, base row ["a","b"] vs desired row ["a","b","X"]: overlap=2,
    base_size=2, recall=1.0 → match.

    For a single-cell change, ["a","b"] vs ["a","CHANGED"]: overlap=1,
    base_size=2, recall=0.5 → match at threshold 0.5.

    Returns (base_idx, desired_idx) pairs in order.
    """
    m = len(base_rows)
    n = len(desired_rows)

    base_sets: list[frozenset[str]] = [
        frozenset(cell_text_hash(c) for c in row.cells) for row in base_rows
    ]
    desired_sets: list[frozenset[str]] = [
        frozenset(cell_text_hash(c) for c in row.cells) for row in desired_rows
    ]

    def _recall(b_set: frozenset[str], d_set: frozenset[str]) -> float:
        """overlap / base_size (how much of the base row is preserved)."""
        if not b_set:
            # Empty base row matches any desired row (same as empty = unchanged)
            return 1.0
        return len(b_set & d_set) / len(b_set)

    # Precompute similarity matrix
    sim: list[list[float]] = [
        [_recall(base_sets[i], desired_sets[j]) for j in range(n)] for i in range(m)
    ]

    # LCS-style DP: maximize match count, break ties by total similarity
    # dp[i][j] = (match_count, total_sim) for base[:i], desired[:j]
    dp: list[list[tuple[int, float]]] = [[(0, 0.0)] * (n + 1) for _ in range(m + 1)]

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            skip_i = dp[i - 1][j]
            skip_j = dp[i][j - 1]
            best_skip = (
                skip_i if (skip_i[0], skip_i[1]) >= (skip_j[0], skip_j[1]) else skip_j
            )

            if sim[i - 1][j - 1] >= match_threshold:
                candidate = (
                    dp[i - 1][j - 1][0] + 1,
                    dp[i - 1][j - 1][1] + sim[i - 1][j - 1],
                )
                dp[i][j] = max(candidate, best_skip)
            else:
                dp[i][j] = best_skip

    # Back-trace
    pairs: list[tuple[int, int]] = []
    i, j = m, n
    while i > 0 and j > 0:
        if (
            sim[i - 1][j - 1] >= match_threshold
            and dp[i][j][0] == dp[i - 1][j - 1][0] + 1
            and abs(dp[i][j][1] - (dp[i - 1][j - 1][1] + sim[i - 1][j - 1])) < 1e-9
        ):
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        else:
            skip_i = dp[i - 1][j]
            skip_j = dp[i][j - 1]
            if (skip_i[0], skip_i[1]) >= (skip_j[0], skip_j[1]):
                i -= 1
            else:
                j -= 1
    pairs.reverse()
    return pairs


# ---------------------------------------------------------------------------
# Main diff function
# ---------------------------------------------------------------------------


def diff_tables(
    base: TableIR,
    desired: TableIR,
    *,
    ctx: TableDiffContext | None = None,
) -> list[SemanticEdit]:
    """Compute a minimal sequence of semantic edits to transform base into desired.

    Algorithm overview
    ------------------
    Phase 1 — Row alignment (fuzzy LCS):
      - Match rows via Recall similarity on cell-text sets.  A row matches if
        >= 50% of its base cells appear in the corresponding desired row.
      - Gaps in base not in LCS → DeleteTableRowEdit (highest index first).
      - Gaps in desired not in LCS → InsertTableRowEdit.

    Phase 2 — Column alignment (only when no row structural changes):
      - Column structural changes are computed ONLY when rows are stable (same
        count and all matched 1:1).  This prevents index-shift confusion when
        row insertions change the table size before column ops run.
      - When rows are stable: compute column hashes from matched rows and emit
        DeleteTableColumnEdit / InsertTableColumnEdit.

    Phase 3 — Cell content edits:
      - For matched (row, col) pairs whose text changed, emit
        ReplaceParagraphSliceEdit.

    Key constraint: Row structural changes and column structural changes are
    never emitted in the same diff call.  If the caller needs both, a second
    diff pass is required after applying the first set.  This avoids the
    index-shift problem where inserting rows changes the row count used by
    column index references.

    Insertion ordering:
      - Prepend insertions (before first anchor): emitted REVERSED so each
        prepend at position 0 builds the correct final order.
      - Post-anchor insertions: REVERSED per anchor group so the API's
        "insert immediately after anchor" produces forward desired order.
    """
    if ctx is None:
        ctx = TableDiffContext(tab_id="t.0", section_index=0, block_index=0)

    edits: list[SemanticEdit] = []

    # -----------------------------------------------------------------------
    # Phase 1: Row alignment via fuzzy LCS
    # -----------------------------------------------------------------------
    row_lcs = _fuzzy_lcs_indices(base.rows, desired.rows)

    anchor_row_map: dict[int, int] = dict(row_lcs)
    anchored_desired_rows: set[int] = {d for _, d in row_lcs}

    deleted_rows = sorted(
        [i for i in range(len(base.rows)) if i not in anchor_row_map],
        reverse=True,
    )
    inserted_desired_rows = [
        i for i in range(len(desired.rows)) if i not in anchored_desired_rows
    ]

    has_row_structural_changes = bool(deleted_rows or inserted_desired_rows)

    # -----------------------------------------------------------------------
    # Phase 2: Column alignment (only when rows are structurally identical)
    # -----------------------------------------------------------------------
    base_col_count = max((len(row.cells) for row in base.rows), default=0)
    desired_col_count = max((len(row.cells) for row in desired.rows), default=0)

    col_lcs: list[tuple[int, int]] = []
    deleted_cols: list[int] = []
    inserted_desired_cols: list[int] = []

    if not has_row_structural_changes:
        # Rows are structurally stable → safe to do column structural changes.
        #
        # Column count changed: use exact column-hash LCS to find insertions/deletions.
        # Column count unchanged: use positional matching for cell content edits only —
        # a cell text change is NOT a column structural change.
        if base_col_count != desired_col_count:
            # Build column hashes from ALL rows (positional anchoring since rows stable).
            def _base_col_hash(col: int) -> str:
                return "\n".join(
                    cell_text_hash(base.rows[r].cells[col])
                    if col < len(base.rows[r].cells)
                    else ""
                    for r in range(len(base.rows))
                )

            def _desired_col_hash(col: int) -> str:
                return "\n".join(
                    cell_text_hash(desired.rows[r].cells[col])
                    if col < len(desired.rows[r].cells)
                    else ""
                    for r in range(len(desired.rows))
                )

            base_col_hashes = [_base_col_hash(c) for c in range(base_col_count)]
            desired_col_hashes = [
                _desired_col_hash(c) for c in range(desired_col_count)
            ]
            col_lcs = _lcs_indices(base_col_hashes, desired_col_hashes)

            deleted_cols = sorted(
                [i for i in range(base_col_count) if i not in {b for b, _d in col_lcs}],
                reverse=True,
            )
            inserted_desired_cols = [
                i for i in range(desired_col_count) if i not in {d for _b, d in col_lcs}
            ]
        else:
            # Same column count: positional matching for cell content edits only.
            min_cols = min(base_col_count, desired_col_count)
            col_lcs = [(i, i) for i in range(min_cols)]
            # No deleted_cols / inserted_desired_cols: cell changes go through Phase 3.
    else:
        # Row structural changes present: only match columns positionally for cell edits,
        # but don't emit any column structural changes.
        min_cols = min(base_col_count, desired_col_count)
        col_lcs = [(i, i) for i in range(min_cols)]

    anchor_col_map: dict[int, int] = dict(col_lcs)

    # -----------------------------------------------------------------------
    # Emit: row deletions (highest index first)
    # -----------------------------------------------------------------------
    for row_idx in deleted_rows:
        edits.append(
            DeleteTableRowEdit(
                tab_id=ctx.tab_id,
                section_index=ctx.section_index,
                block_index=ctx.block_index,
                row_index=row_idx,
            )
        )

    # -----------------------------------------------------------------------
    # Emit: row insertions.
    # inserted_cells is truncated to base_col_count so the API receives a
    # well-formed row that fits the table's current column structure.
    # Any columns beyond base_col_count will be filled in a subsequent
    # column-insertion pass.
    # -----------------------------------------------------------------------
    def _row_cells_for_insert(d_idx: int) -> tuple[str, ...]:
        cells_in_row = desired.rows[d_idx].cells
        return tuple(
            cell_text_hash(cells_in_row[c]) if c < len(cells_in_row) else ""
            for c in range(base_col_count)
        )

    _emit_insertions(
        edits=edits,
        inserted_desired_indices=inserted_desired_rows,
        lcs_pairs=row_lcs,
        make_insert_above=lambda d_idx: InsertTableRowEdit(
            tab_id=ctx.tab_id,
            section_index=ctx.section_index,
            block_index=ctx.block_index,
            row_index=0,
            insert_below=False,
            inserted_cells=_row_cells_for_insert(d_idx),
        ),
        make_insert_below=lambda d_idx, base_anchor: InsertTableRowEdit(
            tab_id=ctx.tab_id,
            section_index=ctx.section_index,
            block_index=ctx.block_index,
            row_index=base_anchor,
            insert_below=True,
            inserted_cells=_row_cells_for_insert(d_idx),
        ),
    )

    # -----------------------------------------------------------------------
    # Emit: column deletions (highest index first)
    # -----------------------------------------------------------------------
    for col_idx in deleted_cols:
        edits.append(
            DeleteTableColumnEdit(
                tab_id=ctx.tab_id,
                section_index=ctx.section_index,
                block_index=ctx.block_index,
                column_index=col_idx,
            )
        )

    # -----------------------------------------------------------------------
    # Emit: column insertions
    # -----------------------------------------------------------------------
    _emit_insertions(
        edits=edits,
        inserted_desired_indices=inserted_desired_cols,
        lcs_pairs=col_lcs,
        make_insert_above=lambda d_idx: InsertTableColumnEdit(
            tab_id=ctx.tab_id,
            section_index=ctx.section_index,
            block_index=ctx.block_index,
            column_index=0,
            insert_right=False,
            inserted_cells=_col_cells_from_desired(desired, d_idx),
        ),
        make_insert_below=lambda d_idx, base_anchor: InsertTableColumnEdit(
            tab_id=ctx.tab_id,
            section_index=ctx.section_index,
            block_index=ctx.block_index,
            column_index=base_anchor,
            insert_right=True,
            inserted_cells=_col_cells_from_desired(desired, d_idx),
        ),
    )

    # -----------------------------------------------------------------------
    # Phase 3: Cell content edits for matched cells where text changed.
    #
    # Safety guard: only emit cell content edits for a matched row pair if the
    # row's column count is the SAME in both base and desired.  When column
    # counts differ for a matched row (because a column was simultaneously
    # inserted or deleted), positional column matching produces incorrect
    # pairings.  Those cells will be handled in a subsequent pass after the
    # column structural changes are applied.
    # -----------------------------------------------------------------------
    for base_row_idx, desired_row_idx in anchor_row_map.items():
        base_row = base.rows[base_row_idx]
        desired_row = desired.rows[desired_row_idx]
        if len(base_row.cells) != len(desired_row.cells):
            # Column count mismatch for this row: skip cell content edits.
            # The column structural changes (from a future pass) will fix this.
            continue
        for base_col_idx, desired_col_idx in anchor_col_map.items():
            if base_col_idx >= len(base_row.cells) or desired_col_idx >= len(
                desired_row.cells
            ):
                continue
            base_cell = base_row.cells[base_col_idx]
            desired_cell = desired_row.cells[desired_col_idx]
            if cell_text_hash(base_cell) == cell_text_hash(desired_cell):
                continue
            story_id = (
                f"{ctx.tab_id}:body:table:{ctx.block_index}"
                f":r{base_row_idx}:c{base_col_idx}"
            )
            desired_paragraphs = tuple(
                ParagraphFragment(paragraph=block)
                for block in desired_cell.content.blocks
                if isinstance(block, ParagraphIR)
            )
            edits.append(
                ReplaceParagraphSliceEdit(
                    tab_id=ctx.tab_id,
                    story_id=story_id,
                    section_index=None,
                    start_block_index=0,
                    delete_block_count=len(base_cell.content.blocks),
                    inserted_paragraphs=desired_paragraphs,
                )
            )

    return edits


# ---------------------------------------------------------------------------
# Generic insertion emitter (shared by rows and columns)
# ---------------------------------------------------------------------------


def _emit_insertions(
    edits: list[SemanticEdit],
    inserted_desired_indices: list[int],
    lcs_pairs: list[tuple[int, int]],
    make_insert_above: Callable[[int], SemanticEdit],
    make_insert_below: Callable[[int, int], SemanticEdit],
) -> None:
    """Emit insertion edits for the given indices in the correct sequential order.

    For items BEFORE any anchor (prepend): emit in REVERSE desired order so
    each prepend at position 0 builds the correct final top-down sequence.

    For items AFTER an anchor: emit in REVERSE desired order per anchor group.
    The API inserts each item immediately after the SAME anchor index, so
    emitting in reverse order produces forward desired ordering.

    Example (3 rows to insert after anchor at base_idx=2):
      Emit (reverse): d=6 below 2, d=5 below 2, d=4 below 2.
      Result: [..., anchor, d4, d5, d6, ...]  ✓
    """
    if not inserted_desired_indices:
        return

    desired_to_base: dict[int, int] = {d: b for b, d in lcs_pairs}
    anchor_desired_sorted = sorted(desired_to_base.keys())

    def _prev_anchor(ins_d_idx: int) -> int | None:
        prev: int | None = None
        for a in anchor_desired_sorted:
            if a < ins_d_idx:
                prev = a
        return prev

    prepend_group: list[int] = []
    after_groups: dict[int, list[int]] = {}

    for ins_d_idx in inserted_desired_indices:
        prev_a_d = _prev_anchor(ins_d_idx)
        if prev_a_d is None:
            prepend_group.append(ins_d_idx)
        else:
            after_groups.setdefault(desired_to_base[prev_a_d], []).append(ins_d_idx)

    # Prepend group: reverse desired order
    for ins_d_idx in reversed(prepend_group):
        edits.append(make_insert_above(ins_d_idx))

    # After-anchor groups: reverse desired order per group, forward anchor order
    for base_anchor_idx in sorted(after_groups.keys()):
        for ins_d_idx in reversed(after_groups[base_anchor_idx]):
            edits.append(make_insert_below(ins_d_idx, base_anchor_idx))


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _col_cells_from_desired(desired: TableIR, col_idx: int) -> tuple[str, ...]:
    return tuple(
        cell_text_hash(row.cells[col_idx]) if col_idx < len(row.cells) else ""
        for row in desired.rows
    )
