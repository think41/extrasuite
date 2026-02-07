"""Tests for v2/aligner.py."""

from extradoc.v2.aligner import BlockAligner
from extradoc.v2.types import (
    AlignedPair,
    ParagraphBlock,
    TableBlock,
    TableRowBlock,
)


def _p(text: str, tag: str = "p") -> ParagraphBlock:
    """Shorthand to create a paragraph block."""
    return ParagraphBlock(tag=tag, xml=f"<{tag}>{text}</{tag}>")


def _table(tid: str, xml: str = "") -> TableBlock:
    """Shorthand to create a table block."""
    if not xml:
        xml = f'<table id="{tid}"><tr id="r1"><td id="0,0"><p>X</p></td></tr></table>'
    return TableBlock(table_id=tid, xml=xml)


class TestBlockAligner:
    def test_identical_lists(self):
        """Identical lists produce all matched pairs."""
        aligner = BlockAligner()
        pristine = [_p("A"), _p("B"), _p("C")]
        current = [_p("A"), _p("B"), _p("C")]
        result = aligner.align(pristine, current)
        assert result == [
            AlignedPair(0, 0),
            AlignedPair(1, 1),
            AlignedPair(2, 2),
        ]

    def test_empty_lists(self):
        aligner = BlockAligner()
        result = aligner.align([], [])
        assert result == []

    def test_all_deleted(self):
        aligner = BlockAligner()
        result = aligner.align([_p("A"), _p("B")], [])
        assert result == [
            AlignedPair(0, None),
            AlignedPair(1, None),
        ]

    def test_all_added(self):
        aligner = BlockAligner()
        result = aligner.align([], [_p("A"), _p("B")])
        assert result == [
            AlignedPair(None, 0),
            AlignedPair(None, 1),
        ]

    def test_one_added_at_end(self):
        aligner = BlockAligner()
        pristine = [_p("A")]
        current = [_p("A"), _p("B")]
        result = aligner.align(pristine, current)
        assert result == [
            AlignedPair(0, 0),
            AlignedPair(None, 1),
        ]

    def test_one_deleted_from_end(self):
        aligner = BlockAligner()
        pristine = [_p("A"), _p("B")]
        current = [_p("A")]
        result = aligner.align(pristine, current)
        assert result == [
            AlignedPair(0, 0),
            AlignedPair(1, None),
        ]

    def test_modified_paragraph(self):
        """Modified paragraph falls back to structural key match."""
        aligner = BlockAligner()
        pristine = [_p("Hello")]
        current = [_p("World")]
        result = aligner.align(pristine, current)
        # Structural key match: both are para:p
        assert result == [AlignedPair(0, 0)]

    def test_reorder(self):
        """Reordered elements preserve current order."""
        aligner = BlockAligner()
        pristine = [_p("A"), _p("B"), _p("C")]
        current = [_p("C"), _p("A"), _p("B")]
        result = aligner.align(pristine, current)
        # C matches 2, A matches 0, B matches 1
        # In current order: C(2,0), A(0,1), B(1,2)
        matched = [(p.pristine_idx, p.current_idx) for p in result]
        assert (2, 0) in matched
        assert (0, 1) in matched
        assert (1, 2) in matched

    def test_structural_key_match_with_different_content(self):
        """Different content but same tag should match structurally."""
        aligner = BlockAligner()
        pristine = [_p("Old Title", "h1"), _p("Old body")]
        current = [_p("New Title", "h1"), _p("New body")]
        result = aligner.align(pristine, current)
        # h1 matches h1, p matches p
        assert result == [
            AlignedPair(0, 0),
            AlignedPair(1, 1),
        ]

    def test_mixed_additions_and_deletions(self):
        """Mix of additions, deletions, and matches."""
        aligner = BlockAligner()
        pristine = [_p("A"), _p("B"), _p("C")]
        current = [_p("A"), _p("D"), _p("C")]
        result = aligner.align(pristine, current)
        # A matches A (exact), C matches C (exact), D added, B deleted
        matched = {(p.pristine_idx, p.current_idx) for p in result}
        assert (0, 0) in matched  # A-A
        assert (2, 2) in matched  # C-C

    def test_table_and_paragraph_mix(self):
        """Tables and paragraphs are aligned independently."""
        aligner = BlockAligner()
        pristine = [_p("A"), _table("t1"), _p("B")]
        current = [_p("A"), _table("t1"), _p("B")]
        result = aligner.align(pristine, current)
        assert result == [
            AlignedPair(0, 0),
            AlignedPair(1, 1),
            AlignedPair(2, 2),
        ]


class TestAlignTableRows:
    def test_identical_rows(self):
        aligner = BlockAligner()
        pristine = [
            TableRowBlock(row_id="r1", row_index=0, xml="<tr/>"),
            TableRowBlock(row_id="r2", row_index=1, xml="<tr/>"),
        ]
        current = [
            TableRowBlock(row_id="r1", row_index=0, xml="<tr/>"),
            TableRowBlock(row_id="r2", row_index=1, xml="<tr/>"),
        ]
        result = aligner.align_table_rows(pristine, current)
        assert result == [
            AlignedPair(0, 0),
            AlignedPair(1, 1),
        ]

    def test_row_added(self):
        aligner = BlockAligner()
        pristine = [
            TableRowBlock(row_id="r1", row_index=0, xml="<tr/>"),
        ]
        current = [
            TableRowBlock(row_id="r1", row_index=0, xml="<tr/>"),
            TableRowBlock(row_id="r2", row_index=1, xml="<tr/>"),
        ]
        result = aligner.align_table_rows(pristine, current)
        assert result == [
            AlignedPair(0, 0),
            AlignedPair(None, 1),
        ]

    def test_row_deleted(self):
        aligner = BlockAligner()
        pristine = [
            TableRowBlock(row_id="r1", row_index=0, xml="<tr/>"),
            TableRowBlock(row_id="r2", row_index=1, xml="<tr/>"),
        ]
        current = [
            TableRowBlock(row_id="r1", row_index=0, xml="<tr/>"),
        ]
        result = aligner.align_table_rows(pristine, current)
        assert result == [
            AlignedPair(0, 0),
            AlignedPair(1, None),
        ]

    def test_row_reorder(self):
        aligner = BlockAligner()
        pristine = [
            TableRowBlock(row_id="r1", row_index=0, xml="<tr/>"),
            TableRowBlock(row_id="r2", row_index=1, xml="<tr/>"),
        ]
        current = [
            TableRowBlock(row_id="r2", row_index=0, xml="<tr/>"),
            TableRowBlock(row_id="r1", row_index=1, xml="<tr/>"),
        ]
        result = aligner.align_table_rows(pristine, current)
        # r2 in current[0] matches pristine[1], r1 in current[1] matches pristine[0]
        matched = {(p.pristine_idx, p.current_idx) for p in result}
        assert (1, 0) in matched
        assert (0, 1) in matched

    def test_empty_rows(self):
        aligner = BlockAligner()
        result = aligner.align_table_rows([], [])
        assert result == []
