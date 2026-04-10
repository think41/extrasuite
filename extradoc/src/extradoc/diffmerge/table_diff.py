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

from difflib import SequenceMatcher
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


def _cell_plain_text(cell: TableCell) -> str:
    """Concatenate a cell's paragraph text verbatim, trimming the trailing "\\n".

    Unlike :func:`cell_text_hash`, this does not add extra paragraph
    delimiters: each paragraph's ``textRun`` content is appended in order,
    then a single trailing newline (the cell's mandatory final "\\n") is
    stripped. Suitable for reconstructing the desired text to insert into a
    freshly-created cell with ``insertText``.
    """
    parts: list[str] = []
    for el in cell.content or []:
        para = el.paragraph
        if para is None:
            continue
        for inline in para.elements or []:
            text_run = inline.text_run
            if text_run is not None:
                parts.append(text_run.content or "")
    text = "".join(parts)
    # A cell's paragraphs each end in "\n". The final paragraph of a cell is
    # always a bare "\n" (the cell's structural terminator), and the
    # penultimate paragraph carries the user text ending in its own "\n".
    # So the concatenation ends in up to two trailing "\n"s that do NOT
    # belong to the user-visible cell text. Strip up to two.
    if text.endswith("\n"):
        text = text[:-1]
    if text.endswith("\n"):
        text = text[:-1]
    return text


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

    base_cells: list[list[str]] = [
        [cell_text_hash(c) for c in row.table_cells or []] for row in base_rows
    ]
    desired_cells: list[list[str]] = [
        [cell_text_hash(c) for c in row.table_cells or []] for row in desired_rows
    ]
    base_sets: list[frozenset[str]] = [frozenset(cs) for cs in base_cells]
    desired_sets: list[frozenset[str]] = [frozenset(cs) for cs in desired_cells]

    def _row_similarity(
        b_cells: list[str],
        d_cells: list[str],
        b_set: frozenset[str],
        d_set: frozenset[str],
    ) -> float:
        """Row similarity with partial credit for edited cells.

        Combines two signals:
        1. Set-recall (overlap / base_size) — handles unchanged cells and
           column additions.
        2. Positional per-cell character similarity — gives partial credit
           when a cell's text was edited in place (e.g. "900" -> "950"),
           which the set-recall metric would score as 0.
        The final score is the max of the two so neither signal can drag
        the other down.
        """
        recall = 1.0 if not b_set else len(b_set & d_set) / len(b_set)
        if not b_cells:
            return recall
        k = min(len(b_cells), len(d_cells))
        if k == 0:
            return recall
        pos_total = 0.0
        for idx in range(k):
            pos_total += SequenceMatcher(None, b_cells[idx], d_cells[idx]).ratio()
        pos_avg = pos_total / len(b_cells)
        return max(recall, pos_avg)

    sim: list[list[float]] = [
        [
            _row_similarity(
                base_cells[i], desired_cells[j], base_sets[i], desired_sets[j]
            )
            for j in range(n)
        ]
        for i in range(m)
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
        row = base_rows[row_idx]
        ops.append(
            DeleteTableRowOp(
                tab_id=tab_id,
                table_start_index=table_start_index,
                row_index=row_idx,
                row_start_index=row.start_index,
                row_end_index=row.end_index,
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
        base_rows=base_rows,
        desired_rows=desired_rows,
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
        base_rows=base_rows,
        desired_rows=desired_rows,
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
    base_rows: list[TableRow],
    desired_rows: list[TableRow],
) -> None:
    """Emit InsertTableRowOp for each unmatched desired row.

    Each emitted op carries ``new_cell_texts`` (the desired text for each new
    cell, in column order) and ``new_row_start_index`` (the byte index in the
    base document where the new row's first char will land after
    ``insertTableRow`` executes). The lowering layer uses both to emit
    ``insertText`` requests that populate the newly-created cells.
    """
    if not inserted_desired_indices:
        return

    def _desired_cell_texts(d_idx: int) -> list[str]:
        cells = desired_rows[d_idx].table_cells or []
        return [_cell_plain_text(c) for c in cells]

    def _anchor_row_end(base_row_idx: int) -> int | None:
        """Byte index where a row inserted BELOW base_rows[base_row_idx] begins.

        Returns ``None`` when the row has no index info (e.g. in synthetic
        unit tests without API indices). In that case the emitted
        ``InsertTableRowOp`` carries an empty ``new_cell_texts`` — the
        structural row insert still happens, but no cell-text inserts are
        emitted by lowering.
        """
        return base_rows[base_row_idx].end_index

    def _anchor_row_start(base_row_idx: int) -> int | None:
        """Byte index where a row inserted ABOVE base_rows[base_row_idx] begins."""
        return base_rows[base_row_idx].start_index

    def make_insert_above(d_idx: int) -> ReconcileOp:
        # ``_emit_insertions`` calls make_insert_above only when there is no
        # preceding anchor — the new row is prepended above base row 0.
        anchor_idx = _anchor_row_start(0)
        return InsertTableRowOp(
            tab_id=tab_id,
            table_start_index=table_start_index,
            row_index=0,
            insert_below=False,
            column_count=base_col_count,
            new_row_start_index=anchor_idx,
            new_cell_texts=_desired_cell_texts(d_idx) if anchor_idx is not None else [],
        )

    def make_insert_below(d_idx: int, base_anchor: int) -> ReconcileOp:
        anchor_idx = _anchor_row_end(base_anchor)
        return InsertTableRowOp(
            tab_id=tab_id,
            table_start_index=table_start_index,
            row_index=base_anchor,
            insert_below=True,
            column_count=base_col_count,
            new_row_start_index=anchor_idx,
            new_cell_texts=_desired_cell_texts(d_idx) if anchor_idx is not None else [],
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
    base_rows: list[TableRow],
    desired_rows: list[TableRow],
) -> None:
    """Emit InsertTableColumnOp for each unmatched desired column.

    Each emitted op carries ``new_cell_texts`` (the desired text for each of
    the new column's cells, one per base row in row order) and
    ``new_cell_anchor_indices`` (per-row BASE byte indices identifying where
    the new cell lands in each row). The lowering layer uses both to emit
    ``insertText`` requests that populate the newly-created cells.
    """
    if not inserted_desired_indices:
        return

    def _desired_cell_texts(d_col: int) -> list[str]:
        # Pull the desired column's cell texts aligned to the BASE rows.
        # When base and desired row counts match (the common case — column
        # inserts happen on structurally-identical row sets) this is just the
        # desired_rows[r].cells[d_col] text for each r. When counts differ,
        # fall back to pulling from whichever desired row exists; if the
        # desired table has fewer rows than base, pad with "".
        out: list[str] = []
        for r in range(len(base_rows)):
            if r >= len(desired_rows):
                out.append("")
                continue
            cells = desired_rows[r].table_cells or []
            if d_col >= len(cells):
                out.append("")
                continue
            out.append(_cell_plain_text(cells[d_col]))
        return out

    def _anchor_indices_insert_right(base_col: int) -> list[int | None]:
        """End-index of each base row's cell at ``base_col``."""
        out: list[int | None] = []
        for row in base_rows:
            cells = row.table_cells or []
            if base_col >= len(cells):
                out.append(None)
            else:
                out.append(cells[base_col].end_index)
        return out

    def _anchor_indices_insert_left(base_col: int) -> list[int | None]:
        """Start-index of each base row's cell at ``base_col``."""
        out: list[int | None] = []
        for row in base_rows:
            cells = row.table_cells or []
            if base_col >= len(cells):
                out.append(None)
            else:
                out.append(cells[base_col].start_index)
        return out

    def _has_any_index(anchors: list[int | None]) -> bool:
        return any(a is not None for a in anchors)

    def make_insert_above(d_idx: int) -> ReconcileOp:
        # Prepend: new column goes to the LEFT of base col 0.
        anchors = _anchor_indices_insert_left(0)
        populated = _has_any_index(anchors)
        return InsertTableColumnOp(
            tab_id=tab_id,
            table_start_index=table_start_index,
            column_index=0,
            insert_right=False,
            new_cell_anchor_indices=anchors if populated else [],
            new_cell_texts=_desired_cell_texts(d_idx) if populated else [],
        )

    def make_insert_below(d_idx: int, base_anchor: int) -> ReconcileOp:
        # Insert to the RIGHT of base column ``base_anchor``.
        anchors = _anchor_indices_insert_right(base_anchor)
        populated = _has_any_index(anchors)
        return InsertTableColumnOp(
            tab_id=tab_id,
            table_start_index=table_start_index,
            column_index=base_anchor,
            insert_right=True,
            new_cell_anchor_indices=anchors if populated else [],
            new_cell_texts=_desired_cell_texts(d_idx) if populated else [],
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
