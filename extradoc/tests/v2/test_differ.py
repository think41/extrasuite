"""Tests for v2/differ.py."""

from extradoc.v2.differ import TreeDiffer
from extradoc.v2.indexer import BlockIndexer
from extradoc.v2.parser import BlockParser
from extradoc.v2.types import ChangeOp, NodeType, SegmentType


def _make_doc(
    body_content: str, headers: str = "", footers: str = "", footnotes: str = ""
) -> str:
    return f'<doc id="d" revision="r"><body class="_base">{body_content}</body>{headers}{footers}{footnotes}</doc>'


def _parse_and_index(xml: str):
    parser = BlockParser()
    doc = parser.parse(xml)
    indexer = BlockIndexer()
    indexer.compute(doc)
    return doc


class TestTreeDiffer:
    def test_no_changes(self):
        """Identical documents produce no segment children."""
        xml = _make_doc("<p>Hello</p>")
        p = _parse_and_index(xml)
        c = _parse_and_index(xml)
        differ = TreeDiffer()
        root = differ.diff(p, c)
        assert root.node_type == NodeType.DOCUMENT
        assert root.op == ChangeOp.UNCHANGED
        assert len(root.children) == 0

    def test_paragraph_added(self):
        """Adding a paragraph produces CONTENT_BLOCK ADDED node."""
        p = _parse_and_index(_make_doc("<p>A</p>"))
        c = _parse_and_index(_make_doc("<p>A</p><p>B</p>"))
        differ = TreeDiffer()
        root = differ.diff(p, c)
        assert len(root.children) == 1
        seg = root.children[0]
        assert seg.node_type == NodeType.SEGMENT
        assert seg.op == ChangeOp.MODIFIED
        assert seg.segment_type == SegmentType.BODY

        content_nodes = [
            ch for ch in seg.children if ch.node_type == NodeType.CONTENT_BLOCK
        ]
        assert len(content_nodes) == 1
        assert content_nodes[0].op == ChangeOp.ADDED
        assert "<p>B</p>" in content_nodes[0].after_xml

    def test_paragraph_deleted(self):
        """Deleting a paragraph produces CONTENT_BLOCK DELETED node."""
        p = _parse_and_index(_make_doc("<p>A</p><p>B</p>"))
        c = _parse_and_index(_make_doc("<p>A</p>"))
        differ = TreeDiffer()
        root = differ.diff(p, c)
        seg = root.children[0]
        content_nodes = [
            ch for ch in seg.children if ch.node_type == NodeType.CONTENT_BLOCK
        ]
        assert len(content_nodes) == 1
        assert content_nodes[0].op == ChangeOp.DELETED
        assert content_nodes[0].pristine_start > 0

    def test_paragraph_modified(self):
        """Modifying a paragraph produces CONTENT_BLOCK MODIFIED node."""
        p = _parse_and_index(_make_doc("<p>Hello</p>"))
        c = _parse_and_index(_make_doc("<p>World</p>"))
        differ = TreeDiffer()
        root = differ.diff(p, c)
        seg = root.children[0]
        content_nodes = [
            ch for ch in seg.children if ch.node_type == NodeType.CONTENT_BLOCK
        ]
        assert len(content_nodes) == 1
        assert content_nodes[0].op == ChangeOp.MODIFIED
        assert "<p>Hello</p>" in content_nodes[0].before_xml
        assert "<p>World</p>" in content_nodes[0].after_xml

    def test_multiple_changes(self):
        """Multiple non-adjacent changes produce separate nodes."""
        p = _parse_and_index(_make_doc("<p>A</p><p>B</p><p>C</p>"))
        c = _parse_and_index(_make_doc("<p>X</p><p>B</p><p>Z</p>"))
        differ = TreeDiffer()
        root = differ.diff(p, c)
        seg = root.children[0]
        # A→X and C→Z separated by unchanged B
        content_nodes = [
            ch for ch in seg.children if ch.node_type == NodeType.CONTENT_BLOCK
        ]
        assert len(content_nodes) == 2
        # Both modified
        assert all(n.op == ChangeOp.MODIFIED for n in content_nodes)

    def test_consecutive_changes_grouped(self):
        """Consecutive same-op paragraphs should be grouped into one CONTENT_BLOCK."""
        p = _parse_and_index(_make_doc("<p>A</p><p>B</p>"))
        c = _parse_and_index(_make_doc("<p>X</p><p>Y</p>"))
        differ = TreeDiffer()
        root = differ.diff(p, c)
        seg = root.children[0]
        content_nodes = [
            ch for ch in seg.children if ch.node_type == NodeType.CONTENT_BLOCK
        ]
        assert len(content_nodes) == 1
        assert content_nodes[0].op == ChangeOp.MODIFIED

    def test_table_added(self):
        """Adding a table produces TABLE ADDED node."""
        p = _parse_and_index(_make_doc("<p>A</p>"))
        c = _parse_and_index(
            _make_doc(
                '<p>A</p><table id="t1"><tr id="r1"><td id="0,0"><p>Cell</p></td></tr></table>'
            )
        )
        differ = TreeDiffer()
        root = differ.diff(p, c)
        seg = root.children[0]
        table_nodes = [ch for ch in seg.children if ch.node_type == NodeType.TABLE]
        assert len(table_nodes) == 1
        assert table_nodes[0].op == ChangeOp.ADDED

    def test_table_deleted(self):
        """Deleting a table produces TABLE DELETED node."""
        p = _parse_and_index(
            _make_doc(
                '<p>A</p><table id="t1"><tr id="r1"><td id="0,0"><p>Cell</p></td></tr></table>'
            )
        )
        c = _parse_and_index(_make_doc("<p>A</p>"))
        differ = TreeDiffer()
        root = differ.diff(p, c)
        seg = root.children[0]
        table_nodes = [ch for ch in seg.children if ch.node_type == NodeType.TABLE]
        assert len(table_nodes) == 1
        assert table_nodes[0].op == ChangeOp.DELETED
        assert table_nodes[0].pristine_start > 0

    def test_table_modified_cell(self):
        """Modifying table cell produces TABLE MODIFIED with row/cell children."""
        p = _parse_and_index(
            _make_doc(
                '<table id="t1"><tr id="r1"><td id="0,0"><p>Old</p></td></tr></table>'
            )
        )
        c = _parse_and_index(
            _make_doc(
                '<table id="t1"><tr id="r1"><td id="0,0"><p>New</p></td></tr></table>'
            )
        )
        differ = TreeDiffer()
        root = differ.diff(p, c)
        seg = root.children[0]
        table_nodes = [ch for ch in seg.children if ch.node_type == NodeType.TABLE]
        assert len(table_nodes) == 1
        table = table_nodes[0]
        assert table.op == ChangeOp.MODIFIED
        # Should have row children
        row_nodes = [ch for ch in table.children if ch.node_type == NodeType.TABLE_ROW]
        assert len(row_nodes) >= 1

    def test_header_added(self):
        """Adding a header produces SEGMENT ADDED child."""
        p = _parse_and_index(_make_doc("<p>A</p>"))
        c = _parse_and_index(
            _make_doc(
                "<p>A</p>",
                headers='<header id="hdr1" class="_base"><p>Header</p></header>',
            )
        )
        differ = TreeDiffer()
        root = differ.diff(p, c)
        header_nodes = [
            ch
            for ch in root.children
            if ch.node_type == NodeType.SEGMENT
            and ch.segment_type == SegmentType.HEADER
        ]
        assert len(header_nodes) == 1
        assert header_nodes[0].op == ChangeOp.ADDED

    def test_header_deleted(self):
        """Deleting a header produces SEGMENT DELETED child."""
        p = _parse_and_index(
            _make_doc(
                "<p>A</p>",
                headers='<header id="hdr1" class="_base"><p>Header</p></header>',
            )
        )
        c = _parse_and_index(_make_doc("<p>A</p>"))
        differ = TreeDiffer()
        root = differ.diff(p, c)
        header_nodes = [
            ch
            for ch in root.children
            if ch.node_type == NodeType.SEGMENT
            and ch.segment_type == SegmentType.HEADER
        ]
        assert len(header_nodes) == 1
        assert header_nodes[0].op == ChangeOp.DELETED

    def test_footer_added(self):
        p = _parse_and_index(_make_doc("<p>A</p>"))
        c = _parse_and_index(
            _make_doc(
                "<p>A</p>",
                footers='<footer id="ftr1" class="_base"><p>Footer</p></footer>',
            )
        )
        differ = TreeDiffer()
        root = differ.diff(p, c)
        footer_nodes = [
            ch
            for ch in root.children
            if ch.node_type == NodeType.SEGMENT
            and ch.segment_type == SegmentType.FOOTER
        ]
        assert len(footer_nodes) == 1
        assert footer_nodes[0].op == ChangeOp.ADDED

    def test_table_row_added(self):
        """Adding a row produces TABLE_ROW ADDED child."""
        p_xml = '<table id="t1"><tr id="r1"><td id="0,0"><p>A</p></td></tr></table>'
        c_xml = '<table id="t1"><tr id="r1"><td id="0,0"><p>A</p></td></tr><tr id="r2"><td id="1,0"><p>B</p></td></tr></table>'
        p = _parse_and_index(_make_doc(p_xml))
        c = _parse_and_index(_make_doc(c_xml))
        differ = TreeDiffer()
        root = differ.diff(p, c)
        seg = root.children[0]
        table = seg.children[0]
        assert table.node_type == NodeType.TABLE
        row_nodes = [ch for ch in table.children if ch.node_type == NodeType.TABLE_ROW]
        added = [r for r in row_nodes if r.op == ChangeOp.ADDED]
        assert len(added) == 1

    def test_table_row_deleted(self):
        """Deleting a row produces TABLE_ROW DELETED child."""
        p_xml = '<table id="t1"><tr id="r1"><td id="0,0"><p>A</p></td></tr><tr id="r2"><td id="1,0"><p>B</p></td></tr></table>'
        c_xml = '<table id="t1"><tr id="r1"><td id="0,0"><p>A</p></td></tr></table>'
        p = _parse_and_index(_make_doc(p_xml))
        c = _parse_and_index(_make_doc(c_xml))
        differ = TreeDiffer()
        root = differ.diff(p, c)
        seg = root.children[0]
        table = seg.children[0]
        row_nodes = [ch for ch in table.children if ch.node_type == NodeType.TABLE_ROW]
        deleted = [r for r in row_nodes if r.op == ChangeOp.DELETED]
        assert len(deleted) == 1

    def test_pristine_indexes_on_changes(self):
        """Change nodes should have valid pristine_start/end."""
        p = _parse_and_index(_make_doc("<p>Hello</p><p>World</p>"))
        c = _parse_and_index(_make_doc("<p>Hello</p><p>Changed</p>"))
        differ = TreeDiffer()
        root = differ.diff(p, c)
        seg = root.children[0]
        content_nodes = [
            ch for ch in seg.children if ch.node_type == NodeType.CONTENT_BLOCK
        ]
        assert len(content_nodes) == 1
        node = content_nodes[0]
        # Should reference the "World" paragraph's index range
        assert node.pristine_start > 0
        assert node.pristine_end > node.pristine_start
