"""Tests for v2/types.py."""

from extradoc.types import (
    AlignedPair,
    ChangeNode,
    ChangeOp,
    DocumentBlock,
    NodeType,
    ParagraphBlock,
    SegmentBlock,
    SegmentContext,
    SegmentType,
    TabBlock,
    TableBlock,
)


def test_paragraph_block_content_hash():
    p = ParagraphBlock(tag="p", xml="<p>hello</p>")
    assert p.content_hash() == "<p>hello</p>"


def test_paragraph_block_content_hash_strips_comment_refs():
    """Adding a comment-ref should not change the content hash."""
    plain = ParagraphBlock(
        tag="p", xml='<p><span class="s1"><i>Some text</i></span></p>'
    )
    with_ref = ParagraphBlock(
        tag="p",
        xml='<p><span class="s1"><i><comment-ref id="c1">Some text</comment-ref></i></span></p>',
    )
    assert plain.content_hash() == with_ref.content_hash()


def test_paragraph_block_content_hash_strips_comment_ref_with_attrs():
    """Comment-ref with multiple attributes should be stripped."""
    plain = ParagraphBlock(tag="p", xml="<p>hello world</p>")
    with_ref = ParagraphBlock(
        tag="p",
        xml='<p><comment-ref id="c1" message="test" replies="0" resolved="false">hello world</comment-ref></p>',
    )
    assert plain.content_hash() == with_ref.content_hash()


def test_paragraph_block_xml_preserves_comment_refs():
    """The raw xml field should still contain comment-ref tags."""
    xml = '<p><comment-ref id="c1">text</comment-ref></p>'
    p = ParagraphBlock(tag="p", xml=xml)
    assert "comment-ref" in p.xml


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
    ctx = SegmentContext(segment_id=None, segment_end=100, tab_id="t.0")
    assert ctx.segment_end_consumed is False


def test_change_node_defaults():
    node = ChangeNode(node_type=NodeType.DOCUMENT, op=ChangeOp.UNCHANGED)
    assert node.children == []
    assert node.segment_type is None
    assert node.pristine_start == 0


def test_document_block_structure():
    doc = DocumentBlock(doc_id="doc1")
    tab = TabBlock(tab_id="t.0", title="Tab 1")
    seg = SegmentBlock(segment_type=SegmentType.BODY, segment_id="body")
    tab.segments.append(seg)
    doc.tabs.append(tab)
    assert len(doc.tabs) == 1
    assert len(doc.tabs[0].segments) == 1
    assert doc.tabs[0].segments[0].segment_type == SegmentType.BODY
