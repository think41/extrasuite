"""Tests for the new heuristic table diff algorithm in table_diff.py.

Tests are entirely in-memory — no Google API calls, no Document parsing.
TableIR objects are constructed directly using make_cell / make_row / make_table
helpers from table_diff.py.
"""

from __future__ import annotations

import random

import pytest

from extradoc.reconcile_v2.diff import (
    DeleteTableColumnEdit,
    DeleteTableRowEdit,
    InsertTableColumnEdit,
    InsertTableRowEdit,
    ReplaceParagraphSliceEdit,
)
from extradoc.reconcile_v2.ir import (
    TableIR,
    TextSpanIR,
)
from extradoc.reconcile_v2.table_diff import (
    TableDiffContext,
    cell_text_hash,
    diff_tables,
    make_cell,
    make_table,
    match_tables,
    table_similarity,
)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

CTX = TableDiffContext(tab_id="t.0", section_index=0, block_index=2)


def _edit_types(edits: list) -> list[type]:
    return [type(e) for e in edits]


def _insert_row_indices(edits: list) -> list[tuple[int, bool]]:
    """Return (row_index, insert_below) for InsertTableRowEdits."""
    return [
        (e.row_index, e.insert_below)
        for e in edits
        if isinstance(e, InsertTableRowEdit)
    ]


def _delete_row_indices(edits: list) -> list[int]:
    return [e.row_index for e in edits if isinstance(e, DeleteTableRowEdit)]


def _insert_col_indices(edits: list) -> list[tuple[int, bool]]:
    return [
        (e.column_index, e.insert_right)
        for e in edits
        if isinstance(e, InsertTableColumnEdit)
    ]


def _delete_col_indices(edits: list) -> list[int]:
    return [e.column_index for e in edits if isinstance(e, DeleteTableColumnEdit)]


# ---------------------------------------------------------------------------
# cell_text_hash tests
# ---------------------------------------------------------------------------


class TestCellTextHash:
    def test_empty_cell(self):
        cell = make_cell("")
        assert cell_text_hash(cell) == ""

    def test_simple_text(self):
        cell = make_cell("hello")
        assert cell_text_hash(cell) == "hello"

    def test_multiword_text(self):
        cell = make_cell("hello world")
        assert cell_text_hash(cell) == "hello world"

    def test_different_cells_different_hashes(self):
        assert cell_text_hash(make_cell("foo")) != cell_text_hash(make_cell("bar"))

    def test_same_text_same_hash(self):
        assert cell_text_hash(make_cell("abc")) == cell_text_hash(make_cell("abc"))


# ---------------------------------------------------------------------------
# table_similarity tests
# ---------------------------------------------------------------------------


class TestTableSimilarity:
    def test_identical_table(self):
        t = make_table([["a", "b"], ["c", "d"]])
        assert table_similarity(t, t) == 1.0

    def test_identical_independent_tables(self):
        t1 = make_table([["a", "b"], ["c", "d"]])
        t2 = make_table([["a", "b"], ["c", "d"]])
        assert table_similarity(t1, t2) == 1.0

    def test_one_row_added(self):
        base = make_table([["a", "b"], ["c", "d"]])
        desired = make_table([["a", "b"], ["c", "d"], ["e", "f"]])
        sim = table_similarity(base, desired)
        # 4 base cells, all present in desired → 1.0
        assert sim == 1.0

    def test_completely_different(self):
        base = make_table([["a", "b"], ["c", "d"]])
        desired = make_table([["x", "y"], ["z", "w"]])
        sim = table_similarity(base, desired)
        assert sim == 0.0

    def test_partially_similar(self):
        base = make_table([["a", "b"], ["c", "d"]])
        desired = make_table([["a", "b"], ["x", "y"]])
        sim = table_similarity(base, desired)
        # 2 of 4 base cells present in desired
        assert sim == 0.5

    def test_empty_base_table(self):
        base = make_table([])
        desired = make_table([["a"]])
        # empty base → 1.0 by convention
        assert table_similarity(base, desired) == 1.0

    def test_row_deleted(self):
        base = make_table([["a", "b"], ["c", "d"], ["e", "f"]])
        desired = make_table([["a", "b"], ["e", "f"]])
        sim = table_similarity(base, desired)
        # 4 of 6 base cells present in desired
        assert sim == pytest.approx(4 / 6)


# ---------------------------------------------------------------------------
# match_tables tests
# ---------------------------------------------------------------------------


class TestMatchTables:
    def test_empty_lists(self):
        assert match_tables([], []) == []

    def test_single_identical(self):
        t = make_table([["a", "b"]])
        pairs = match_tables([t], [t])
        assert pairs == [(0, 0)]

    def test_two_tables_matched_correctly(self):
        t1_base = make_table([["a", "b"], ["c", "d"]])
        t2_base = make_table([["x", "y"]])
        t1_desired = make_table([["a", "b"], ["c", "d"]])
        t2_desired = make_table([["x", "y"]])
        pairs = match_tables([t1_base, t2_base], [t1_desired, t2_desired])
        assert set(pairs) == {(0, 0), (1, 1)}

    def test_tables_reordered(self):
        t1 = make_table([["a", "b"]])
        t2 = make_table([["x", "y"]])
        # desired has them in reverse order
        pairs = match_tables([t1, t2], [t2, t1])
        # t1 should match desired[1], t2 should match desired[0]
        assert set(pairs) == {(0, 1), (1, 0)}


# ---------------------------------------------------------------------------
# Deterministic diff_tables tests
# ---------------------------------------------------------------------------


class TestDiffTablesNoChange:
    def test_identical_table_no_edits(self):
        t = make_table([["a", "b"], ["c", "d"]])
        edits = diff_tables(t, t, ctx=CTX)
        # No structural edits; cell content unchanged
        structural = [
            e
            for e in edits
            if isinstance(
                e,
                InsertTableRowEdit
                | DeleteTableRowEdit
                | InsertTableColumnEdit
                | DeleteTableColumnEdit,
            )
        ]
        assert structural == []

    def test_empty_table_no_edits(self):
        t = make_table([])
        edits = diff_tables(t, t, ctx=CTX)
        assert edits == []


class TestDiffTablesRowInsert:
    def test_add_row_at_end(self):
        base = make_table([["a", "b"], ["c", "d"]])
        desired = make_table([["a", "b"], ["c", "d"], ["e", "f"]])
        edits = diff_tables(base, desired, ctx=CTX)
        inserts = [e for e in edits if isinstance(e, InsertTableRowEdit)]
        assert len(inserts) == 1
        ins = inserts[0]
        # Should insert below row 1 (the last base row)
        assert ins.insert_below is True
        assert ins.inserted_cells == ("e", "f")

    def test_add_row_at_beginning(self):
        base = make_table([["c", "d"], ["e", "f"]])
        desired = make_table([["a", "b"], ["c", "d"], ["e", "f"]])
        edits = diff_tables(base, desired, ctx=CTX)
        inserts = [e for e in edits if isinstance(e, InsertTableRowEdit)]
        assert len(inserts) == 1
        ins = inserts[0]
        assert ins.insert_below is False

    def test_add_row_in_middle(self):
        base = make_table([["a", "b"], ["e", "f"]])
        desired = make_table([["a", "b"], ["c", "d"], ["e", "f"]])
        edits = diff_tables(base, desired, ctx=CTX)
        inserts = [e for e in edits if isinstance(e, InsertTableRowEdit)]
        assert len(inserts) == 1
        ins = inserts[0]
        # Inserted after "a,b" row (base index 0)
        assert ins.row_index == 0
        assert ins.insert_below is True
        assert ins.inserted_cells == ("c", "d")

    def test_add_multiple_rows(self):
        base = make_table([["a", "b"]])
        desired = make_table([["a", "b"], ["c", "d"], ["e", "f"], ["g", "h"]])
        edits = diff_tables(base, desired, ctx=CTX)
        inserts = [e for e in edits if isinstance(e, InsertTableRowEdit)]
        assert len(inserts) == 3
        # All inserts should have insert_below=True (anchored to "a,b" row)
        for ins in inserts:
            assert ins.insert_below is True

    def test_no_spurious_deletes_on_insert(self):
        base = make_table([["a", "b"], ["c", "d"]])
        desired = make_table([["a", "b"], ["c", "d"], ["e", "f"]])
        edits = diff_tables(base, desired, ctx=CTX)
        deletes = [e for e in edits if isinstance(e, DeleteTableRowEdit)]
        assert deletes == []


class TestDiffTablesRowDelete:
    def test_delete_last_row(self):
        base = make_table([["a", "b"], ["c", "d"]])
        desired = make_table([["a", "b"]])
        edits = diff_tables(base, desired, ctx=CTX)
        deletes = [e for e in edits if isinstance(e, DeleteTableRowEdit)]
        assert len(deletes) == 1
        assert deletes[0].row_index == 1

    def test_delete_first_row(self):
        base = make_table([["a", "b"], ["c", "d"]])
        desired = make_table([["c", "d"]])
        edits = diff_tables(base, desired, ctx=CTX)
        deletes = [e for e in edits if isinstance(e, DeleteTableRowEdit)]
        assert len(deletes) == 1
        assert deletes[0].row_index == 0

    def test_delete_middle_row(self):
        base = make_table([["a", "b"], ["c", "d"], ["e", "f"]])
        desired = make_table([["a", "b"], ["e", "f"]])
        edits = diff_tables(base, desired, ctx=CTX)
        deletes = [e for e in edits if isinstance(e, DeleteTableRowEdit)]
        assert len(deletes) == 1
        assert deletes[0].row_index == 1

    def test_delete_multiple_rows(self):
        base = make_table([["a"], ["b"], ["c"], ["d"], ["e"]])
        desired = make_table([["a"], ["e"]])
        edits = diff_tables(base, desired, ctx=CTX)
        deletes = [e for e in edits if isinstance(e, DeleteTableRowEdit)]
        assert len(deletes) == 3
        # Deletions should be highest index first
        row_indices = [d.row_index for d in deletes]
        assert row_indices == sorted(row_indices, reverse=True)

    def test_no_spurious_inserts_on_delete(self):
        base = make_table([["a", "b"], ["c", "d"], ["e", "f"]])
        desired = make_table([["a", "b"], ["e", "f"]])
        edits = diff_tables(base, desired, ctx=CTX)
        inserts = [e for e in edits if isinstance(e, InsertTableRowEdit)]
        assert inserts == []


class TestDiffTablesColumnInsert:
    def test_add_column_at_end(self):
        base = make_table([["a", "b"], ["c", "d"]])
        desired = make_table([["a", "b", "x"], ["c", "d", "y"]])
        edits = diff_tables(base, desired, ctx=CTX)
        inserts = [e for e in edits if isinstance(e, InsertTableColumnEdit)]
        assert len(inserts) == 1
        ins = inserts[0]
        assert ins.insert_right is True
        assert ins.inserted_cells == ("x", "y")

    def test_add_column_at_beginning(self):
        base = make_table([["b", "c"], ["e", "f"]])
        desired = make_table([["a", "b", "c"], ["d", "e", "f"]])
        edits = diff_tables(base, desired, ctx=CTX)
        inserts = [e for e in edits if isinstance(e, InsertTableColumnEdit)]
        assert len(inserts) == 1
        assert inserts[0].insert_right is False

    def test_add_column_in_middle(self):
        base = make_table([["a", "c"], ["d", "f"]])
        desired = make_table([["a", "b", "c"], ["d", "e", "f"]])
        edits = diff_tables(base, desired, ctx=CTX)
        inserts = [e for e in edits if isinstance(e, InsertTableColumnEdit)]
        assert len(inserts) == 1
        ins = inserts[0]
        assert ins.insert_right is True
        assert ins.inserted_cells == ("b", "e")


class TestDiffTablesColumnDelete:
    def test_delete_last_column(self):
        base = make_table([["a", "b", "c"], ["d", "e", "f"]])
        desired = make_table([["a", "b"], ["d", "e"]])
        edits = diff_tables(base, desired, ctx=CTX)
        deletes = [e for e in edits if isinstance(e, DeleteTableColumnEdit)]
        assert len(deletes) == 1
        assert deletes[0].column_index == 2

    def test_delete_first_column(self):
        base = make_table([["a", "b", "c"], ["d", "e", "f"]])
        desired = make_table([["b", "c"], ["e", "f"]])
        edits = diff_tables(base, desired, ctx=CTX)
        deletes = [e for e in edits if isinstance(e, DeleteTableColumnEdit)]
        assert len(deletes) == 1
        assert deletes[0].column_index == 0

    def test_delete_middle_column(self):
        base = make_table([["a", "b", "c"], ["d", "e", "f"]])
        desired = make_table([["a", "c"], ["d", "f"]])
        edits = diff_tables(base, desired, ctx=CTX)
        deletes = [e for e in edits if isinstance(e, DeleteTableColumnEdit)]
        assert len(deletes) == 1
        assert deletes[0].column_index == 1

    def test_delete_multiple_columns(self):
        """Deleting 2 out of 4 columns from a multi-row table.

        Uses unique cell texts per row so row recall is 2/4=0.5, meeting the
        match threshold.  The algorithm correctly emits column deletions.
        """
        base = make_table([["a", "b", "c", "d"], ["e", "f", "g", "h"]])
        desired = make_table([["a", "d"], ["e", "h"]])
        edits = diff_tables(base, desired, ctx=CTX)
        deletes = [e for e in edits if isinstance(e, DeleteTableColumnEdit)]
        assert len(deletes) == 2
        col_indices = [d.column_index for d in deletes]
        assert col_indices == sorted(col_indices, reverse=True)

    def test_delete_multiple_columns_single_row_convergence(self):
        """For a single-row table with large column reduction, the algorithm may
        use row delete+insert instead of column deletes.  Verify convergence."""
        base = make_table([["a", "b", "c", "d", "e"]])
        desired = make_table([["a", "e"]])
        result, _rounds = _apply_diff_until_convergence(
            _table_to_text_grid(base), _table_to_text_grid(desired)
        )
        assert result == [["a", "e"]]


class TestDiffTablesRowAndColumn:
    def test_add_row_and_column_requires_two_passes(self):
        """Row and column structural changes are NOT emitted simultaneously.

        When both row count and column count change, the first pass handles row
        structural changes only (no column structural edits are emitted).  A
        second pass on the intermediate result produces the column structural edits.
        """
        base = make_table([["a", "b"], ["c", "d"]])
        desired = make_table([["a", "b", "x"], ["c", "d", "y"], ["e", "f", "g"]])
        edits = diff_tables(base, desired, ctx=CTX)
        # First pass: only row structural changes (column structural changes deferred)
        row_inserts = [e for e in edits if isinstance(e, InsertTableRowEdit)]
        col_inserts = [e for e in edits if isinstance(e, InsertTableColumnEdit)]
        assert len(row_inserts) == 1
        assert col_inserts == []  # Column changes deferred to second pass

    def test_add_row_and_column_second_pass(self):
        """Second pass after row insertion produces the column structural edit."""
        desired = make_table([["a", "b", "x"], ["c", "d", "y"], ["e", "f", "g"]])
        # Simulate first pass: add the row
        intermediate = make_table([["a", "b"], ["c", "d"], ["e", "f"]])
        # Second pass: now column count differs, column change emitted
        edits2 = diff_tables(intermediate, desired, ctx=CTX)
        col_inserts = [e for e in edits2 if isinstance(e, InsertTableColumnEdit)]
        assert len(col_inserts) == 1


class TestDiffTablesCellContent:
    def test_cell_content_change_only(self):
        base = make_table([["a", "b"], ["c", "d"]])
        desired = make_table([["a", "CHANGED"], ["c", "d"]])
        edits = diff_tables(base, desired, ctx=CTX)
        structural = [
            e
            for e in edits
            if isinstance(
                e,
                InsertTableRowEdit
                | DeleteTableRowEdit
                | InsertTableColumnEdit
                | DeleteTableColumnEdit,
            )
        ]
        assert structural == []
        content = [e for e in edits if isinstance(e, ReplaceParagraphSliceEdit)]
        assert len(content) == 1

    def test_cell_content_change_and_row_insert(self):
        """When a row is inserted alongside a cell content change, the first pass
        handles the row insertion.  The cell content change on a matched row is
        also emitted in the same pass (it uses positional column matching)."""
        base = make_table([["a", "b"], ["c", "d"]])
        desired = make_table([["a", "CHANGED"], ["c", "d"], ["e", "f"]])
        edits = diff_tables(base, desired, ctx=CTX)
        row_inserts = [e for e in edits if isinstance(e, InsertTableRowEdit)]
        content_edits = [e for e in edits if isinstance(e, ReplaceParagraphSliceEdit)]
        assert len(row_inserts) == 1
        # Cell content change for matched row (row 0 base → row 0 desired, col 1 changed)
        assert len(content_edits) == 1

    def test_no_content_edit_for_inserted_rows(self):
        """Newly inserted rows should not produce cell-content edits."""
        base = make_table([["a", "b"]])
        desired = make_table([["a", "b"], ["c", "d"]])
        edits = diff_tables(base, desired, ctx=CTX)
        content_edits = [e for e in edits if isinstance(e, ReplaceParagraphSliceEdit)]
        assert content_edits == []


class TestDiffTablesLargeTable:
    def test_large_table_delete_middle_row(self):
        """8x5 table -- delete row 4 (0-indexed)."""
        rows = [[f"r{r}c{c}" for c in range(5)] for r in range(8)]
        base = make_table(rows)
        desired_rows = [rows[i] for i in range(8) if i != 4]
        desired = make_table(desired_rows)
        edits = diff_tables(base, desired, ctx=CTX)
        deletes = [e for e in edits if isinstance(e, DeleteTableRowEdit)]
        assert len(deletes) == 1
        assert deletes[0].row_index == 4

    def test_large_table_insert_middle_column(self):
        """5x8 table -- insert a column at position 3."""
        rows = [[f"r{r}c{c}" for c in range(8)] for r in range(5)]
        base = make_table(rows)
        # Insert a new column at index 3 in desired
        desired_rows = [[*row[:3], "NEW", *row[3:]] for row in rows]
        desired = make_table(desired_rows)
        edits = diff_tables(base, desired, ctx=CTX)
        inserts = [e for e in edits if isinstance(e, InsertTableColumnEdit)]
        assert len(inserts) == 1
        ins = inserts[0]
        assert ins.insert_right is True
        assert ins.inserted_cells == tuple(["NEW"] * 5)


class TestDiffTablesHashCollision:
    def test_identical_cell_text_columns(self):
        """Table where multiple cells have the same text."""
        base = make_table([["x", "x", "x"], ["y", "y", "y"]])
        desired = make_table([["x", "x", "x"], ["y", "y", "y"]])
        edits = diff_tables(base, desired, ctx=CTX)
        structural = [
            e
            for e in edits
            if isinstance(
                e,
                InsertTableRowEdit
                | DeleteTableRowEdit
                | InsertTableColumnEdit
                | DeleteTableColumnEdit,
            )
        ]
        assert structural == []

    def test_all_empty_cells(self):
        base = make_table([["", ""], ["", ""]])
        desired = make_table([["", ""], ["", ""]])
        edits = diff_tables(base, desired, ctx=CTX)
        structural = [
            e
            for e in edits
            if isinstance(
                e,
                InsertTableRowEdit
                | DeleteTableRowEdit
                | InsertTableColumnEdit
                | DeleteTableColumnEdit,
            )
        ]
        assert structural == []

    def test_add_row_all_empty(self):
        """Add a row of empty cells to an all-empty table."""
        base = make_table([["", ""], ["", ""]])
        desired = make_table([["", ""], ["", ""], ["", ""]])
        edits = diff_tables(base, desired, ctx=CTX)
        # The new row has same hash as existing rows, so LCS picks 2 anchors
        # and the third row is inserted. Row/col structural edit count: 1 insert.
        inserts = [e for e in edits if isinstance(e, InsertTableRowEdit)]
        assert len(inserts) == 1

    def test_delete_row_all_empty(self):
        """Delete one row from an all-empty table."""
        base = make_table([["", ""], ["", ""], ["", ""]])
        desired = make_table([["", ""], ["", ""]])
        edits = diff_tables(base, desired, ctx=CTX)
        deletes = [e for e in edits if isinstance(e, DeleteTableRowEdit)]
        assert len(deletes) == 1


# ---------------------------------------------------------------------------
# Context propagation tests
# ---------------------------------------------------------------------------


class TestDiffTablesContext:
    def test_context_propagated(self):
        ctx = TableDiffContext(tab_id="mytab", section_index=3, block_index=7)
        base = make_table([["a", "b"]])
        desired = make_table([["a", "b"], ["c", "d"]])
        edits = diff_tables(base, desired, ctx=ctx)
        for edit in edits:
            assert edit.tab_id == "mytab"
            assert edit.section_index == 3
            assert edit.block_index == 7

    def test_default_context_used(self):
        base = make_table([["a"]])
        desired = make_table([["a"], ["b"]])
        edits = diff_tables(base, desired)
        # Should not raise; uses placeholder context
        assert len(edits) > 0


# ---------------------------------------------------------------------------
# Fuzz / property-based tests
# ---------------------------------------------------------------------------


def _apply_edits_to_table(table: TableIR, edits: list) -> TableIR:
    """Apply structural edits to a TableIR in-memory to verify diff correctness.

    Only handles the structural edit types (row/column insert/delete) and
    cell content replacements.  Mirrors what the Google Docs API would do.

    Note on cell-content edits: story_id encodes base row/col indices (pre-structural-change).
    Since all deletions are emitted first (highest-index-first) and all insertions after,
    the base indices in story_id still refer to correct post-deletion positions.
    """
    # Convert to mutable 2D representation
    cells: list[list[str]] = [
        [cell_text_hash(cell) for cell in row.cells] for row in table.rows
    ]

    for edit in edits:
        if isinstance(edit, DeleteTableRowEdit):
            if 0 <= edit.row_index < len(cells):
                cells.pop(edit.row_index)
        elif isinstance(edit, InsertTableRowEdit):
            insert_at = edit.row_index + 1 if edit.insert_below else edit.row_index
            if not cells:
                new_row = list(edit.inserted_cells) if edit.inserted_cells else []
            else:
                new_row = (
                    list(edit.inserted_cells)
                    if edit.inserted_cells
                    else [""] * len(cells[0])
                )
            cells.insert(insert_at, new_row)
        elif isinstance(edit, DeleteTableColumnEdit):
            for row in cells:
                if 0 <= edit.column_index < len(row):
                    row.pop(edit.column_index)
        elif isinstance(edit, InsertTableColumnEdit):
            if edit.insert_right:
                insert_at = edit.column_index + 1
            else:
                insert_at = edit.column_index
            col_cells = (
                list(edit.inserted_cells) if edit.inserted_cells else [""] * len(cells)
            )
            for row_idx, row in enumerate(cells):
                val = col_cells[row_idx] if row_idx < len(col_cells) else ""
                row.insert(insert_at, val)
        elif isinstance(edit, ReplaceParagraphSliceEdit):
            # Parse "r{row}:c{col}" from story_id (these are BASE row/col indices,
            # but since deletions happen first and we track the current cell array,
            # we need to apply in order with proper state tracking)
            parts = edit.story_id.split(":")
            row_part = next((p for p in parts if p.startswith("r")), None)
            col_part = next((p for p in parts if p.startswith("c")), None)
            if row_part and col_part:
                row_idx = int(row_part[1:])
                col_idx = int(col_part[1:])
                text = "".join(
                    frag.paragraph.inlines[0].text
                    for frag in edit.inserted_paragraphs
                    if frag.paragraph.inlines
                    and isinstance(frag.paragraph.inlines[0], TextSpanIR)
                )
                if 0 <= row_idx < len(cells) and 0 <= col_idx < len(cells[row_idx]):
                    cells[row_idx][col_idx] = text

    return make_table(cells)


def _table_to_text_grid(table: TableIR) -> list[list[str]]:
    return [[cell_text_hash(cell) for cell in row.cells] for row in table.rows]


def _random_table(
    rng: random.Random, rows: int, cols: int, vocab: list[str]
) -> list[list[str]]:
    return [[rng.choice(vocab) for _ in range(cols)] for _ in range(rows)]


def _apply_random_mutations(
    rng: random.Random,
    grid: list[list[str]],
    n_mutations: int,
    vocab: list[str],
) -> list[list[str]]:
    """Apply n_mutations random structural/content changes to the grid."""
    import copy

    g = copy.deepcopy(grid)
    ops = ["insert_row", "delete_row", "insert_col", "delete_col", "edit_cell"]

    for _ in range(n_mutations):
        if not g or not g[0]:
            # Rebuild a minimal table if everything was deleted
            g = _random_table(rng, 2, 2, vocab)
            continue
        rows = len(g)
        cols = len(g[0])
        op = rng.choice(ops)
        if op == "insert_row":
            new_row = [rng.choice(vocab) for _ in range(cols)]
            pos = rng.randint(0, rows)
            g.insert(pos, new_row)
        elif op == "delete_row" and rows > 1:
            pos = rng.randint(0, rows - 1)
            g.pop(pos)
        elif op == "insert_col":
            new_col = [rng.choice(vocab) for _ in range(len(g))]
            pos = rng.randint(0, cols)
            for i, row in enumerate(g):
                row.insert(pos, new_col[i])
        elif op == "delete_col" and cols > 1:
            pos = rng.randint(0, cols - 1)
            for row in g:
                row.pop(pos)
        elif op == "edit_cell":
            r = rng.randint(0, rows - 1)
            c = rng.randint(0, cols - 1)
            g[r][c] = rng.choice(vocab)
    return g


def _apply_diff_until_convergence(
    base_grid: list[list[str]],
    desired_grid: list[list[str]],
    *,
    max_rounds: int = 10,
) -> tuple[list[list[str]], int]:
    """Iteratively apply diff_tables until base_grid == desired_grid or max_rounds.

    Returns (final_grid, rounds_taken).
    """
    current = make_table(base_grid)
    desired = make_table(desired_grid)
    for round_num in range(max_rounds):
        current_grid = _table_to_text_grid(current)
        if current_grid == desired_grid:
            return current_grid, round_num
        edits = diff_tables(current, desired, ctx=CTX)
        if not edits:
            break  # No progress possible
        current = _apply_edits_to_table(current, edits)
    return _table_to_text_grid(current), max_rounds


class TestFuzz:
    """Property-based fuzz tests: apply random mutations and verify diff round-trip.

    Since diff_tables handles only one structural dimension (rows OR columns) per pass,
    the fuzz tests use iterative convergence: apply diffs until the table matches the
    desired state or a round limit is reached.  The round limit catches algorithmic
    bugs that would cause infinite loops (no-progress cases).
    """

    def test_fuzz_200_cases(self):
        """Run 200 random mutation scenarios with iterative convergence."""
        rng = random.Random(42)
        # Small vocabulary to create hash collisions that stress the LCS
        vocab = [f"w{i}" for i in range(8)]
        failures: list[str] = []

        for case_idx in range(200):
            # Random starting table (2-5 rows, 2-4 cols)
            rows = rng.randint(2, 5)
            cols = rng.randint(2, 4)
            base_grid = _random_table(rng, rows, cols, vocab)

            # Apply 1-3 random mutations
            n_mut = rng.randint(1, 3)
            desired_grid = _apply_random_mutations(rng, base_grid, n_mut, vocab)

            if not desired_grid or not desired_grid[0]:
                continue  # skip degenerate cases

            result_grid, rounds = _apply_diff_until_convergence(base_grid, desired_grid)

            if result_grid != desired_grid:
                failures.append(
                    f"Case {case_idx} ({rounds} rounds): "
                    f"base={base_grid} desired={desired_grid} result={result_grid}"
                )

        if failures:
            summary = "\n".join(failures[:5])
            if len(failures) > 5:
                summary += f"\n... and {len(failures) - 5} more"
            pytest.fail(f"{len(failures)}/200 fuzz cases failed:\n{summary}")

    def test_fuzz_no_change_200_cases(self):
        """Verify that diffing identical tables always returns zero structural edits."""
        rng = random.Random(123)
        vocab = [f"v{i}" for i in range(6)]

        for _ in range(200):
            rows = rng.randint(1, 6)
            cols = rng.randint(1, 5)
            grid = _random_table(rng, rows, cols, vocab)
            t = make_table(grid)
            edits = diff_tables(t, t, ctx=CTX)
            structural = [
                e
                for e in edits
                if isinstance(
                    e,
                    InsertTableRowEdit
                    | DeleteTableRowEdit
                    | InsertTableColumnEdit
                    | DeleteTableColumnEdit,
                )
            ]
            assert (
                structural == []
            ), f"Expected no structural edits for identical table, got {structural}"
