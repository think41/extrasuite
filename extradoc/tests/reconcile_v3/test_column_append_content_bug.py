"""Regression tests for table column append populating new-column cell content.

Bug: when a new column is appended to an existing table, the reconciler emits
an ``insertTableColumn`` request (correctly creating an empty column) but does
NOT emit any ``insertText`` request to populate the newly-created cells with
the user's desired text. Result: new column shows up empty in the live doc.

These tests assert directly on the lowered requests (not via the mock).

Companion to ``test_row_append_content_bug.py``; the column case differs in
that the new cells are scattered across rows (one per row) rather than
contiguous within a single row.
"""

from __future__ import annotations

from extradoc.api_types._generated import (
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    StructuralElement,
    Table,
    TableCell,
    TableRow,
    TextRun,
)
from extradoc.reconcile_v3.api import reconcile_batches

from .helpers import (
    make_indexed_para,
    make_indexed_terminal,
    make_para_el,
    make_terminal_para,
)
from .test_lower import make_indexed_doc


def _cell(
    text: str,
    *,
    start: int,
    p1_start: int,
    p2_start: int,
    end: int,
) -> TableCell:
    """Cell with two paragraphs (text + trailing \\n), with explicit indices."""
    return TableCell(
        start_index=start,
        end_index=end,
        content=[
            StructuralElement(
                start_index=p1_start,
                end_index=p1_start + len(text) + 1,
                paragraph=Paragraph(
                    elements=[ParagraphElement(text_run=TextRun(content=text + "\n"))],
                    paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                ),
            ),
            StructuralElement(
                start_index=p2_start,
                end_index=p2_start + 1,
                paragraph=Paragraph(
                    elements=[ParagraphElement(text_run=TextRun(content="\n"))],
                    paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                ),
            ),
        ],
    )


def _collect_requests(batches):
    out = []
    for batch in batches:
        for req in batch.requests or []:
            d = req.model_dump(by_alias=True, exclude_none=True)
            out.append(d)
    return out


def _find_insert_texts(requests: list[dict]) -> list[tuple[int, str]]:
    out = []
    for r in requests:
        if "insertText" in r:
            it = r["insertText"]
            out.append((it["location"]["index"], it["text"]))
    return out


def _make_base_2x2_table_at(table_start: int) -> tuple[StructuralElement, int]:
    """Build a 2x2 table [A1|B1 / A2|B2] starting at table_start.

    Layout (same as the row-append regression test):

      cell = 1 overhead + "X\\n" (3 bytes) + "\\n" (1 byte) = 5 bytes
      row  = 1 overhead + 2 * 5 = 11 bytes
      table = 2 * 11 = 22 bytes, so table.end = table_start + 22

      table.start = S, end = S + 23  (indices: table covers S..S+22 inclusive,
                                       end = S + 23 is exclusive)
      row0: start=S+1  end=S+12
        cell0: start=S+2,  end=S+7   (p1=[S+3,S+6), p2=[S+6,S+7))
        cell1: start=S+7,  end=S+12  (p1=[S+8,S+11), p2=[S+11,S+12))
      row1: start=S+12 end=S+23
        cell0: start=S+13, end=S+18  (p1=[S+14,S+17), p2=[S+17,S+18))
        cell1: start=S+18, end=S+23  (p1=[S+19,S+22), p2=[S+22,S+23))
    """
    s = table_start
    row0 = TableRow(
        start_index=s + 1,
        end_index=s + 12,
        table_cells=[
            _cell("A1", start=s + 2, p1_start=s + 3, p2_start=s + 6, end=s + 7),
            _cell("B1", start=s + 7, p1_start=s + 8, p2_start=s + 11, end=s + 12),
        ],
    )
    row1 = TableRow(
        start_index=s + 12,
        end_index=s + 23,
        table_cells=[
            _cell("A2", start=s + 13, p1_start=s + 14, p2_start=s + 17, end=s + 18),
            _cell("B2", start=s + 18, p1_start=s + 19, p2_start=s + 22, end=s + 23),
        ],
    )
    table_el = StructuralElement(
        start_index=s,
        end_index=s + 23,
        table=Table(table_rows=[row0, row1], columns=2, rows=2),
    )
    return table_el, s + 23


def _make_base_1x2_table_at(table_start: int) -> tuple[StructuralElement, int]:
    """Build a 1x2 table [A1|B1] starting at table_start. Same layout as 2x2."""
    s = table_start
    row0 = TableRow(
        start_index=s + 1,
        end_index=s + 12,
        table_cells=[
            _cell("A1", start=s + 2, p1_start=s + 3, p2_start=s + 6, end=s + 7),
            _cell("B1", start=s + 7, p1_start=s + 8, p2_start=s + 11, end=s + 12),
        ],
    )
    table_el = StructuralElement(
        start_index=s,
        end_index=s + 12,
        table=Table(table_rows=[row0], columns=2, rows=1),
    )
    return table_el, s + 12


def _desired_cell(text: str) -> TableCell:
    return TableCell(content=[make_para_el(text + "\n"), make_terminal_para()])


def _desired_table(rows: list[list[str]]) -> StructuralElement:
    return StructuralElement(
        table=Table(
            table_rows=[
                TableRow(table_cells=[_desired_cell(t) for t in row]) for row in rows
            ],
            columns=len(rows[0]),
            rows=len(rows),
        )
    )


# ---------------------------------------------------------------------------


def test_append_single_column_populates_new_cells_1x2() -> None:
    """Base: 1 row x 2 cols. Desired: 1x3 (append 'C1'). Should insert 'C1'."""
    table_el, _ = _make_base_1x2_table_at(table_start=1)
    terminal = make_indexed_terminal(1 + 12)
    base = make_indexed_doc(body_content=[table_el, terminal])

    desired_table = _desired_table([["A1", "B1", "C1"]])
    desired = make_indexed_doc(
        body_content=[desired_table, make_terminal_para()],
    )

    batches = reconcile_batches(base, desired)
    reqs = _collect_requests(batches)

    col_inserts = [r for r in reqs if "insertTableColumn" in r]
    assert len(col_inserts) == 1, f"expected 1 insertTableColumn, got {col_inserts}"

    text_inserts = _find_insert_texts(reqs)
    c1_hits = [(idx, t) for idx, t in text_inserts if "C1" in t]
    assert c1_hits, (
        f"expected an insertText containing 'C1' to populate new column cell, "
        f"got text inserts: {text_inserts}"
    )

    # Table starts at S=1. Base row0.cell1 (B1).end = S+12 = 13. With
    # insert_right=True the new cell begins exactly at 13; its single "\n"
    # paragraph is at 13 + 0*2 + 1 = 14.
    c1_idx = c1_hits[0][0]
    assert c1_idx == 14, f"C1 insertText should target index 14, got {c1_idx}"


def test_append_single_column_populates_new_cells_2x2() -> None:
    """Base: 2x2 [A1|B1 / A2|B2]. Desired: 2x3 adding column [C1, C2]."""
    table_el, table_end = _make_base_2x2_table_at(table_start=1)
    terminal = make_indexed_terminal(table_end)
    base = make_indexed_doc(body_content=[table_el, terminal])

    desired_table = _desired_table([["A1", "B1", "C1"], ["A2", "B2", "C2"]])
    desired = make_indexed_doc(
        body_content=[desired_table, make_terminal_para()],
    )

    batches = reconcile_batches(base, desired)
    reqs = _collect_requests(batches)

    col_inserts = [r for r in reqs if "insertTableColumn" in r]
    assert len(col_inserts) == 1, f"expected 1 insertTableColumn, got {col_inserts}"

    text_inserts = _find_insert_texts(reqs)
    c1_hits = [(idx, t) for idx, t in text_inserts if "C1" in t]
    c2_hits = [(idx, t) for idx, t in text_inserts if "C2" in t]
    assert c1_hits, f"missing insertText for 'C1'; text inserts: {text_inserts}"
    assert c2_hits, f"missing insertText for 'C2'; text inserts: {text_inserts}"

    # Table starts at S=1. Base row0.cell1 (B1).end = S+12 = 13 →
    #   row0 new cell p1 at 13 + 0*2 + 1 = 14.
    # Base row1.cell1 (B2).end = S+23 = 24 →
    #   row1 new cell p1 at 24 + 1*2 + 1 = 27.
    c1_idx = c1_hits[0][0]
    c2_idx = c2_hits[0][0]
    assert c1_idx == 14, f"C1 insertText should target index 14, got {c1_idx}"
    assert c2_idx == 27, f"C2 insertText should target index 27, got {c2_idx}"


def test_append_two_columns_populates_first_only_2x2() -> None:
    """Base 2x2; desired adds TWO new columns. The FIRST-emitted structural
    insertTableColumn populates its cells; the SECOND is guarded and leaves
    its cells empty.

    Documents the scope of the fix: when multiple column inserts hit the
    same table in one push, only the first gets its cells populated —
    because subsequent ops' BASE anchor indices are stale by then
    (intermediate structural + variable-length text inserts have shifted
    per-row cell boundaries by amounts we can't reconstruct cleanly at
    lower time). The user can rerun push on the still-empty cells and
    they'll be populated by matched-cell content alignment.

    This matches the scope of ``InsertTableRowOp``'s analogous cell-text
    fix (single-row-append only).
    """
    table_el, table_end = _make_base_2x2_table_at(table_start=1)
    terminal = make_indexed_terminal(table_end)
    base = make_indexed_doc(body_content=[table_el, terminal])

    desired_table = _desired_table(
        [["A1", "B1", "C1", "D1"], ["A2", "B2", "C2", "D2"]]
    )
    desired = make_indexed_doc(
        body_content=[desired_table, make_terminal_para()],
    )

    batches = reconcile_batches(base, desired)
    reqs = _collect_requests(batches)

    col_inserts = [r for r in reqs if "insertTableColumn" in r]
    assert len(col_inserts) == 2, (
        f"expected 2 insertTableColumn, got {len(col_inserts)}"
    )

    text_inserts = _find_insert_texts(reqs)
    # The first-emitted op populates its row of cells. The LCS-driven emit
    # order pairs the first-emitted op with the RIGHTMOST desired column
    # (column ops are emitted in reverse desired order within an anchor
    # group), so its texts are "D1"/"D2"/Col D's header — collectively the
    # tokens ending in "1" and "2" that start with the rightmost header.
    # We assert that AT LEAST one column's worth of cell texts landed.
    populated_columns = 0
    for pair in (("C1", "C2"), ("D1", "D2")):
        if all(any(t == exp for _, t in text_inserts) for exp in pair):
            populated_columns += 1
    assert populated_columns >= 1, (
        f"expected at least one new column to be populated; text inserts: "
        f"{text_inserts}"
    )


def test_append_column_alongside_paragraph_edit() -> None:
    """Base 2x2 with a paragraph before it; desired edits that paragraph AND
    appends a new column [C1,C2].

    Mirrors the row-append combined edit scenario: a structural column insert
    paired with an unrelated text edit in the same push. Both changes must
    land. The edit lives OUTSIDE the table so the column LCS is not perturbed
    and the safety guard does not engage.
    """
    # Base: paragraph "Intro\n" at [1,7), table at [7, 7+23), terminal at 30.
    intro = make_indexed_para("Intro\n", start=1)
    table_el, table_end = _make_base_2x2_table_at(table_start=7)
    terminal = make_indexed_terminal(table_end)
    base = make_indexed_doc(body_content=[intro, table_el, terminal])

    # Desired: edit intro paragraph + append column (C1, C2).
    desired_table = _desired_table([["A1", "B1", "C1"], ["A2", "B2", "C2"]])
    desired = make_indexed_doc(
        body_content=[
            make_para_el("Intro_edited\n"),
            desired_table,
            make_terminal_para(),
        ],
    )

    batches = reconcile_batches(base, desired)
    reqs = _collect_requests(batches)

    col_inserts = [r for r in reqs if "insertTableColumn" in r]
    col_deletes = [r for r in reqs if "deleteTableColumn" in r]
    # Exactly one column insert, no column deletes — the safety guard must
    # therefore NOT engage, so cell-text inserts for the new column must land.
    assert len(col_inserts) == 1, (
        f"expected 1 insertTableColumn, got {len(col_inserts)}: {col_inserts}"
    )
    assert not col_deletes, f"unexpected deleteTableColumn: {col_deletes}"

    text_inserts = _find_insert_texts(reqs)
    all_texts = [t for _, t in text_inserts]
    assert any("C1" in t for t in all_texts), f"missing C1: {all_texts}"
    assert any("C2" in t for t in all_texts), f"missing C2: {all_texts}"
    # Matched-cell update machinery may emit the full text or just the diff
    # fragment — either form is fine as long as "_edited" lands somewhere.
    assert any("_edited" in t for t in all_texts), (
        f"missing Intro edit: {all_texts}"
    )
