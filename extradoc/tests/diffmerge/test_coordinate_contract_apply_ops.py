"""Coordinate contract tests for ``apply_ops_to_document``.

Exercises the three-state invariant on ``startIndex`` / ``endIndex`` specified
in ``docs/coordinate_contract.md``. Each scenario builds a small base
document (plain dicts, no fixtures), runs one or zero reconcile ops through
``apply_ops_to_document``, and pins expected concrete / None indices on the
result.
"""

from __future__ import annotations

from typing import Any

import pytest

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
from extradoc.diffmerge.apply_ops import (
    _assert_indices_well_formed,
    apply_ops_to_document,
)
from extradoc.diffmerge.content_align import ContentAlignment, ContentMatch
from extradoc.diffmerge.model import UpdateBodyContentOp

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TAB_ID = "t0"


def _para_dict(text: str, start: int) -> dict[str, Any]:
    """Build a body paragraph dict with concrete indices.

    The run occupies [start, start + len(text)); the paragraph shell carries
    the same bounds.
    """
    end = start + len(text)
    return {
        "startIndex": start,
        "endIndex": end,
        "paragraph": {
            "elements": [
                {
                    "startIndex": start,
                    "endIndex": end,
                    "textRun": {"content": text, "textStyle": {}},
                }
            ],
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
        },
    }


def _table_dict(rows_texts: list[list[str]], start: int) -> dict[str, Any]:
    """Build a concrete-index table dict shaped like the Google API response.

    Each cell contains exactly one paragraph with a single text run. Indices
    are fabricated sequentially for the test; only their concreteness matters
    for this test's assertions.
    """
    cur = start
    rows: list[dict[str, Any]] = []
    table_start = cur
    for row_texts in rows_texts:
        cells: list[dict[str, Any]] = []
        row_start = cur
        for text in row_texts:
            cell_start = cur
            para = _para_dict(text, cur)
            cur = para["endIndex"] + 1  # +1 for cell terminator
            cells.append(
                {
                    "startIndex": cell_start,
                    "endIndex": cur,
                    "content": [para],
                }
            )
        rows.append({"startIndex": row_start, "endIndex": cur, "tableCells": cells})
    table_end = cur
    return {
        "startIndex": table_start,
        "endIndex": table_end,
        "table": {
            "rows": len(rows_texts),
            "columns": len(rows_texts[0]) if rows_texts else 0,
            "tableRows": rows,
        },
    }


def _make_base(body_content: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a minimal document dict with a single tab and a body."""
    return {
        "tabs": [
            {
                "tabProperties": {"tabId": TAB_ID},
                "documentTab": {"body": {"content": body_content}},
            }
        ]
    }


def _se_para(text: str) -> StructuralElement:
    return StructuralElement(
        paragraph=Paragraph(
            elements=[ParagraphElement(text_run=TextRun(content=text))],
            paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
        )
    )


def _se_table(rows_texts: list[list[str]]) -> StructuralElement:
    rows = []
    for row_texts in rows_texts:
        cells = [TableCell(content=[_se_para(text)]) for text in row_texts]
        rows.append(TableRow(table_cells=cells))
    return StructuralElement(
        table=Table(
            table_rows=rows,
            rows=len(rows_texts),
            columns=len(rows_texts[0]) if rows_texts else 0,
        )
    )


def _body(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return doc["tabs"][0]["documentTab"]["body"]["content"]


def _is_concrete(el: dict[str, Any]) -> bool:
    s = el.get("startIndex")
    e = el.get("endIndex")
    # "concrete" for this test = either key missing OR integer value; NOT None
    return s is not None and e is not None


def _is_nulled(el: dict[str, Any]) -> bool:
    return el.get("startIndex") is None and el.get("endIndex") is None


# ---------------------------------------------------------------------------
# 1. Identity merge — zero ops, everything stays concrete.
# ---------------------------------------------------------------------------


def test_identity_merge_preserves_concrete_indices() -> None:
    p0 = _para_dict("hello\n", 1)  # [1..7)
    p1 = _para_dict("world\n", 7)  # [7..13)
    base = _make_base([p0, p1])

    desired = apply_ops_to_document(base, [])

    body = _body(desired)
    assert body[0]["startIndex"] == 1
    assert body[0]["endIndex"] == 7
    assert body[1]["startIndex"] == 7
    assert body[1]["endIndex"] == 13
    # Runs inside also concrete.
    assert body[0]["paragraph"]["elements"][0]["startIndex"] == 1
    assert body[0]["paragraph"]["elements"][0]["endIndex"] == 7
    _assert_indices_well_formed(desired)


# ---------------------------------------------------------------------------
# 2. Single paragraph text edit: the touched para + same-run siblings nulled;
#    elements before the touched span remain concrete.
# ---------------------------------------------------------------------------


def test_single_paragraph_edit_nulls_touched_and_later_siblings() -> None:
    p0 = _para_dict("alpha\n", 1)  # untouched, BEFORE the edit
    p1 = _para_dict("beta\n", 7)  # edited
    p2 = _para_dict("gamma\n", 12)  # untouched, sibling AFTER the edit
    base = _make_base([p0, p1, p2])

    ancestor = [_se_para("alpha\n"), _se_para("beta\n"), _se_para("gamma\n")]
    mine = [_se_para("alpha\n"), _se_para("BETA\n"), _se_para("gamma\n")]

    alignment = ContentAlignment(
        matches=[
            ContentMatch(base_idx=0, desired_idx=0),
            ContentMatch(base_idx=1, desired_idx=1),
            ContentMatch(base_idx=2, desired_idx=2),
        ],
        base_deletes=[],
        desired_inserts=[],
        total_cost=0.0,
    )
    op = UpdateBodyContentOp(
        tab_id=TAB_ID,
        story_kind="body",
        story_id="body",
        alignment=alignment,
        base_content=ancestor,
        desired_content=mine,
    )

    desired = apply_ops_to_document(base, [op])
    body = _body(desired)

    # p0 is before the touched span → concrete.
    assert body[0]["startIndex"] == 1
    assert body[0]["endIndex"] == 7
    # p1 is the edited paragraph → None.
    assert _is_nulled(body[1])
    # p2 is after but there is no later mutation, so the touched span ends
    # at index 1; p2 stays concrete.
    assert body[2]["startIndex"] == 12
    _assert_indices_well_formed(desired)


# ---------------------------------------------------------------------------
# 3. Insert new paragraph mid-body: elements outside the touched span keep
#    concrete indices. A table positioned after an untouched element is
#    outside the run.
# ---------------------------------------------------------------------------


def test_insert_mid_body_poisons_only_touched_span() -> None:
    p0 = _para_dict("alpha\n", 1)  # [1..7)
    p1 = _para_dict("beta\n", 7)  # [7..12)
    table = _table_dict([["x"]], 12)
    # Append a trailing paragraph after the table, also concrete.
    tail_start = table["endIndex"]
    tail = _para_dict("tail\n", tail_start)
    base = _make_base([p0, p1, table, tail])

    # User inserts a new paragraph between p0 and p1.
    ancestor = [
        _se_para("alpha\n"),
        _se_para("beta\n"),
        _se_table([["x"]]),
        _se_para("tail\n"),
    ]
    mine = [
        _se_para("alpha\n"),
        _se_para("NEW\n"),
        _se_para("beta\n"),
        _se_table([["x"]]),
        _se_para("tail\n"),
    ]
    alignment = ContentAlignment(
        matches=[
            ContentMatch(base_idx=0, desired_idx=0),
            ContentMatch(base_idx=1, desired_idx=2),
            ContentMatch(base_idx=2, desired_idx=3),
            ContentMatch(base_idx=3, desired_idx=4),
        ],
        base_deletes=[],
        desired_inserts=[1],
        total_cost=1.0,
    )
    op = UpdateBodyContentOp(
        tab_id=TAB_ID,
        story_kind="body",
        story_id="body",
        alignment=alignment,
        base_content=ancestor,
        desired_content=mine,
    )

    desired = apply_ops_to_document(base, [op])
    body = _body(desired)

    # The only mutation is the insert at result index 1; touched span = [1..1].
    assert len(body) == 5
    # p0 (before insert) → concrete.
    assert body[0]["startIndex"] == 1
    # inserted new para → None.
    assert _is_nulled(body[1])
    # beta: outside the mutation span → concrete (preserved from base).
    assert body[2]["startIndex"] == 7
    # table: outside → concrete.
    assert body[3]["startIndex"] == 12
    assert body[3]["endIndex"] == table["endIndex"]
    # tail: outside → concrete.
    assert body[4]["startIndex"] == tail_start
    _assert_indices_well_formed(desired)


# ---------------------------------------------------------------------------
# 4. Table cell paragraph join (FORM-15G shape): 2 raw paragraphs → 1 desired
#    paragraph. Cell shape change poisons the whole table.
# ---------------------------------------------------------------------------


def test_table_cell_paragraph_join_poisons_entire_table() -> None:
    # Build a table where one cell has two paragraphs, like the FORM-15G
    # layout that flattens into a single editable line.
    p_head = _para_dict("Before\n", 1)  # body para before the table
    # Table starts at 8.
    cur = 8
    cell_start = cur
    cell_p0 = _para_dict("Name\n", cur)  # [8..13)
    cur = cell_p0["endIndex"]
    cell_p1 = _para_dict("Status\n", cur)  # [13..20)
    cur = cell_p1["endIndex"] + 1  # +1 cell terminator
    cell_end = cur
    cell_dict = {
        "startIndex": cell_start,
        "endIndex": cell_end,
        "content": [cell_p0, cell_p1],
    }
    row_end = cur
    row_dict = {
        "startIndex": cell_start,
        "endIndex": row_end,
        "tableCells": [cell_dict],
    }
    table = {
        "startIndex": cell_start,
        "endIndex": row_end,
        "table": {
            "rows": 1,
            "columns": 1,
            "tableRows": [row_dict],
        },
    }
    base = _make_base([p_head, table])

    # Ancestor is the SERDE-FLATTENED view of the raw table: the two
    # physical paragraphs collapsed into a single editable line (e.g. GFM
    # table cell). This is the shape that triggers the join branch in
    # `_merge_table_cell`: len(ancestor) < len(raw) → truncate raw to the
    # desired paragraph count.
    a_table = StructuralElement(
        table=Table(
            table_rows=[
                TableRow(table_cells=[TableCell(content=[_se_para("Name Status\n")])])
            ],
            rows=1,
            columns=1,
        )
    )
    # User edited the flattened line.
    d_table = StructuralElement(
        table=Table(
            table_rows=[
                TableRow(table_cells=[TableCell(content=[_se_para("Full name\n")])])
            ],
            rows=1,
            columns=1,
        )
    )

    alignment = ContentAlignment(
        matches=[
            ContentMatch(base_idx=0, desired_idx=0),
            ContentMatch(base_idx=1, desired_idx=1),
        ],
        base_deletes=[],
        desired_inserts=[],
        total_cost=1.0,
    )
    op = UpdateBodyContentOp(
        tab_id=TAB_ID,
        story_kind="body",
        story_id="body",
        alignment=alignment,
        base_content=[_se_para("Before\n"), a_table],
        desired_content=[_se_para("Before\n"), d_table],
    )

    desired = apply_ops_to_document(base, [op])
    body = _body(desired)

    # The head paragraph is before the touched span → concrete.
    assert body[0]["startIndex"] == 1

    # The table element was mutated. Everything inside it (rows, cells,
    # cell content, paragraphs, runs) is nulled.
    tbl_el = body[1]
    assert _is_nulled(tbl_el)
    t = tbl_el["table"]
    for row in t["tableRows"]:
        assert _is_nulled(row)
        for cell in row["tableCells"]:
            assert _is_nulled(cell)
            for cse in cell["content"]:
                assert _is_nulled(cse)
                for pe in cse["paragraph"]["elements"]:
                    # Run-level indices were present on base → now None.
                    assert pe.get("startIndex") is None
                    assert pe.get("endIndex") is None
    # The truncated paragraph: desired had one paragraph; the cell content
    # must now have length 1.
    assert len(t["tableRows"][0]["tableCells"][0]["content"]) == 1
    _assert_indices_well_formed(desired)


# ---------------------------------------------------------------------------
# 5. Style-only run edit: paragraph nulled (run splitting may change
#    byte structure), siblings outside the span stay concrete.
# ---------------------------------------------------------------------------


def test_style_only_edit_nulls_paragraph() -> None:
    p0 = _para_dict("alpha\n", 1)
    p1 = _para_dict("beta\n", 7)
    base = _make_base([p0, p1])

    # Mine: p1 is now bold (style-only change).
    bold_run = ParagraphElement(
        text_run=TextRun(content="beta\n", text_style={"bold": True})  # type: ignore[arg-type]
    )
    mine_p1 = StructuralElement(
        paragraph=Paragraph(
            elements=[bold_run],
            paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
        )
    )
    alignment = ContentAlignment(
        matches=[
            ContentMatch(base_idx=0, desired_idx=0),
            ContentMatch(base_idx=1, desired_idx=1),
        ],
        base_deletes=[],
        desired_inserts=[],
        total_cost=0.0,
    )
    op = UpdateBodyContentOp(
        tab_id=TAB_ID,
        story_kind="body",
        story_id="body",
        alignment=alignment,
        base_content=[_se_para("alpha\n"), _se_para("beta\n")],
        desired_content=[_se_para("alpha\n"), mine_p1],
    )

    desired = apply_ops_to_document(base, [op])
    body = _body(desired)

    # p0 is before the touched span → concrete.
    assert body[0]["startIndex"] == 1
    # p1 touched → nulled.
    assert _is_nulled(body[1])
    # Nested run indices nulled.
    for pe in body[1]["paragraph"]["elements"]:
        assert pe.get("startIndex") is None
        assert pe.get("endIndex") is None
    _assert_indices_well_formed(desired)


# ---------------------------------------------------------------------------
# 6. Short-circuit: base and desired are identical → concrete indices stay.
#    Exercised by the no-ops entry path already, but pin a cell explicitly.
# ---------------------------------------------------------------------------


def test_shortcircuit_unchanged_cell_keeps_concrete_indices() -> None:
    table = _table_dict([["keep"]], 1)
    base = _make_base([table])

    desired = apply_ops_to_document(base, [])
    body = _body(desired)
    tbl_el = body[0]
    # Everything concrete.
    assert tbl_el["startIndex"] == table["startIndex"]
    assert tbl_el["endIndex"] == table["endIndex"]
    row0 = tbl_el["table"]["tableRows"][0]
    assert row0["startIndex"] is not None
    cell0 = row0["tableCells"][0]
    assert cell0["startIndex"] is not None
    assert cell0["endIndex"] is not None
    _assert_indices_well_formed(desired)


# ---------------------------------------------------------------------------
# 7. Mixed-state assertion: hand-corrupt a node and verify the helper raises.
# ---------------------------------------------------------------------------


def test_assert_indices_well_formed_raises_on_mixed_state() -> None:
    p0 = _para_dict("hi\n", 1)
    doc = _make_base([p0])

    # Hand-corrupt: set startIndex=5, endIndex=None on the paragraph shell.
    doc["tabs"][0]["documentTab"]["body"]["content"][0]["startIndex"] = 5
    doc["tabs"][0]["documentTab"]["body"]["content"][0]["endIndex"] = None

    with pytest.raises(AssertionError) as excinfo:
        _assert_indices_well_formed(doc)
    # Path to the corrupted node should appear in the message.
    assert "tabs[0].documentTab.body.content[0]" in str(excinfo.value)
    assert "startIndex" in str(excinfo.value)
    assert "endIndex" in str(excinfo.value)
