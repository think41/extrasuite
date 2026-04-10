"""Regression tests for table-structural ops using stale BASE anchor indices
when a same-tab body-text edit precedes them in the batch.

Bug: ``UpdateBodyContentOp`` lowers into ``insertText`` /
``deleteContentRange`` requests that go into batch1 BEFORE the table-structural
child ops (``InsertTableColumnOp``, ``InsertTableRowOp``, ``DeleteTableRowOp``,
``DeleteTableColumnOp``, ``UpdateTableCellStyleOp``, ...). All table-structural
ops carry a ``tableStartLocation`` with a BASE byte index. When the body-text
ops shift the doc at positions ≤ ``tableStartLocation``, the subsequent table
ops see stale coordinates and either 400 or land in the wrong place.

These tests assert directly on the lowered ``batch_requests`` (not via the
mock).
"""

from __future__ import annotations

from extradoc.api_types._generated import (
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    StructuralElement,
    TableCell,
    TextRun,
)
from extradoc.reconcile_v3.api import reconcile_batches

from .helpers import (
    assert_batches_within_base,
    make_indexed_para,
    make_indexed_terminal,
    make_para_el,
    make_terminal_para,
)
from .test_column_append_content_bug import (
    _desired_table,
    _make_base_2x2_table_at,
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
    return [
        (r["insertText"]["location"]["index"], r["insertText"]["text"])
        for r in requests
        if "insertText" in r
    ]


def _get_table_start(req: dict) -> int | None:
    """Extract tableStartLocation.index from a structural table op dict."""
    for key in (
        "insertTableColumn",
        "insertTableRow",
        "deleteTableColumn",
        "deleteTableRow",
    ):
        if key in req:
            return req[key]["tableCellLocation"]["tableStartLocation"]["index"]
    return None


def test_insert_text_before_table_shifts_insertTableColumn_start() -> None:
    """A paragraph grow that emits an insertText BEFORE the table must shift
    the table-structural op's tableStartLocation by the insert length, AND
    shift the new-column cell-fill insertTexts by the same delta."""
    # Base: "Intro\n" at [1,7), table at [7, 7+23), terminal at 30.
    intro = make_indexed_para("Intro\n", start=1)
    table_el, table_end = _make_base_2x2_table_at(table_start=7)
    terminal = make_indexed_terminal(table_end)
    base = make_indexed_doc(body_content=[intro, table_el, terminal])

    # Desired: grow intro to "Intro_edited\n" (+7 chars) + add column [C1, C2].
    desired_table = _desired_table([["A1", "B1", "C1"], ["A2", "B2", "C2"]])
    desired = make_indexed_doc(
        body_content=[
            make_para_el("Intro_edited\n"),
            desired_table,
            make_terminal_para(),
        ],
    )

    batches = reconcile_batches(base, desired)
    assert_batches_within_base(base, batches)
    reqs = _collect_requests(batches)

    col_inserts = [r for r in reqs if "insertTableColumn" in r]
    assert len(col_inserts) == 1
    # BASE table_start=7. insertText "_edited" (+7) at loc=6 precedes 7 →
    # shifted start = 14.
    assert _get_table_start(col_inserts[0]) == 14

    text_inserts = _find_insert_texts(reqs)
    c1_hits = [(idx, t) for idx, t in text_inserts if t == "C1"]
    c2_hits = [(idx, t) for idx, t in text_inserts if t == "C2"]
    assert c1_hits and c2_hits
    # Unshifted anchors: C1@20, C2@33 (from the column-append regression test).
    # Shift by +7 → 27 and 40.
    assert c1_hits[0][0] == 27
    assert c2_hits[0][0] == 40


def test_delete_before_table_shifts_insertTableRow_start() -> None:
    """A paragraph shrink (net delete) before a table must shift table ops
    down by the net deleted bytes."""
    # Base: 28-byte intro at [1,29), table at [29, 29+23), terminal at 52.
    intro = make_indexed_para("Introduction to my document\n", start=1)
    table_el, table_end = _make_base_2x2_table_at(table_start=29)
    terminal = make_indexed_terminal(table_end)
    base = make_indexed_doc(body_content=[intro, table_el, terminal])

    # Desired: shrink intro to "Hi\n" AND append a row [C1, C2].
    desired_table = _desired_table([["A1", "B1"], ["A2", "B2"], ["C1", "C2"]])
    desired = make_indexed_doc(
        body_content=[make_para_el("Hi\n"), desired_table, make_terminal_para()],
    )

    batches = reconcile_batches(base, desired)
    assert_batches_within_base(base, batches)
    reqs = _collect_requests(batches)

    row_inserts = [r for r in reqs if "insertTableRow" in r]
    assert len(row_inserts) == 1
    # BASE table_start=29. Net delta: -28 +3 = -25. Shifted start = 4.
    assert _get_table_start(row_inserts[0]) == 4

    # Row-fill inserts: new_row_start BASE = 29+23 = 52. Shifted: 52-25 = 27.
    # p1_index_col0 = 27 + 1 (row overhead) + 0*3 + 1 = 29
    # p1_index_col1 = 27 + 1 + 1*3 + 1 = 31
    text_inserts = _find_insert_texts(reqs)
    texts_by_text = {t: idx for idx, t in text_inserts}
    assert "C1" in texts_by_text and "C2" in texts_by_text
    assert texts_by_text["C1"] == 29
    assert texts_by_text["C2"] == 31


def test_multiple_body_edits_accumulate_shift() -> None:
    """Multiple body-text ops before a table structural op: shifts accumulate."""
    # Base: para1 at [1,7) = "AAA\n" (4 bytes? no — "AAA\n" is 4 chars 1..5)
    # Use explicit sizes. Para1 "P1\n" [1,4); Para2 "P2XX\n" [4,9); table [9, 9+23=32).
    p1 = make_indexed_para("P1\n", start=1)
    p2 = make_indexed_para("P2XX\n", start=4)
    table_el, table_end = _make_base_2x2_table_at(table_start=9)
    terminal = make_indexed_terminal(table_end)
    base = make_indexed_doc(body_content=[p1, p2, table_el, terminal])

    # Desired: grow p1 to "P1GROWN\n" (+5), shrink p2 to "P\n" (-3), add column [C1,C2].
    desired_table = _desired_table([["A1", "B1", "C1"], ["A2", "B2", "C2"]])
    desired = make_indexed_doc(
        body_content=[
            make_para_el("P1GROWN\n"),
            make_para_el("P\n"),
            desired_table,
            make_terminal_para(),
        ],
    )

    batches = reconcile_batches(base, desired)
    assert_batches_within_base(base, batches)
    reqs = _collect_requests(batches)

    col_inserts = [r for r in reqs if "insertTableColumn" in r]
    assert len(col_inserts) == 1
    # Net delta: +5 -3 = +2. Shifted table_start = 9+2 = 11.
    assert _get_table_start(col_inserts[0]) == 11


def test_body_edit_after_table_does_not_shift_table_start() -> None:
    """A body-text op targeting a position AFTER the table must NOT shift
    the table's tableStartLocation."""
    # Base: table at [1, 24), terminal at 24, then trailing para is the
    # terminal. Add a trailing para that has content so we can edit it.
    table_el, table_end = _make_base_2x2_table_at(table_start=1)
    trailing = make_indexed_para("Outro\n", start=table_end)
    terminal = make_indexed_terminal(table_end + 6)
    base = make_indexed_doc(body_content=[table_el, trailing, terminal])

    desired_table = _desired_table([["A1", "B1", "C1"], ["A2", "B2", "C2"]])
    desired = make_indexed_doc(
        body_content=[
            desired_table,
            make_para_el("Outro_edited\n"),
            make_terminal_para(),
        ],
    )

    batches = reconcile_batches(base, desired)
    assert_batches_within_base(base, batches)
    reqs = _collect_requests(batches)

    col_inserts = [r for r in reqs if "insertTableColumn" in r]
    assert len(col_inserts) == 1
    # BASE table_start=1; body edit is at position > 24 (after table) → no shift.
    assert _get_table_start(col_inserts[0]) == 1
