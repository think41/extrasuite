"""Tests for v2/walker.py."""

from extradoc.v2.generators.content import ContentGenerator
from extradoc.v2.generators.structural import StructuralGenerator
from extradoc.v2.generators.table import TableGenerator
from extradoc.v2.types import ChangeNode, ChangeOp, NodeType, SegmentType
from extradoc.v2.walker import RequestWalker


def _make_walker() -> RequestWalker:
    content_gen = ContentGenerator()
    table_gen = TableGenerator(content_gen)
    structural_gen = StructuralGenerator()
    return RequestWalker(content_gen, table_gen, structural_gen)


class TestRequestWalker:
    def test_empty_tree(self):
        """No children = no requests."""
        walker = _make_walker()
        root = ChangeNode(node_type=NodeType.DOCUMENT, op=ChangeOp.UNCHANGED)
        reqs = walker.walk(root)
        assert reqs == []

    def test_single_content_delete(self):
        """Delete content block produces deleteContentRange."""
        walker = _make_walker()
        root = ChangeNode(
            node_type=NodeType.DOCUMENT,
            op=ChangeOp.UNCHANGED,
            children=[
                ChangeNode(
                    node_type=NodeType.SEGMENT,
                    op=ChangeOp.MODIFIED,
                    segment_type=SegmentType.BODY,
                    segment_id=None,
                    segment_end=20,
                    children=[
                        ChangeNode(
                            node_type=NodeType.CONTENT_BLOCK,
                            op=ChangeOp.DELETED,
                            before_xml="<p>Hello</p>",
                            pristine_start=1,
                            pristine_end=7,
                        ),
                    ],
                ),
            ],
        )
        reqs = walker.walk(root)
        assert len(reqs) == 1
        assert "deleteContentRange" in reqs[0]

    def test_single_content_add(self):
        """Add content block produces insertText + styling."""
        walker = _make_walker()
        root = ChangeNode(
            node_type=NodeType.DOCUMENT,
            op=ChangeOp.UNCHANGED,
            children=[
                ChangeNode(
                    node_type=NodeType.SEGMENT,
                    op=ChangeOp.MODIFIED,
                    segment_type=SegmentType.BODY,
                    segment_id=None,
                    segment_end=20,
                    children=[
                        ChangeNode(
                            node_type=NodeType.CONTENT_BLOCK,
                            op=ChangeOp.ADDED,
                            after_xml="<p>New</p>",
                            pristine_start=10,
                            pristine_end=10,
                        ),
                    ],
                ),
            ],
        )
        reqs = walker.walk(root)
        assert len(reqs) > 0
        assert "insertText" in reqs[0]

    def test_backwards_walk_order(self):
        """Two content blocks should be processed highest-pristine-start first."""
        walker = _make_walker()
        root = ChangeNode(
            node_type=NodeType.DOCUMENT,
            op=ChangeOp.UNCHANGED,
            children=[
                ChangeNode(
                    node_type=NodeType.SEGMENT,
                    op=ChangeOp.MODIFIED,
                    segment_type=SegmentType.BODY,
                    segment_id=None,
                    segment_end=30,
                    children=[
                        ChangeNode(
                            node_type=NodeType.CONTENT_BLOCK,
                            op=ChangeOp.DELETED,
                            before_xml="<p>First</p>",
                            pristine_start=1,
                            pristine_end=7,
                        ),
                        ChangeNode(
                            node_type=NodeType.CONTENT_BLOCK,
                            op=ChangeOp.DELETED,
                            before_xml="<p>Second</p>",
                            pristine_start=15,
                            pristine_end=22,
                        ),
                    ],
                ),
            ],
        )
        reqs = walker.walk(root)
        # Both should be deleteContentRange
        delete_reqs = [r for r in reqs if "deleteContentRange" in r]
        assert len(delete_reqs) == 2
        # Second (higher index) should come first due to backwards walk
        first_start = delete_reqs[0]["deleteContentRange"]["range"]["startIndex"]
        second_start = delete_reqs[1]["deleteContentRange"]["range"]["startIndex"]
        assert first_start > second_start

    def test_header_add(self):
        """Added header segment produces createHeader."""
        walker = _make_walker()
        root = ChangeNode(
            node_type=NodeType.DOCUMENT,
            op=ChangeOp.UNCHANGED,
            children=[
                ChangeNode(
                    node_type=NodeType.SEGMENT,
                    op=ChangeOp.ADDED,
                    segment_type=SegmentType.HEADER,
                    segment_id="hdr1",
                    node_id="hdr1",
                ),
            ],
        )
        reqs = walker.walk(root)
        assert len(reqs) == 1
        assert "createHeader" in reqs[0]

    def test_footer_delete(self):
        """Deleted footer segment produces deleteFooter."""
        walker = _make_walker()
        root = ChangeNode(
            node_type=NodeType.DOCUMENT,
            op=ChangeOp.UNCHANGED,
            children=[
                ChangeNode(
                    node_type=NodeType.SEGMENT,
                    op=ChangeOp.DELETED,
                    segment_type=SegmentType.FOOTER,
                    segment_id="ftr1",
                    node_id="ftr1",
                ),
            ],
        )
        reqs = walker.walk(root)
        assert len(reqs) == 1
        assert "deleteFooter" in reqs[0]

    def test_table_in_segment(self):
        """Table change in body segment produces table requests."""
        walker = _make_walker()
        root = ChangeNode(
            node_type=NodeType.DOCUMENT,
            op=ChangeOp.UNCHANGED,
            children=[
                ChangeNode(
                    node_type=NodeType.SEGMENT,
                    op=ChangeOp.MODIFIED,
                    segment_type=SegmentType.BODY,
                    segment_id=None,
                    segment_end=50,
                    children=[
                        ChangeNode(
                            node_type=NodeType.TABLE,
                            op=ChangeOp.DELETED,
                            before_xml='<table id="t1"><tr id="r1"><td id="0,0"><p>A</p></td></tr></table>',
                            pristine_start=5,
                            pristine_end=12,
                            table_start=5,
                        ),
                    ],
                ),
            ],
        )
        reqs = walker.walk(root)
        assert len(reqs) == 1
        assert "deleteContentRange" in reqs[0]

    def test_body_segment_id_is_none(self):
        """Body segment should resolve to None segment_id (no segmentId in requests)."""
        walker = _make_walker()
        root = ChangeNode(
            node_type=NodeType.DOCUMENT,
            op=ChangeOp.UNCHANGED,
            children=[
                ChangeNode(
                    node_type=NodeType.SEGMENT,
                    op=ChangeOp.MODIFIED,
                    segment_type=SegmentType.BODY,
                    segment_id="body",
                    segment_end=20,
                    children=[
                        ChangeNode(
                            node_type=NodeType.CONTENT_BLOCK,
                            op=ChangeOp.DELETED,
                            before_xml="<p>A</p>",
                            pristine_start=1,
                            pristine_end=3,
                        ),
                    ],
                ),
            ],
        )
        reqs = walker.walk(root)
        assert len(reqs) == 1
        rng = reqs[0]["deleteContentRange"]["range"]
        assert "segmentId" not in rng
