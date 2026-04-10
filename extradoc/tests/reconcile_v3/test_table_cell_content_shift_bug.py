"""Regression tests for table cell content ops using stale BASE indices when
table-structural ops (deleteTableRow) precede them in the batch.

Bug: when rows are deleted from a table AND cell content is modified in
surviving rows, the cell content update ops (UpdateBodyContentOp with
story_kind="table_cell") would produce insertText/deleteContentRange requests
using BASE document indices. But deleteTableRow requests that execute earlier
in the same batch shrink the document, making those BASE indices stale. The
API rejected with:

    "Index X must be less than the end index of the referenced segment, Y."

Fix: ``_lower_story_content_update`` now shifts table-cell base content
elements by the cumulative body-level delta from prior requests in the batch
(including ``deleteTableRow`` byte removals recorded as struct_events).
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
from extradoc.indexer import utf16_len
from extradoc.reconcile_v3.api import reconcile_batches

from .helpers import (
    make_indexed_doc,
    make_indexed_para,
    make_indexed_terminal,
    make_para_el,
    make_terminal_para,
)

# ---------------------------------------------------------------------------
# Table builder helpers
# ---------------------------------------------------------------------------


def _indexed_cell(text: str, *, start: int) -> TableCell:
    tlen = utf16_len(text)
    p1_start = start + 1
    p1_end = p1_start + tlen + 1
    p2_start = p1_end
    p2_end = p2_start + 1
    return TableCell(
        start_index=start,
        end_index=p2_end,
        content=[
            StructuralElement(
                start_index=p1_start,
                end_index=p1_end,
                paragraph=Paragraph(
                    elements=[ParagraphElement(text_run=TextRun(content=text + "\n"))],
                    paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                ),
            ),
            StructuralElement(
                start_index=p2_start,
                end_index=p2_end,
                paragraph=Paragraph(
                    elements=[ParagraphElement(text_run=TextRun(content="\n"))],
                    paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
                ),
            ),
        ],
    )


def _cell_size(text: str) -> int:
    return 1 + utf16_len(text) + 1 + 1


def _row_size(texts: list[str]) -> int:
    return 1 + sum(_cell_size(t) for t in texts)


def _make_indexed_table(
    rows: list[list[str]], table_start: int
) -> tuple[StructuralElement, int]:
    pos = table_start
    table_rows = []
    for row_texts in rows:
        row_start = pos
        pos += 1
        cells = []
        for text in row_texts:
            cell = _indexed_cell(text, start=pos)
            cells.append(cell)
            pos += _cell_size(text)
        table_rows.append(
            TableRow(start_index=row_start, end_index=pos, table_cells=cells)
        )
    table_el = StructuralElement(
        start_index=table_start,
        end_index=pos,
        table=Table(
            table_rows=table_rows,
            columns=len(rows[0]) if rows else 0,
            rows=len(rows),
        ),
    )
    return table_el, pos


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
# Request execution simulator
# ---------------------------------------------------------------------------


def _simulate_batches(
    batches,
    *,
    initial_body_len: int,
    deleted_row_sizes: list[int],
) -> list[str]:
    """Simulate sequential request execution and return list of violations.

    Tracks document length through insertText, deleteContentRange, and
    deleteTableRow ops. Each out-of-bounds index produces a violation string.
    Empty list means all indices are valid.

    ``deleted_row_sizes`` lists the byte size of each deleted row in the order
    ``deleteTableRow`` requests appear in the batch.
    """
    doc_len = initial_body_len
    violations: list[str] = []
    req_idx = 0
    del_iter = iter(deleted_row_sizes)

    for batch in batches:
        for req in batch.requests or []:
            d = req.model_dump(by_alias=True, exclude_none=True)

            if "insertText" in d:
                idx = d["insertText"]["location"]["index"]
                text = d["insertText"]["text"]
                if idx > doc_len:
                    violations.append(
                        f"req[{req_idx}] insertText: index={idx} > doc_len={doc_len} "
                        f"(text={text!r})"
                    )
                else:
                    doc_len += utf16_len(text)

            elif "deleteContentRange" in d:
                rng = d["deleteContentRange"]["range"]
                s, e = rng["startIndex"], rng["endIndex"]
                if e > doc_len:
                    violations.append(
                        f"req[{req_idx}] deleteContentRange: endIndex={e} "
                        f"> doc_len={doc_len}"
                    )
                elif s < 0:
                    violations.append(
                        f"req[{req_idx}] deleteContentRange: startIndex={s} < 0"
                    )
                else:
                    doc_len -= e - s

            elif "deleteTableRow" in d:
                try:
                    row_bytes = next(del_iter)
                except StopIteration:
                    violations.append(
                        f"req[{req_idx}] deleteTableRow: unexpected (no size info)"
                    )
                    row_bytes = 0
                doc_len -= row_bytes

            req_idx += 1

    return violations


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_delete_row_and_edit_cell_content() -> None:
    """Delete one row from a 3x2 table and edit a cell in a surviving row.

    Base:
      Row 0: ["A1", "B1"]
      Row 1: ["A2", "B2"]  ← deleted
      Row 2: ["A3", "B3"]  ← edit A3 → "A3_edited"

    Without the fix, the insertText for "_edited" targets base index 27
    which is stale after deleteTableRow shrinks the doc.
    """
    table_el, table_end = _make_indexed_table(
        [["A1", "B1"], ["A2", "B2"], ["A3", "B3"]], table_start=1
    )
    terminal = make_indexed_terminal(table_end)
    base = make_indexed_doc(body_content=[table_el, terminal])

    desired = make_indexed_doc(
        body_content=[
            _desired_table([["A1", "B1"], ["A3_edited", "B3"]]),
            make_terminal_para(),
        ]
    )

    batches = reconcile_batches(base, desired)
    violations = _simulate_batches(
        batches,
        initial_body_len=table_end + 1,
        deleted_row_sizes=[_row_size(["A2", "B2"])],
    )
    assert violations == [], "Requests produce stale indices:\n  " + "\n  ".join(
        violations
    )


def test_delete_multiple_rows_and_edit_cells() -> None:
    """Delete two rows and edit cells in two surviving rows."""
    table_el, table_end = _make_indexed_table(
        [["H1", "H2"], ["del1", "del2"], ["C1", "C2"], ["del3", "del4"], ["E1", "E2"]],
        table_start=1,
    )
    terminal = make_indexed_terminal(table_end)
    base = make_indexed_doc(body_content=[table_el, terminal])

    desired = make_indexed_doc(
        body_content=[
            _desired_table([["H1", "H2"], ["C1_new", "C2"], ["E1_new", "E2"]]),
            make_terminal_para(),
        ]
    )

    batches = reconcile_batches(base, desired)
    # Row deletes are emitted in descending index order: row 3 first, then row 1
    violations = _simulate_batches(
        batches,
        initial_body_len=table_end + 1,
        deleted_row_sizes=[
            _row_size(["del3", "del4"]),  # row 3 deleted first
            _row_size(["del1", "del2"]),  # then row 1
        ],
    )
    assert violations == [], "Requests produce stale indices:\n  " + "\n  ".join(
        violations
    )


def test_delete_row_and_fill_empty_cells() -> None:
    """Matches the original user scenario: delete a row, fill empty cells
    in surviving rows with new text.
    """
    table_el, table_end = _make_indexed_table(
        [
            ["Sr", "Question", "Filter"],
            ["", "Q1", ""],
            ["", "Q_delete", ""],
            ["", "Q2", ""],
        ],
        table_start=1,
    )
    terminal = make_indexed_terminal(table_end)
    base = make_indexed_doc(body_content=[table_el, terminal])

    desired = make_indexed_doc(
        body_content=[
            _desired_table(
                [
                    ["Sr", "Question", "Filter"],
                    ["1", "Q1", "F1"],
                    ["2", "Q2", "F2"],
                ]
            ),
            make_terminal_para(),
        ]
    )

    batches = reconcile_batches(base, desired)
    violations = _simulate_batches(
        batches,
        initial_body_len=table_end + 1,
        deleted_row_sizes=[_row_size(["", "Q_delete", ""])],
    )
    assert violations == [], "Requests produce stale indices:\n  " + "\n  ".join(
        violations
    )


def test_body_text_before_table_plus_row_delete_and_cell_edit() -> None:
    """Combined: body text edit before table + row deletion + cell edit.

    Base:
      Para "Intro\\n"
      3x2 table
        Row 0: ["A1", "B1"]
        Row 1: ["A2", "B2"]  ← delete
        Row 2: ["A3", "B3"]  ← edit A3 → "A3_edited"

    Desired:
      Para "Introduction\\n"  (+7 chars)
      2x2 table (rows 0 and 2)
    """
    intro = make_indexed_para("Intro\n", start=1)
    table_el, table_end = _make_indexed_table(
        [["A1", "B1"], ["A2", "B2"], ["A3", "B3"]], table_start=7
    )
    terminal = make_indexed_terminal(table_end)
    base = make_indexed_doc(body_content=[intro, table_el, terminal])

    desired = make_indexed_doc(
        body_content=[
            make_para_el("Introduction\n"),
            _desired_table([["A1", "B1"], ["A3_edited", "B3"]]),
            make_terminal_para(),
        ]
    )

    batches = reconcile_batches(base, desired)
    violations = _simulate_batches(
        batches,
        initial_body_len=table_end + 1,
        deleted_row_sizes=[_row_size(["A2", "B2"])],
    )
    assert violations == [], "Requests produce stale indices:\n  " + "\n  ".join(
        violations
    )
