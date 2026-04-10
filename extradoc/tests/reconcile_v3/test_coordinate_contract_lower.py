"""Coordinate contract tests for ``reconcile_v3/lower.py``.

These tests pin the consumer-side invariants of the coordinate contract
documented in ``extradoc/docs/coordinate_contract.md``:

- Base-tree reads must always yield concrete indices (State A).
- Desired-tree elements with ``(None, None)`` indices (State B) must have
  their live-doc coordinate synthesized from base anchors + cumulative shift,
  or must raise ``CoordinateNotResolvedError``.
- Silent ``continue`` on missing indices is forbidden. Loud failure is the
  only acceptable behaviour when coordinates cannot be resolved.

Each test hand-enumerates the exact emitted op list (no snapshot capture) and
validates via ``simulate_ops_against_base``.
"""

from __future__ import annotations

from typing import Any

import pytest

from extradoc.api_types._generated import (
    Paragraph,
    ParagraphElement,
    ParagraphStyle,
    StructuralElement,
    TextRun,
)
from extradoc.diffmerge import CoordinateNotResolvedError
from extradoc.diffmerge.content_align import ContentAlignment, ContentMatch
from extradoc.diffmerge.model import UpdateBodyContentOp
from extradoc.reconcile_v3.lower import lower_batches
from tests.reconcile_v3.helpers import simulate_ops_against_base

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _indexed_para(text: str, start: int) -> StructuralElement:
    """Paragraph element with concrete indices (base-tree State A)."""
    end = start + len(text)
    return StructuralElement(
        start_index=start,
        end_index=end,
        paragraph=Paragraph(
            elements=[
                ParagraphElement(
                    start_index=start,
                    end_index=end,
                    text_run=TextRun(content=text),
                )
            ],
            paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
        ),
    )


def _none_indexed_para(text: str) -> StructuralElement:
    """Paragraph element with ``(None, None)`` indices (desired-tree State B)."""
    return StructuralElement(
        start_index=None,
        end_index=None,
        paragraph=Paragraph(
            elements=[
                ParagraphElement(
                    start_index=None,
                    end_index=None,
                    text_run=TextRun(content=text),
                )
            ],
            paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
        ),
    )


def _make_base_with_table_cell(
    cell_start: int, cell_end: int
) -> tuple[list[StructuralElement], dict[str, Any]]:
    """Build a tiny base doc with a table containing one cell [cell_start..cell_end).

    Returns ``(cell_content, base_doc_dict)`` where ``cell_content`` is the
    cell's content list with concrete body-level absolute indices, and
    ``base_doc_dict`` is the full tab dict for the simulator oracle.

    Layout::

        [  0..  1)  sectionBreak
        [  1..  5)  paragraph "abc\\n"  (4 chars: a b c \\n)
        [  5..  6)  table opener
        [  6..  7)  row[0] opener
        [  7..  8)  cell[0][0] opener  (anchor = cell_start - 1 conceptually)
        [cs..ce)    cell[0][0] content (3 paragraphs)
        ...
    """
    # Inside the cell: three paragraphs that together span [cell_start..cell_end).
    # For the FORM-15G-style layout we just need the cell content list; body-level
    # absolute indices on those content elements.
    assert cell_end > cell_start + 6, "need room for 3 short paragraphs"
    p1_start = cell_start
    p1_text = "Name\n"  # 5 chars
    p2_start = p1_start + len(p1_text)
    p2_text = "PAN\n"  # 4 chars
    p3_start = p2_start + len(p2_text)
    # Terminal paragraph ends at cell_end
    p3_text = "X" * (cell_end - p3_start - 1) + "\n"

    cell_content = [
        _indexed_para(p1_text, p1_start),
        _indexed_para(p2_text, p2_start),
        _indexed_para(p3_text, p3_start),
    ]

    # Full base doc dict for the simulator.
    cell_dict = {
        "startIndex": cell_start,
        "endIndex": cell_end,
        "content": [
            {
                "startIndex": p1_start,
                "endIndex": p1_start + len(p1_text),
                "paragraph": {
                    "elements": [
                        {
                            "startIndex": p1_start,
                            "endIndex": p1_start + len(p1_text),
                            "textRun": {"content": p1_text},
                        }
                    ]
                },
            },
            {
                "startIndex": p2_start,
                "endIndex": p2_start + len(p2_text),
                "paragraph": {
                    "elements": [
                        {
                            "startIndex": p2_start,
                            "endIndex": p2_start + len(p2_text),
                            "textRun": {"content": p2_text},
                        }
                    ]
                },
            },
            {
                "startIndex": p3_start,
                "endIndex": cell_end,
                "paragraph": {
                    "elements": [
                        {
                            "startIndex": p3_start,
                            "endIndex": cell_end,
                            "textRun": {"content": p3_text},
                        }
                    ]
                },
            },
        ],
    }

    # Second cell for FORM-15G-like fixture: trivial cell after the first.
    cell2_start = cell_end + 1  # skip row/cell opener
    cell2_para_start = cell2_start
    cell2_para_text = "q\n"
    cell2_end = cell2_start + len(cell2_para_text)
    cell2_dict = {
        "startIndex": cell2_start,
        "endIndex": cell2_end,
        "content": [
            {
                "startIndex": cell2_para_start,
                "endIndex": cell2_end,
                "paragraph": {
                    "elements": [
                        {
                            "startIndex": cell2_para_start,
                            "endIndex": cell2_end,
                            "textRun": {"content": cell2_para_text},
                        }
                    ]
                },
            }
        ],
    }

    table_start = cell_start - 2  # table opener + row opener + cell opener
    table_end = cell2_end + 1  # trailing newline after last row
    table_dict = {
        "startIndex": table_start,
        "endIndex": table_end,
        "table": {
            "rows": 1,
            "columns": 2,
            "tableRows": [
                {"tableCells": [cell_dict, cell2_dict]},
            ],
        },
    }

    # Preceding body: sectionBreak + filler paragraph sized to place the table
    # right at the expected offset.
    sb = {"startIndex": 0, "endIndex": 1, "sectionBreak": {}}
    filler_len = table_start - 1  # chars between index 1 and table_start
    filler_text = "." * (filler_len - 1) + "\n" if filler_len > 0 else "\n"
    filler_para = {
        "startIndex": 1,
        "endIndex": 1 + len(filler_text),
        "paragraph": {
            "elements": [
                {
                    "startIndex": 1,
                    "endIndex": 1 + len(filler_text),
                    "textRun": {"content": filler_text},
                }
            ]
        },
    }
    # If filler doesn't land exactly at table_start, pad with another newline.
    assert 1 + len(filler_text) == table_start, (
        f"filler mismatch: {1 + len(filler_text)} != {table_start}"
    )

    trailing = {
        "startIndex": table_end,
        "endIndex": table_end + 1,
        "paragraph": {
            "elements": [
                {
                    "startIndex": table_end,
                    "endIndex": table_end + 1,
                    "textRun": {"content": "\n"},
                }
            ]
        },
    }

    base_doc = {
        "tabs": [
            {
                "documentTab": {
                    "body": {
                        "content": [sb, filler_para, table_dict, trailing],
                    }
                }
            }
        ]
    }

    return cell_content, base_doc


def _req_to_dict(req: Any) -> dict[str, Any]:
    """Convert a typed Request to a dict for the simulator oracle."""
    return req.model_dump(by_alias=True, exclude_none=True)


# ---------------------------------------------------------------------------
# Scenario 1: joined cell — base delete targets base cell range, not desired
# ---------------------------------------------------------------------------


def test_joined_cell_delete_reads_base_not_desired() -> None:
    """Base cell [414..496) with 3 paragraphs; desired collapses to 1 paragraph
    with None indices. The emitted ops must read base-tree ranges for the
    delete, not stale desired values. No op may touch {496, 497} (FORM-15G
    cell-boundary bug).
    """
    cell_content, base_doc = _make_base_with_table_cell(414, 496)

    # Desired: single paragraph with None indices (State B — poisoned cell).
    desired_content = [_none_indexed_para("Joined text\n")]

    alignment = ContentAlignment(
        matches=[],
        base_deletes=[0, 1, 2],
        desired_inserts=[0],
        total_cost=0.0,
    )

    op = UpdateBodyContentOp(
        tab_id="",
        story_kind="table_cell",
        story_id="r0:c0",
        alignment=alignment,
        base_content=cell_content,
        desired_content=desired_content,
    )

    batches = lower_batches([op])
    assert len(batches) == 1
    reqs = batches[0]
    req_dicts = [_req_to_dict(r) for r in reqs]

    # Assert: at least one delete whose range reads base cell ranges.
    deletes = [r for r in req_dicts if "deleteContentRange" in r]
    assert len(deletes) == 3
    delete_ranges = {
        (
            d["deleteContentRange"]["range"]["startIndex"],
            d["deleteContentRange"]["range"]["endIndex"],
        )
        for d in deletes
    }
    # Base paragraphs: [414..419), [419..423), [423..496)
    assert (414, 419) in delete_ranges
    assert (419, 423) in delete_ranges
    assert (423, 496) in delete_ranges

    # No op may START at or INSERT at the cell boundary {496, 497}.
    # (An exclusive endIndex of 496 is legal — it means "up to but not
    # including the cell terminator".)
    for r in req_dicts:
        for key in ("deleteContentRange", "updateTextStyle", "updateParagraphStyle"):
            if key not in r:
                continue
            rng = r[key].get("range") or {}
            assert rng.get("startIndex") not in (496, 497), (
                f"op {r} starts at cell boundary"
            )
        if "insertText" in r:
            loc = r["insertText"].get("location") or {}
            assert loc.get("index") not in (496, 497), (
                f"insert {r} lands on cell boundary"
            )

    assert simulate_ops_against_base(base_doc, req_dicts) == []


# ---------------------------------------------------------------------------
# Scenario 2: insert into a None-indexed cell — hand-computed anchor
# ---------------------------------------------------------------------------


def test_insert_in_none_indexed_cell_uses_base_anchor() -> None:
    """A pure insert into a cell whose desired paragraph has None indices
    must compute insertText.location.index from the base anchor. Because the
    insertion is BEFORE the cell terminal (base index 423), the live-doc index
    should land at 423 (no shift — no prior deletes).
    """
    cell_content, base_doc = _make_base_with_table_cell(414, 496)

    # Alignment: all base elements matched, insert one desired element at front.
    alignment = ContentAlignment(
        matches=[
            ContentMatch(base_idx=0, desired_idx=1),
            ContentMatch(base_idx=1, desired_idx=2),
            ContentMatch(base_idx=2, desired_idx=3),
        ],
        base_deletes=[],
        desired_inserts=[0],
        total_cost=0.0,
    )
    desired_content = [
        _none_indexed_para("NEW\n"),  # inserted, None indices
        cell_content[0],  # matched — reuse base with concrete indices
        cell_content[1],
        cell_content[2],
    ]

    op = UpdateBodyContentOp(
        tab_id="",
        story_kind="table_cell",
        story_id="r0:c0",
        alignment=alignment,
        base_content=cell_content,
        desired_content=desired_content,
    )

    batches = lower_batches([op])
    reqs = [_req_to_dict(r) for r in batches[0]]

    # Expect exactly one insertText landing at base anchor = 414 (start of
    # the cell's first paragraph).
    inserts = [r for r in reqs if "insertText" in r]
    assert len(inserts) == 1
    assert inserts[0]["insertText"]["location"]["index"] == 414
    assert inserts[0]["insertText"]["text"] == "NEW\n"

    assert simulate_ops_against_base(base_doc, reqs) == []


# ---------------------------------------------------------------------------
# Scenario 3: CoordinateNotResolvedError raised loudly on corrupt base
# ---------------------------------------------------------------------------


def test_corrupt_base_element_raises_coordinate_error() -> None:
    """If the base tree is corrupt (a base paragraph has start=None AND
    end=None), lowering must raise ``CoordinateNotResolvedError`` with a
    message identifying the site — not silently skip or fabricate indices.
    """
    # Corrupt base: paragraph with fully-None indices.
    corrupt_base = [
        StructuralElement(
            start_index=None,
            end_index=None,
            paragraph=Paragraph(
                elements=[ParagraphElement(text_run=TextRun(content="broken\n"))],
                paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
            ),
        )
    ]

    alignment = ContentAlignment(
        matches=[],
        base_deletes=[0],
        desired_inserts=[],
        total_cost=0.0,
    )

    op = UpdateBodyContentOp(
        tab_id="",
        story_kind="body",
        story_id="body",
        alignment=alignment,
        base_content=corrupt_base,
        desired_content=[],
    )

    with pytest.raises(CoordinateNotResolvedError) as excinfo:
        lower_batches([op])

    msg = str(excinfo.value)
    assert "base_idx=0" in msg
    assert "concrete" in msg.lower()


# ---------------------------------------------------------------------------
# Scenario 4: FORM-15G-like — no op lands on cell boundary {496, 497}
# ---------------------------------------------------------------------------


def test_form15g_cell_boundary_not_touched() -> None:
    """Small 2-cell table; first cell [414..496), second cell follows.
    A join-collapse of the first cell must not emit any op touching the
    cell-boundary indices 496 or 497.
    """
    cell_content, base_doc = _make_base_with_table_cell(414, 496)

    desired_content = [_none_indexed_para("flat\n")]
    alignment = ContentAlignment(
        matches=[],
        base_deletes=[0, 1, 2],
        desired_inserts=[0],
        total_cost=0.0,
    )

    op = UpdateBodyContentOp(
        tab_id="",
        story_kind="table_cell",
        story_id="r0:c0",
        alignment=alignment,
        base_content=cell_content,
        desired_content=desired_content,
    )

    reqs = [_req_to_dict(r) for r in lower_batches([op])[0]]

    # Pin full op list structure: 3 deletes + 1 insert (+ optional style).
    deletes = [r for r in reqs if "deleteContentRange" in r]
    inserts = [r for r in reqs if "insertText" in r]
    assert len(deletes) == 3
    assert len(inserts) == 1

    # Verify no op starts at / inserts at the cell boundary {496, 497}.
    # (Exclusive endIndex=496 is legal — that's one-past-last-content-char.)
    for r in reqs:
        for key in ("deleteContentRange", "updateTextStyle", "updateParagraphStyle"):
            if key not in r:
                continue
            rng = r[key].get("range", {})
            assert rng.get("startIndex") not in (496, 497)
        if "insertText" in r:
            loc = r["insertText"].get("location", {})
            assert loc.get("index") not in (496, 497)

    assert simulate_ops_against_base(base_doc, reqs) == []


# ---------------------------------------------------------------------------
# Scenario 5: updateTextStyle range synthesis for inserted run
# ---------------------------------------------------------------------------


def test_inserted_run_text_style_range_uses_base_anchor() -> None:
    """A styled paragraph inserted into a None-indexed region must emit its
    updateTextStyle with a range anchored at base_anchor_start + local run
    offset — not at a stale desired-tree value.
    """
    cell_content, base_doc = _make_base_with_table_cell(414, 496)

    # Insert one styled paragraph at the start of the cell.
    styled_para = StructuralElement(
        start_index=None,
        end_index=None,
        paragraph=Paragraph(
            elements=[
                ParagraphElement(
                    start_index=None,
                    end_index=None,
                    text_run=TextRun(
                        content="HI\n",
                        text_style={"bold": True},
                    ),
                )
            ],
            paragraph_style=ParagraphStyle(named_style_type="NORMAL_TEXT"),
        ),
    )

    alignment = ContentAlignment(
        matches=[
            ContentMatch(base_idx=0, desired_idx=1),
            ContentMatch(base_idx=1, desired_idx=2),
            ContentMatch(base_idx=2, desired_idx=3),
        ],
        base_deletes=[],
        desired_inserts=[0],
        total_cost=0.0,
    )

    op = UpdateBodyContentOp(
        tab_id="",
        story_kind="table_cell",
        story_id="r0:c0",
        alignment=alignment,
        base_content=cell_content,
        desired_content=[styled_para, *cell_content],
    )

    reqs = [_req_to_dict(r) for r in lower_batches([op])[0]]

    # The insertText lands at the base anchor (start of cell's first paragraph).
    inserts = [r for r in reqs if "insertText" in r]
    assert len(inserts) == 1
    assert inserts[0]["insertText"]["location"]["index"] == 414

    # The updateTextStyle for the "HI\n" run must cover [414..417).
    styles = [r for r in reqs if "updateTextStyle" in r]
    assert len(styles) == 1
    rng = styles[0]["updateTextStyle"]["range"]
    assert rng["startIndex"] == 414
    assert rng["endIndex"] == 417  # 414 + len("HI\n")

    assert simulate_ops_against_base(base_doc, reqs) == []
