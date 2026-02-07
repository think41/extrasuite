"""Tests for v2/types.py."""

from extradoc.v2.types import (
    AlignedPair,
    ChangeNode,
    ChangeOp,
    DocumentBlock,
    NodeType,
    ParagraphBlock,
    SegmentBlock,
    SegmentContext,
    SegmentType,
    TableBlock,
)


def test_paragraph_block_content_hash():
    p = ParagraphBlock(tag="p", xml="<p>hello</p>")
    assert p.content_hash() == "<p>hello</p>"


def test_paragraph_block_structural_key():
    p = ParagraphBlock(tag="h1", xml="<h1>Title</h1>")
    assert p.structural_key() == "para:h1"


def test_table_block_structural_key():
    t = TableBlock(table_id="t1", xml="<table/>")
    assert t.structural_key() == "table"


def test_aligned_pair_frozen():
    pair = AlignedPair(pristine_idx=0, current_idx=1)
    assert pair.pristine_idx == 0
    assert pair.current_idx == 1
    # Frozen dataclass - can be used in sets
    s = {pair}
    assert len(s) == 1


def test_segment_context_defaults():
    ctx = SegmentContext(segment_id=None, segment_end=100)
    assert ctx.segment_end_consumed is False


def test_change_node_defaults():
    node = ChangeNode(node_type=NodeType.DOCUMENT, op=ChangeOp.UNCHANGED)
    assert node.children == []
    assert node.segment_type is None
    assert node.pristine_start == 0


def test_document_block_structure():
    doc = DocumentBlock(doc_id="doc1", revision="rev1")
    seg = SegmentBlock(segment_type=SegmentType.BODY, segment_id="body")
    doc.segments.append(seg)
    assert len(doc.segments) == 1
    assert doc.segments[0].segment_type == SegmentType.BODY
