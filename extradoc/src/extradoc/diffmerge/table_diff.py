"""Heuristic table structural diff for reconcile_v3.

This module implements:
- cell_text_hash: extract plain text from a typed TableCell model
- table_similarity: 0.0-1.0 measure of how similar two tables are
- match_tables: greedy bipartite match of base vs desired tables
- diff_tables: minimal sequence of row/column structural + cell content ops

Adapted from reconcile_v2/table_diff.py.  This version operates on typed
Pydantic models from api_types._generated, and returns v3 ReconcileOp types.

Design principles:
- No Google API calls; pure in-memory computation over typed models.
- May import from model.py but NOT from diff.py or lower.py.
- Deterministic: same input → same output.
- Handles multi-row and multi-column changes (unlimited).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from extradoc.api_types._generated import Table, TableCell, TableRow
from extradoc.diffmerge.model import (
    DeleteTableColumnOp,
    DeleteTableRowOp,
    InsertTableColumnOp,
    InsertTableRowOp,
    ReconcileOp,
)

# ---------------------------------------------------------------------------
# Cell text extraction
# ---------------------------------------------------------------------------


def cell_text_hash(cell: TableCell) -> str:
    """Return a normalized plain-text string for a cell's content.

    Formatting is ignored; only text content is used.  The result is suitable
    as a dictionary key for set-intersection comparisons.
    """
    parts: list[str] = []
    for el in cell.content or []:
        para = el.paragraph
        if para is None:
            continue
        for inline in para.elements or []:
            text_run = inline.text_run
            if text_run is not None:
                content = text_run.content or ""
                parts.append(content)
        parts.append("\n")
    return "".join(parts).rstrip("\n")


# ---------------------------------------------------------------------------
# Similarity metric
# ---------------------------------------------------------------------------


def table_similarity(base: Table, desired: Table) -> float:
    """Return a similarity score in [0.0, 1.0].

    Computed as:  |intersection of cell text hashes| / |base cell count|

    Empty base → 1.0.
    """
    base_hashes: list[str] = [
        cell_text_hash(cell)
        for row in base.table_rows or []
        for cell in row.table_cells or []
    ]
    if not base_hashes:
        return 1.0
    desired_hashes: set[str] = {
        cell_text_hash(cell)
        for row in desired.table_rows or []
        for cell in row.table_cells or []
    }
    intersection = sum(1 for h in base_hashes if h in desired_hashes)
    return intersection / len(base_hashes)


# ---------------------------------------------------------------------------
# Table identity matching (greedy bipartite)
# ---------------------------------------------------------------------------


def match_tables(
    base_tables: list[Table],
    desired_tables: list[Table],
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
    base_rows: list[TableRow],
    desired_rows: list[TableRow],
    *,
    match_threshold: float = 0.5,
) -> list[tuple[int, int]]:
    """Fuzzy LCS: rows match if cell-text RECALL (overlap/base_size) >= threshold.

    Recall rather than Jaccard is used so that adding columns to a row does not
    prevent it from matching its base counterpart.

    Returns (base_idx, desired_idx) pairs in order.
    """
    m = len(base_rows)
    n = len(desired_rows)

    base_sets: list[frozenset[str]] = [
        frozenset(cell_text_hash(c) for c in row.table_cells or []) for row in base_rows
    ]
    desired_sets: list[frozenset[str]] = [
        frozenset(cell_text_hash(c) for c in row.table_cells or [])
        for row in desired_rows
    ]

    def _recall(b_set: frozenset[str], d_set: frozenset[str]) -> float:
        """overlap / base_size (how much of the base row is preserved)."""
        if not b_set:
            return 1.0
        return len(b_set & d_set) / len(b_set)

    # Precompute similarity matrix
    sim: list[list[float]] = [
        [_recall(base_sets[i], desired_sets[j]) for j in range(n)] for i in range(m)
    ]

    # LCS-style DP: maximize match count, break ties by total similarity
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
    base: Table,
    desired: Table,
    *,
    tab_id: str,
    table_start_index: int,
) -> list[ReconcileOp]:
    """Compute a minimal sequence of ReconcileOps to transform base into desired.

    Parameters
    ----------
    base:
        Typed ``Table`` model from the Google Docs API.
    desired:
        The desired target ``Table`` model.
    tab_id:
        The tab identifier for emitted ops.
    table_start_index:
        The startIndex of the table element in the flat document space.
        Used by lowering to construct ``tableStartLocation``.

    Returns
    -------
    list[ReconcileOp]
        Ordered list of structural ops (InsertTableRowOp, DeleteTableRowOp,
        InsertTableColumnOp, DeleteTableColumnOp).  Cell content changes are
        NOT emitted here — they are handled by the caller (_diff_table in
        diff.py) via ContentAlignment on the matched cells.

    Algorithm overview
    ------------------
    Phase 1 — Row alignment (fuzzy LCS):
      - Match rows via Recall similarity on cell-text sets.
      - Unmatched base rows → DeleteTableRowOp (highest index first).
      - Unmatched desired rows → InsertTableRowOp.

    Phase 2 — Column alignment (independent of row changes):
      - Compute column hashes and emit DeleteTableColumnOp /
        InsertTableColumnOp when column count differs.
      - Row and column structural changes can be emitted in the same call.
    """
    base_rows = base.table_rows or []
    desired_rows = desired.table_rows or []

    ops: list[ReconcileOp] = []

    # -----------------------------------------------------------------------
    # Phase 1: Row alignment via fuzzy LCS
    # -----------------------------------------------------------------------
    row_lcs = _fuzzy_lcs_indices(base_rows, desired_rows)

    anchor_row_map: dict[int, int] = dict(row_lcs)
    anchored_desired_rows: set[int] = {d for _, d in row_lcs}

    deleted_rows = sorted(
        [i for i in range(len(base_rows)) if i not in anchor_row_map],
        reverse=True,
    )
    inserted_desired_rows = [
        i for i in range(len(desired_rows)) if i not in anchored_desired_rows
    ]

    # -----------------------------------------------------------------------
    # Phase 2: Column alignment (only when rows are structurally identical)
    # -----------------------------------------------------------------------
    base_col_count = max((len(row.table_cells or []) for row in base_rows), default=0)
    desired_col_count = max(
        (len(row.table_cells or []) for row in desired_rows), default=0
    )

    col_lcs: list[tuple[int, int]] = []
    deleted_cols: list[int] = []
    inserted_desired_cols: list[int] = []

    if base_col_count != desired_col_count:

        def _base_col_hash(col: int) -> str:
            return "\n".join(
                cell_text_hash((base_rows[r].table_cells or [])[col])
                if col < len(base_rows[r].table_cells or [])
                else ""
                for r in range(len(base_rows))
            )

        def _desired_col_hash(col: int) -> str:
            return "\n".join(
                cell_text_hash((desired_rows[r].table_cells or [])[col])
                if col < len(desired_rows[r].table_cells or [])
                else ""
                for r in range(len(desired_rows))
            )

        base_col_hashes = [_base_col_hash(c) for c in range(base_col_count)]
        desired_col_hashes = [_desired_col_hash(c) for c in range(desired_col_count)]
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

    # -----------------------------------------------------------------------
    # Emit: row deletions (highest index first)
    # -----------------------------------------------------------------------
    for row_idx in deleted_rows:
        ops.append(
            DeleteTableRowOp(
                tab_id=tab_id,
                table_start_index=table_start_index,
                row_index=row_idx,
            )
        )

    # -----------------------------------------------------------------------
    # Emit: row insertions
    # -----------------------------------------------------------------------
    _emit_row_insertions(
        ops=ops,
        inserted_desired_indices=inserted_desired_rows,
        lcs_pairs=row_lcs,
        tab_id=tab_id,
        table_start_index=table_start_index,
        base_col_count=base_col_count,
    )

    # -----------------------------------------------------------------------
    # Emit: column deletions (highest index first)
    # -----------------------------------------------------------------------
    for col_idx in deleted_cols:
        ops.append(
            DeleteTableColumnOp(
                tab_id=tab_id,
                table_start_index=table_start_index,
                column_index=col_idx,
            )
        )

    # -----------------------------------------------------------------------
    # Emit: column insertions
    # -----------------------------------------------------------------------
    _emit_col_insertions(
        ops=ops,
        inserted_desired_indices=inserted_desired_cols,
        lcs_pairs=col_lcs,
        tab_id=tab_id,
        table_start_index=table_start_index,
    )

    return ops


def get_matched_rows(
    base: Table,
    desired: Table,
) -> list[tuple[int, int]]:
    """Return the fuzzy-LCS row matches for base and desired tables.

    Used by the caller to iterate over matched rows for cell content diffing.
    """
    base_rows = base.table_rows or []
    desired_rows = desired.table_rows or []
    return _fuzzy_lcs_indices(base_rows, desired_rows)


# ---------------------------------------------------------------------------
# Generic insertion emitters
# ---------------------------------------------------------------------------


def _emit_row_insertions(
    ops: list[ReconcileOp],
    inserted_desired_indices: list[int],
    lcs_pairs: list[tuple[int, int]],
    tab_id: str,
    table_start_index: int,
    base_col_count: int,
) -> None:
    """Emit InsertTableRowOp for each unmatched desired row."""
    if not inserted_desired_indices:
        return

    def make_insert_above(d_idx: int) -> ReconcileOp:  # noqa: ARG001
        return InsertTableRowOp(
            tab_id=tab_id,
            table_start_index=table_start_index,
            row_index=0,
            insert_below=False,
            column_count=base_col_count,
        )

    def make_insert_below(d_idx: int, base_anchor: int) -> ReconcileOp:  # noqa: ARG001
        return InsertTableRowOp(
            tab_id=tab_id,
            table_start_index=table_start_index,
            row_index=base_anchor,
            insert_below=True,
            column_count=base_col_count,
        )

    _emit_insertions(
        ops=ops,
        inserted_desired_indices=inserted_desired_indices,
        lcs_pairs=lcs_pairs,
        make_insert_above=make_insert_above,
        make_insert_below=make_insert_below,
    )


def _emit_col_insertions(
    ops: list[ReconcileOp],
    inserted_desired_indices: list[int],
    lcs_pairs: list[tuple[int, int]],
    tab_id: str,
    table_start_index: int,
) -> None:
    """Emit InsertTableColumnOp for each unmatched desired column."""
    if not inserted_desired_indices:
        return

    def make_insert_above(d_idx: int) -> ReconcileOp:  # noqa: ARG001
        return InsertTableColumnOp(
            tab_id=tab_id,
            table_start_index=table_start_index,
            column_index=0,
            insert_right=False,
        )

    def make_insert_below(d_idx: int, base_anchor: int) -> ReconcileOp:  # noqa: ARG001
        return InsertTableColumnOp(
            tab_id=tab_id,
            table_start_index=table_start_index,
            column_index=base_anchor,
            insert_right=True,
        )

    _emit_insertions(
        ops=ops,
        inserted_desired_indices=inserted_desired_indices,
        lcs_pairs=lcs_pairs,
        make_insert_above=make_insert_above,
        make_insert_below=make_insert_below,
    )


def _emit_insertions(
    ops: list[ReconcileOp],
    inserted_desired_indices: list[int],
    lcs_pairs: list[tuple[int, int]],
    make_insert_above: Callable[[int], ReconcileOp],
    make_insert_below: Callable[[int, int], ReconcileOp],
) -> None:
    """Emit insertion ops for the given indices in the correct sequential order.

    For items BEFORE any anchor (prepend): emit in REVERSE desired order so
    each prepend at position 0 builds the correct final top-down sequence.

    For items AFTER an anchor: emit in REVERSE desired order per anchor group.
    The API inserts each item immediately after the SAME anchor index, so
    emitting in reverse order produces forward desired ordering.
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
        ops.append(make_insert_above(ins_d_idx))

    # After-anchor groups: reverse desired order per group, forward anchor order
    for base_anchor_idx in sorted(after_groups.keys()):
        for ins_d_idx in reversed(after_groups[base_anchor_idx]):
            ops.append(make_insert_below(ins_d_idx, base_anchor_idx))
