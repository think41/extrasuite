"""Tests for ``simulate_ops_against_base``.

The simulator is a test-side oracle that detects batchUpdate requests that
would fail at the Google Docs API layer because their ranges/indices are
invalid against a base document (particularly: ranges that straddle
tableCell boundaries, or touch the body terminal newline).

The canonical motivating bug is FORM-15G: the reconciler emits a raw
``deleteContentRange`` that straddles a cell boundary (e.g. a delete of
``[496..497)`` where index 496 is the exclusive end of a table cell).
"""

from __future__ import annotations

from typing import Any

from tests.reconcile_v3.helpers import simulate_ops_against_base

# ---------------------------------------------------------------------------
# Hand-crafted base document fixture
# ---------------------------------------------------------------------------


def _make_base_doc_with_table() -> dict[str, Any]:
    """Build a minimal base doc with a table for simulator tests.

    Layout (indices hand-pinned, cell boundary deliberately at 496):

        [  0..  1) sectionBreak
        [  1..  6) paragraph "abcd\\n"
        [  6..496) table (t_start=6)
            row 0:
                cell 0 [ 10..250)  contains a paragraph "x\\n"
                cell 1 [260..495)  contains a paragraph "y\\n"
        [496..500) trailing paragraph "zzz\\n"
    """
    sb = {"startIndex": 0, "endIndex": 1, "sectionBreak": {}}
    p1 = {
        "startIndex": 1,
        "endIndex": 6,
        "paragraph": {
            "elements": [
                {
                    "startIndex": 1,
                    "endIndex": 6,
                    "textRun": {"content": "abcd\n"},
                }
            ],
        },
    }
    cell0_para = {
        "startIndex": 10,
        "endIndex": 12,
        "paragraph": {
            "elements": [
                {"startIndex": 10, "endIndex": 12, "textRun": {"content": "x\n"}}
            ]
        },
    }
    cell1_para = {
        "startIndex": 260,
        "endIndex": 262,
        "paragraph": {
            "elements": [
                {"startIndex": 260, "endIndex": 262, "textRun": {"content": "y\n"}}
            ]
        },
    }
    table = {
        "startIndex": 6,
        "endIndex": 496,
        "table": {
            "rows": 1,
            "columns": 2,
            "tableRows": [
                {
                    "startIndex": 7,
                    "endIndex": 495,
                    "tableCells": [
                        {
                            "startIndex": 10,
                            "endIndex": 250,
                            "content": [cell0_para],
                        },
                        {
                            "startIndex": 260,
                            "endIndex": 495,
                            "content": [cell1_para],
                        },
                    ],
                }
            ],
        },
    }
    trailing = {
        "startIndex": 496,
        "endIndex": 500,
        "paragraph": {
            "elements": [
                {
                    "startIndex": 496,
                    "endIndex": 500,
                    "textRun": {"content": "zzz\n"},
                }
            ]
        },
    }
    return {
        "documentId": "doc1",
        "tabs": [
            {
                "documentTab": {
                    "body": {"content": [sb, p1, table, trailing]},
                }
            }
        ],
    }


# ---------------------------------------------------------------------------
# Positive cases
# ---------------------------------------------------------------------------


def test_single_paragraph_replace_is_valid() -> None:
    """A delete + insert inside a single paragraph is accepted."""
    base = _make_base_doc_with_table()
    # Delete "bc" at [2..4) and insert "BC" at [2..4)
    reqs = [
        {"deleteContentRange": {"range": {"startIndex": 2, "endIndex": 4}}},
        {"insertText": {"location": {"index": 2}, "text": "BC"}},
    ]
    assert simulate_ops_against_base(base, reqs) == []


def test_insert_at_valid_index() -> None:
    base = _make_base_doc_with_table()
    reqs = [{"insertText": {"location": {"index": 3}, "text": "Q"}}]
    assert simulate_ops_against_base(base, reqs) == []


# ---------------------------------------------------------------------------
# Negative: cell boundary straddle
# ---------------------------------------------------------------------------


def test_delete_straddling_cell_boundary_is_rejected() -> None:
    """A delete that crosses a cell boundary is rejected.

    This is the FORM-15G class of bug: in the fixture, cell1 ends at 495
    and the trailing paragraph begins at 496. A delete of [493..497)
    strictly contains the cell-end boundary 495 and must be flagged.
    """
    base = _make_base_doc_with_table()
    reqs = [{"deleteContentRange": {"range": {"startIndex": 493, "endIndex": 497}}}]
    vs = simulate_ops_against_base(base, reqs)
    assert len(vs) == 1
    v = vs[0]
    assert v.op_type == "deleteContentRange"
    assert "tableCell boundary" in v.reason
    assert "495" in v.reason


def test_delete_terminal_newline_is_rejected() -> None:
    """Deleting up to the body terminal index must violate."""
    base = _make_base_doc_with_table()
    # terminal_end is 500; a delete ending at 500 touches it.
    reqs = [{"deleteContentRange": {"range": {"startIndex": 497, "endIndex": 500}}}]
    vs = simulate_ops_against_base(base, reqs)
    assert any("terminal" in v.reason for v in vs)


def test_delete_index_zero_is_rejected() -> None:
    base = _make_base_doc_with_table()
    reqs = [{"deleteContentRange": {"range": {"startIndex": 0, "endIndex": 1}}}]
    vs = simulate_ops_against_base(base, reqs)
    assert len(vs) == 1
    assert "index 0" in vs[0].reason


def test_insert_out_of_range_is_rejected() -> None:
    base = _make_base_doc_with_table()
    reqs = [{"insertText": {"location": {"index": 99999}, "text": "X"}}]
    vs = simulate_ops_against_base(base, reqs)
    assert len(vs) == 1
    assert vs[0].op_type == "insertText"


# ---------------------------------------------------------------------------
# Positive: multi-op shift tracking
# ---------------------------------------------------------------------------


def test_multi_op_with_shift_tracking() -> None:
    """Insert at 3 (+2 chars), then delete [5..6) — which is base [3..4)."""
    base = _make_base_doc_with_table()
    reqs = [
        {"insertText": {"location": {"index": 3}, "text": "QQ"}},
        {"deleteContentRange": {"range": {"startIndex": 5, "endIndex": 6}}},
    ]
    vs = simulate_ops_against_base(base, reqs)
    assert vs == [], f"expected no violations, got {vs}"


# ---------------------------------------------------------------------------
# Unrecognized request types pass through
# ---------------------------------------------------------------------------


def test_unrecognized_request_is_skipped() -> None:
    base = _make_base_doc_with_table()
    reqs = [{"someFutureRequest": {"foo": "bar"}}]
    assert simulate_ops_against_base(base, reqs) == []


# ---------------------------------------------------------------------------
# Table structural requests
# ---------------------------------------------------------------------------


def test_insert_table_row_valid_start() -> None:
    base = _make_base_doc_with_table()
    reqs = [
        {
            "insertTableRow": {
                "tableCellLocation": {
                    "tableStartLocation": {"index": 6},
                    "rowIndex": 0,
                    "columnIndex": 0,
                },
                "insertBelow": True,
            }
        }
    ]
    assert simulate_ops_against_base(base, reqs) == []


def test_insert_table_row_bogus_start_rejected() -> None:
    base = _make_base_doc_with_table()
    reqs = [
        {
            "insertTableRow": {
                "tableCellLocation": {
                    "tableStartLocation": {"index": 999},
                    "rowIndex": 0,
                    "columnIndex": 0,
                },
                "insertBelow": True,
            }
        }
    ]
    vs = simulate_ops_against_base(base, reqs)
    assert len(vs) == 1
    assert vs[0].op_type == "insertTableRow"
