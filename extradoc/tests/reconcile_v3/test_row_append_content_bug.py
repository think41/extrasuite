"""Regression tests for table row append populating new-row cell content.

Bug: when a new row is appended to an existing table, the reconciler emits an
``insertTableRow`` request (correctly creating an empty row) but does NOT emit
any ``insertText`` request to populate the newly-created cells with the user's
desired text. Result: new row shows up empty in the live doc.

These tests assert directly on the lowered requests (not via the mock).
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

from .helpers import make_indexed_terminal, make_para_el, make_terminal_para
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


def _make_base_2x2_table_at(table_start: int) -> tuple[StructuralElement, int]:
    """Build a 2x2 table [A1|B1 / A2|B2] starting at table_start.

    Layout (each cell = 1 overhead + "X\\n" (3 chars) + "\\n" (1 char) = 5 chars;
    each row = 1 overhead + 2*5 = 11 chars; table = 2 rows * 11 = 22 chars):

      table.start = S, end = S + 22
      row0.start  = S+1,  end = S+12
        c0: start=S+2, p1=[S+3,S+6), p2=[S+6,S+7), end=S+7
        c1: start=S+7, p1=[S+8,S+11), p2=[S+11,S+12), end=S+12
      row1.start  = S+12, end = S+23
        c0: start=S+13, p1=[S+14,S+17), p2=[S+17,S+18), end=S+18
        c1: start=S+18, p1=[S+19,S+22), p2=[S+22,S+23), end=S+23

    Returns the StructuralElement plus the end_index of the table (= S+23).
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


def _find_insert_texts(requests: list[dict]) -> list[tuple[int, str]]:
    out = []
    for r in requests:
        if "insertText" in r:
            it = r["insertText"]
            out.append((it["location"]["index"], it["text"]))
    return out


# ---------------------------------------------------------------------------


def test_append_single_row_populates_new_cells_2x1() -> None:
    """Base: 2 rows x 1 col. Desired: 3 rows (add row 'C'). Should insert 'C'."""
    # Table at index 1. Each cell = 1 overhead + "X\n"(2) + "\n"(1) = 4 chars.
    # Actually with 1-char text + \n = 2. Let's rebuild.
    # For simplicity, build a 2x1 table manually with indices.
    s = 1
    cell_size = 4  # 1 overhead + "A\n"(2) + "\n"(1)
    row_size = 1 + cell_size  # 1 row overhead

    def _cell1(t: str, *, start: int) -> TableCell:
        return TableCell(
            start_index=start,
            end_index=start + cell_size,
            content=[
                StructuralElement(
                    start_index=start + 1,
                    end_index=start + 3,
                    paragraph=Paragraph(
                        elements=[ParagraphElement(text_run=TextRun(content=t + "\n"))],
                        paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                    ),
                ),
                StructuralElement(
                    start_index=start + 3,
                    end_index=start + 4,
                    paragraph=Paragraph(
                        elements=[ParagraphElement(text_run=TextRun(content="\n"))],
                        paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                    ),
                ),
            ],
        )

    r0 = TableRow(
        start_index=s + 1,
        end_index=s + 1 + cell_size,
        table_cells=[_cell1("A", start=s + 2)],
    )
    r1 = TableRow(
        start_index=s + 1 + cell_size,
        end_index=s + 1 + 2 * cell_size,
        table_cells=[_cell1("B", start=s + 2 + cell_size)],
    )
    table_size = 1 + 2 * row_size  # = 1 + 2*5 = 11
    table_el = StructuralElement(
        start_index=s,
        end_index=s + table_size,
        table=Table(table_rows=[r0, r1], columns=1, rows=2),
    )
    terminal = make_indexed_terminal(s + table_size)
    base = make_indexed_doc(body_content=[table_el, terminal])

    desired_table = _desired_table([["A"], ["B"], ["C"]])
    desired = make_indexed_doc(
        body_content=[desired_table, make_terminal_para()],
    )

    batches = reconcile_batches(base, desired)
    reqs = _collect_requests(batches)

    # Assert: exactly one insertTableRow was emitted
    row_inserts = [r for r in reqs if "insertTableRow" in r]
    assert len(row_inserts) == 1, f"expected 1 insertTableRow, got {row_inserts}"

    # Assert: one insertText containing "C" to populate the new row's cell
    text_inserts = _find_insert_texts(reqs)
    c_inserts = [t for idx, t in text_inserts if "C" in t]
    assert c_inserts, (
        f"expected an insertText containing 'C' to populate new row cell, "
        f"got text inserts: {text_inserts}"
    )


def test_append_single_row_populates_new_cells_2x2() -> None:
    """Base: 2x2 [A1/B1; A2/B2]. Desired: 3x2 adding [A3/B3]. Both must land."""
    table_el, table_end = _make_base_2x2_table_at(table_start=1)
    terminal = make_indexed_terminal(table_end)
    base = make_indexed_doc(body_content=[table_el, terminal])

    desired_table = _desired_table([["A1", "B1"], ["A2", "B2"], ["A3", "B3"]])
    desired = make_indexed_doc(
        body_content=[desired_table, make_terminal_para()],
    )

    batches = reconcile_batches(base, desired)
    reqs = _collect_requests(batches)

    row_inserts = [r for r in reqs if "insertTableRow" in r]
    assert len(row_inserts) == 1, f"expected 1 insertTableRow, got {row_inserts}"

    text_inserts = _find_insert_texts(reqs)
    a3_hits = [(idx, t) for idx, t in text_inserts if "A3" in t]
    b3_hits = [(idx, t) for idx, t in text_inserts if "B3" in t]
    assert a3_hits, f"missing insertText for 'A3'; text inserts: {text_inserts}"
    assert b3_hits, f"missing insertText for 'B3'; text inserts: {text_inserts}"

    # After insertTableRow the new row begins at byte 24 (base table_end = 24).
    # Each empty cell is 2 bytes (1 cell overhead + 1 "\n" paragraph) because
    # ``insertTableRow`` creates cells with a single paragraph each.
    # Row overhead = 1, cell 0 overhead = 1 → A3 p1 = 24 + 1 + 0*2 + 1 = 26.
    # Cell 1: B3 p1 = 24 + 1 + 1*2 + 1 = 28.
    a3_idx = a3_hits[0][0]
    b3_idx = b3_hits[0][0]
    assert a3_idx == 26, f"A3 insertText should target index 26, got {a3_idx}"
    assert b3_idx == 28, f"B3 insertText should target index 28, got {b3_idx}"


def test_append_two_rows_populates_all_cells_2x2() -> None:
    """Base: 2x2 [A1|B1 / A2|B2]. Desired: 4x2 adding rows [A3|B3, A4|B4].
    BOTH new rows must be populated.
    """
    table_el, table_end = _make_base_2x2_table_at(table_start=1)
    terminal = make_indexed_terminal(table_end)
    base = make_indexed_doc(body_content=[table_el, terminal])

    desired_table = _desired_table(
        [["A1", "B1"], ["A2", "B2"], ["A3", "B3"], ["A4", "B4"]]
    )
    desired = make_indexed_doc(
        body_content=[desired_table, make_terminal_para()],
    )

    batches = reconcile_batches(base, desired)
    reqs = _collect_requests(batches)

    row_inserts = [r for r in reqs if "insertTableRow" in r]
    assert len(row_inserts) == 2, f"expected 2 insertTableRow, got {row_inserts}"

    text_inserts = _find_insert_texts(reqs)
    all_texts = [t for _, t in text_inserts]
    for expected in ("A3", "B3", "A4", "B4"):
        assert any(t == expected for t in all_texts), (
            f"missing insertText for {expected!r}; text inserts: {text_inserts}"
        )


def test_append_three_rows_populates_all_cells_2x2() -> None:
    """Base 2x2; append 3 new rows. All new cells populated."""
    table_el, table_end = _make_base_2x2_table_at(table_start=1)
    terminal = make_indexed_terminal(table_end)
    base = make_indexed_doc(body_content=[table_el, terminal])

    desired_table = _desired_table(
        [
            ["A1", "B1"],
            ["A2", "B2"],
            ["A3", "B3"],
            ["A4", "B4"],
            ["A5", "B5"],
        ]
    )
    desired = make_indexed_doc(
        body_content=[desired_table, make_terminal_para()],
    )

    batches = reconcile_batches(base, desired)
    reqs = _collect_requests(batches)

    row_inserts = [r for r in reqs if "insertTableRow" in r]
    assert len(row_inserts) == 3

    text_inserts = _find_insert_texts(reqs)
    all_texts = [t for _, t in text_inserts]
    for expected in ("A3", "B3", "A4", "B4", "A5", "B5"):
        assert any(t == expected for t in all_texts), (
            f"missing insertText for {expected!r}; text inserts: {text_inserts}"
        )


def test_append_row_and_column_populates_all_cells_2x2() -> None:
    """Base 2x2; desired 3x3 = add one new row AND one new column.
    Both new structures must have their cells populated.
    """
    table_el, table_end = _make_base_2x2_table_at(table_start=1)
    terminal = make_indexed_terminal(table_end)
    base = make_indexed_doc(body_content=[table_el, terminal])

    desired_table = _desired_table(
        [["A1", "B1", "C1"], ["A2", "B2", "C2"], ["A3", "B3", "C3"]]
    )
    desired = make_indexed_doc(
        body_content=[desired_table, make_terminal_para()],
    )

    batches = reconcile_batches(base, desired)
    reqs = _collect_requests(batches)

    # The table diff may represent 2x2→3x3 as (1 row + 1 col) OR as pure
    # column inserts (depending on LCS matching); we don't care which shape
    # the structural ops take, only that every new cell text lands.
    row_inserts = [r for r in reqs if "insertTableRow" in r]
    col_inserts = [r for r in reqs if "insertTableColumn" in r]
    assert row_inserts or col_inserts, "expected at least one structural table op"

    text_inserts = _find_insert_texts(reqs)
    all_texts = [t for _, t in text_inserts]
    for expected in ("C1", "C2", "A3", "B3", "C3"):
        assert any(t == expected for t in all_texts), (
            f"missing insertText for {expected!r}; text inserts: {text_inserts}"
        )


def test_append_row_alongside_matched_cell_edits() -> None:
    """Base 2x2; desired edits A1 AND adds a new row. Both land correctly.

    Simulates the real-world S8 failure mode: one row appended while matched
    cells in earlier rows have their content updated in the same push.
    """
    table_el, table_end = _make_base_2x2_table_at(table_start=1)
    terminal = make_indexed_terminal(table_end)
    base = make_indexed_doc(body_content=[table_el, terminal])

    # Desired: edit cell (0,0) to "A1_new" and append row (A3, B3)
    desired_table = _desired_table([["A1_new", "B1"], ["A2", "B2"], ["A3", "B3"]])
    desired = make_indexed_doc(
        body_content=[desired_table, make_terminal_para()],
    )

    batches = reconcile_batches(base, desired)
    reqs = _collect_requests(batches)

    row_inserts = [r for r in reqs if "insertTableRow" in r]
    assert len(row_inserts) == 1

    text_inserts = _find_insert_texts(reqs)
    all_texts = [t for _, t in text_inserts]
    assert any("A3" in t for t in all_texts), f"missing A3: {all_texts}"
    assert any("B3" in t for t in all_texts), f"missing B3: {all_texts}"
    # The matched-cell update machinery may emit just the DIFF fragment
    # ("_new") rather than the full new text ("A1_new"); either form is fine
    # as long as the "_new" suffix lands in the stream.
    assert any("_new" in t for t in all_texts), f"missing A1 edit: {all_texts}"
