"""Tests for v2/generators/structural.py."""

from extradoc.generators.structural import StructuralGenerator
from extradoc.types import ChangeNode, ChangeOp, NodeType, SegmentType

TAB_ID = "t.0"


class TestHeaderFooter:
    def test_add_header(self):
        gen = StructuralGenerator()
        node = ChangeNode(
            node_type=NodeType.SEGMENT,
            op=ChangeOp.ADDED,
            segment_type=SegmentType.HEADER,
            segment_id="hdr1",
        )
        reqs = gen.emit_header_footer(node, tab_id=TAB_ID)
        assert len(reqs) == 1
        assert "createHeader" in reqs[0]
        assert reqs[0]["createHeader"]["type"] == "DEFAULT"
        assert reqs[0]["createHeader"]["sectionBreakLocation"]["tabId"] == TAB_ID

    def test_add_footer(self):
        gen = StructuralGenerator()
        node = ChangeNode(
            node_type=NodeType.SEGMENT,
            op=ChangeOp.ADDED,
            segment_type=SegmentType.FOOTER,
            segment_id="ftr1",
        )
        reqs = gen.emit_header_footer(node, tab_id=TAB_ID)
        assert len(reqs) == 1
        assert "createFooter" in reqs[0]
        assert reqs[0]["createFooter"]["sectionBreakLocation"]["tabId"] == TAB_ID

    def test_delete_header(self):
        gen = StructuralGenerator()
        node = ChangeNode(
            node_type=NodeType.SEGMENT,
            op=ChangeOp.DELETED,
            segment_type=SegmentType.HEADER,
            segment_id="hdr1",
            node_id="hdr1",
        )
        reqs = gen.emit_header_footer(node, tab_id=TAB_ID)
        assert len(reqs) == 1
        assert "deleteHeader" in reqs[0]
        assert reqs[0]["deleteHeader"]["headerId"] == "hdr1"
        assert reqs[0]["deleteHeader"]["tabId"] == TAB_ID

    def test_delete_footer(self):
        gen = StructuralGenerator()
        node = ChangeNode(
            node_type=NodeType.SEGMENT,
            op=ChangeOp.DELETED,
            segment_type=SegmentType.FOOTER,
            segment_id="ftr1",
            node_id="ftr1",
        )
        reqs = gen.emit_header_footer(node, tab_id=TAB_ID)
        assert len(reqs) == 1
        assert "deleteFooter" in reqs[0]
        assert reqs[0]["deleteFooter"]["footerId"] == "ftr1"
        assert reqs[0]["deleteFooter"]["tabId"] == TAB_ID

    def test_unchanged_produces_nothing(self):
        gen = StructuralGenerator()
        node = ChangeNode(
            node_type=NodeType.SEGMENT,
            op=ChangeOp.UNCHANGED,
            segment_type=SegmentType.HEADER,
        )
        reqs = gen.emit_header_footer(node, tab_id=TAB_ID)
        assert reqs == []


class TestTab:
    def test_add_tab(self):
        gen = StructuralGenerator()
        node = ChangeNode(
            node_type=NodeType.SEGMENT,
            op=ChangeOp.ADDED,
            node_id="tab1",
            after_xml='<tab title="My Tab"/>',
        )
        reqs = gen.emit_tab(node)
        assert len(reqs) == 1
        assert "addDocumentTab" in reqs[0]
        assert reqs[0]["addDocumentTab"]["tabProperties"]["title"] == "My Tab"

    def test_delete_tab(self):
        gen = StructuralGenerator()
        node = ChangeNode(
            node_type=NodeType.SEGMENT,
            op=ChangeOp.DELETED,
            node_id="tab1",
        )
        reqs = gen.emit_tab(node)
        assert len(reqs) == 1
        assert "deleteTab" in reqs[0]
        assert reqs[0]["deleteTab"]["tabId"] == "tab1"


class TestFootnote:
    def test_add_footnote(self):
        gen = StructuralGenerator()
        node = ChangeNode(
            node_type=NodeType.SEGMENT,
            op=ChangeOp.ADDED,
            segment_type=SegmentType.FOOTNOTE,
            segment_id="fn1",
            node_id="fn1",
        )
        reqs = gen.emit_footnote(node, tab_id=TAB_ID)
        assert len(reqs) == 1
        assert "createFootnote" in reqs[0]
        assert reqs[0]["createFootnote"]["endOfSegmentLocation"]["tabId"] == TAB_ID

    def test_delete_footnote_with_content_xml(self):
        gen = StructuralGenerator()
        node = ChangeNode(
            node_type=NodeType.SEGMENT,
            op=ChangeOp.DELETED,
            segment_type=SegmentType.FOOTNOTE,
            segment_id="fn1",
            node_id="fn1",
        )
        content_xml = '<p>Before<footnote id="fn1"><p>Note</p></footnote>After</p>'
        reqs = gen.emit_footnote(node, content_xml, base_index=1, tab_id=TAB_ID)
        assert len(reqs) == 1
        assert "deleteContentRange" in reqs[0]
        rng = reqs[0]["deleteContentRange"]["range"]
        # "Before" = 6 chars + base_index=1 = 7
        assert rng["startIndex"] == 7
        assert rng["endIndex"] == 8  # 1-character footnote reference
        assert rng["tabId"] == TAB_ID

    def test_delete_footnote_no_content(self):
        gen = StructuralGenerator()
        node = ChangeNode(
            node_type=NodeType.SEGMENT,
            op=ChangeOp.DELETED,
            segment_type=SegmentType.FOOTNOTE,
            segment_id="fn1",
            node_id="fn1",
        )
        reqs = gen.emit_footnote(node, None, base_index=1, tab_id=TAB_ID)
        # Can't calculate index without content
        assert reqs == []
