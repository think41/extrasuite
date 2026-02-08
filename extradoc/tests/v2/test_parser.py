"""Tests for v2/parser.py."""

from extradoc.v2.parser import BlockParser
from extradoc.v2.types import (
    ParagraphBlock,
    SegmentType,
    TableBlock,
)


def _make_doc(
    body_content: str = "", headers: str = "", footers: str = "", footnotes: str = ""
) -> str:
    """Build a minimal document XML string."""
    return f'<doc id="test-id" revision="rev1"><tab id="t.0" title="Tab 1"><body class="_base">{body_content}</body>{headers}{footers}{footnotes}</tab></doc>'


class TestBlockParser:
    def test_empty_body(self):
        xml = _make_doc()
        parser = BlockParser()
        doc = parser.parse(xml)
        assert doc.doc_id == "test-id"
        assert doc.revision == "rev1"
        assert len(doc.tabs) == 1
        assert doc.tabs[0].tab_id == "t.0"
        assert len(doc.tabs[0].segments) == 1
        assert doc.tabs[0].segments[0].segment_type == SegmentType.BODY
        assert doc.tabs[0].segments[0].children == []

    def test_paragraphs(self):
        xml = _make_doc("<p>Hello</p><p>World</p>")
        doc = BlockParser().parse(xml)
        body = doc.tabs[0].segments[0]
        assert len(body.children) == 2
        assert all(isinstance(c, ParagraphBlock) for c in body.children)
        assert body.children[0].tag == "p"
        assert body.children[1].tag == "p"

    def test_heading_tags(self):
        xml = _make_doc("<h1>Title</h1><h2>Sub</h2><h3>Sub2</h3>")
        doc = BlockParser().parse(xml)
        body = doc.tabs[0].segments[0]
        assert len(body.children) == 3
        tags = [c.tag for c in body.children if isinstance(c, ParagraphBlock)]
        assert tags == ["h1", "h2", "h3"]

    def test_table(self):
        xml = _make_doc(
            '<table id="t1">'
            '<col id="c1" index="0"/>'
            '<col id="c2" index="1"/>'
            '<tr id="r1"><td id="0,0"><p>A</p></td><td id="0,1"><p>B</p></td></tr>'
            '<tr id="r2"><td id="1,0"><p>C</p></td><td id="1,1"><p>D</p></td></tr>'
            "</table>"
        )
        doc = BlockParser().parse(xml)
        body = doc.tabs[0].segments[0]
        assert len(body.children) == 1
        table = body.children[0]
        assert isinstance(table, TableBlock)
        assert table.table_id == "t1"
        assert len(table.columns) == 2
        assert table.columns[0].col_id == "c1"
        assert len(table.rows) == 2
        assert table.rows[0].row_id == "r1"
        assert len(table.rows[0].cells) == 2
        assert table.rows[0].cells[0].cell_id == "0,0"

    def test_mixed_content(self):
        xml = _make_doc(
            "<p>Before</p>"
            '<table id="t1"><tr id="r1"><td id="0,0"><p>Cell</p></td></tr></table>'
            "<p>After</p>"
        )
        doc = BlockParser().parse(xml)
        body = doc.tabs[0].segments[0]
        assert len(body.children) == 3
        assert isinstance(body.children[0], ParagraphBlock)
        assert isinstance(body.children[1], TableBlock)
        assert isinstance(body.children[2], ParagraphBlock)

    def test_headers_footers(self):
        xml = _make_doc(
            "<p>Body</p>",
            headers='<header id="hdr1" class="_base"><p>Header</p></header>',
            footers='<footer id="ftr1" class="_base"><p>Footer</p></footer>',
        )
        doc = BlockParser().parse(xml)
        assert len(doc.tabs[0].segments) == 3
        assert doc.tabs[0].segments[0].segment_type == SegmentType.BODY
        assert doc.tabs[0].segments[1].segment_type == SegmentType.HEADER
        assert doc.tabs[0].segments[1].segment_id == "hdr1"
        assert doc.tabs[0].segments[2].segment_type == SegmentType.FOOTER
        assert doc.tabs[0].segments[2].segment_id == "ftr1"

    def test_footnotes(self):
        xml = _make_doc(
            "<p>Body</p>",
            footnotes='<footnote id="fn1"><p>Footnote text</p></footnote>',
        )
        doc = BlockParser().parse(xml)
        assert len(doc.tabs[0].segments) == 2
        assert doc.tabs[0].segments[1].segment_type == SegmentType.FOOTNOTE
        assert doc.tabs[0].segments[1].segment_id == "fn1"

    def test_inline_footnote_in_paragraph(self):
        xml = _make_doc('<p>Text<footnote id="fn1"><p>Note</p></footnote></p>')
        doc = BlockParser().parse(xml)
        body = doc.tabs[0].segments[0]
        para = body.children[0]
        assert isinstance(para, ParagraphBlock)
        assert len(para.footnotes) == 1
        assert para.footnotes[0].footnote_id == "fn1"

    def test_list_items(self):
        xml = _make_doc(
            '<li type="bullet" level="0">Item 1</li>'
            '<li type="bullet" level="1">Item 2</li>'
        )
        doc = BlockParser().parse(xml)
        body = doc.tabs[0].segments[0]
        assert len(body.children) == 2
        assert all(
            isinstance(c, ParagraphBlock) and c.tag == "li" for c in body.children
        )

    def test_nested_table_in_cell(self):
        xml = _make_doc(
            '<table id="t1"><tr id="r1"><td id="0,0">'
            '<table id="t2"><tr id="nr1"><td id="n0,0"><p>Nested</p></td></tr></table>'
            "</td></tr></table>"
        )
        doc = BlockParser().parse(xml)
        body = doc.tabs[0].segments[0]
        table = body.children[0]
        assert isinstance(table, TableBlock)
        cell = table.rows[0].cells[0]
        assert len(cell.children) == 1
        nested = cell.children[0]
        assert isinstance(nested, TableBlock)
        assert nested.table_id == "t2"
