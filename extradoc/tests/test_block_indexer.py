"""Tests for v2/indexer.py."""

from extradoc.block_indexer import BlockIndexer
from extradoc.parser import BlockParser
from extradoc.types import ParagraphBlock, SegmentType, TableBlock, TocBlock


def _parse_and_index(body_content: str) -> list:
    """Helper: parse doc and compute indexes, return body children."""
    xml = f'<doc id="d" revision="r"><tab id="t.0" title="Tab 1"><body class="_base">{body_content}</body></tab></doc>'
    parser = BlockParser()
    doc = parser.parse(xml)
    indexer = BlockIndexer()
    indexer.compute(doc)
    return doc.tabs[0].segments[0].children


class TestBlockIndexer:
    def test_single_paragraph(self):
        """Body starts at index 1. 'Hello' = 5 chars + 1 newline = 6."""
        children = _parse_and_index("<p>Hello</p>")
        assert len(children) == 1
        p = children[0]
        assert isinstance(p, ParagraphBlock)
        assert p.start_index == 1
        assert p.end_index == 7  # 1 + 5 + 1 = 7

    def test_two_paragraphs(self):
        children = _parse_and_index("<p>Hi</p><p>Bye</p>")
        assert len(children) == 2
        p1, p2 = children
        assert p1.start_index == 1
        assert p1.end_index == 4  # 1 + 2 + 1 = 4
        assert p2.start_index == 4
        assert p2.end_index == 8  # 4 + 3 + 1 = 8

    def test_empty_paragraph(self):
        children = _parse_and_index("<p></p>")
        p = children[0]
        assert p.start_index == 1
        assert p.end_index == 2  # 1 + 0 + 1 = 2 (just newline)

    def test_paragraph_with_bold(self):
        """Inline tags don't add length."""
        children = _parse_and_index("<p><b>Hi</b></p>")
        p = children[0]
        assert p.start_index == 1
        assert p.end_index == 4  # 1 + 2 + 1 = 4

    def test_simple_table(self):
        """Table: 1(table) + 1(row) + 1(cell) + 1(newline) + 1(end) = 5 for 1x1 empty."""
        children = _parse_and_index(
            '<table id="t1"><tr id="r1"><td id="0,0"><p>AB</p></td></tr></table>'
        )
        table = children[0]
        assert isinstance(table, TableBlock)
        assert table.start_index == 1
        # table_start(1) + row_marker(1) + cell_marker(1) + "AB"(2) + newline(1) + table_end(1) = 7
        assert table.end_index == 8  # 1 + 7 = 8

    def test_table_row_and_cell_indexes(self):
        children = _parse_and_index(
            '<table id="t1">'
            '<tr id="r1"><td id="0,0"><p>A</p></td><td id="0,1"><p>B</p></td></tr>'
            "</table>"
        )
        table = children[0]
        assert isinstance(table, TableBlock)
        row = table.rows[0]
        # Table start: 1, table marker: +1 = 2
        # Row starts at 2, marker: +1 = 3
        assert row.start_index == 2
        # Cell 0: marker at 3, content starts 4 = "A"(1)+\n(1) = 2, ends 6
        assert row.cells[0].start_index == 4
        assert row.cells[0].end_index == 6
        # Cell 1: marker at 6, content starts 7 = "B"(1)+\n(1) = 2, ends 9
        assert row.cells[1].start_index == 7
        assert row.cells[1].end_index == 9
        # Row ends at 9
        assert row.end_index == 9
        # Table: 9 + 1 (end marker) = 10
        assert table.end_index == 10

    def test_header_starts_at_zero(self):
        """Headers start at index 0, not 1."""
        xml = '<doc id="d" revision="r"><tab id="t.0" title="Tab 1"><body class="_base"></body><header id="h1" class="_base"><p>Hi</p></header></tab></doc>'
        doc = BlockParser().parse(xml)
        BlockIndexer().compute(doc)
        header = doc.tabs[0].segments[1]
        assert header.segment_type == SegmentType.HEADER
        assert header.start_index == 0
        p = header.children[0]
        assert isinstance(p, ParagraphBlock)
        assert p.start_index == 0
        assert p.end_index == 3  # "Hi"(2) + \n(1) = 3

    def test_segment_end_index(self):
        xml = '<doc id="d" revision="r"><tab id="t.0" title="Tab 1"><body class="_base"><p>A</p><p>B</p></body></tab></doc>'
        doc = BlockParser().parse(xml)
        BlockIndexer().compute(doc)
        body = doc.tabs[0].segments[0]
        # A: 1 → 3, B: 3 → 5
        assert body.end_index == 5

    def test_special_element_counts_as_one(self):
        """<pagebreak/> counts as 1 index."""
        children = _parse_and_index("<p><pagebreak/>Text</p>")
        p = children[0]
        # pagebreak(1) + "Text"(4) + \n(1) = 6
        assert p.end_index - p.start_index == 6

    def test_toc_with_paragraphs(self):
        """TOC: 1(start) + paragraph lengths + 1(end). Subsequent content indexes correct."""
        children = _parse_and_index(
            "<p>Before</p><toc><p>Chapter 1</p><p>Chapter 2</p></toc><p>After</p>"
        )
        assert len(children) == 3
        p_before = children[0]
        toc = children[1]
        p_after = children[2]

        assert isinstance(p_before, ParagraphBlock)
        assert isinstance(toc, TocBlock)
        assert isinstance(p_after, ParagraphBlock)

        # "Before" = 6 chars + 1 newline = 7, starts at 1
        assert p_before.start_index == 1
        assert p_before.end_index == 8

        # TOC: start marker(1) + "Chapter 1"(9)+\n(1) + "Chapter 2"(9)+\n(1) + end marker(1) = 22
        assert toc.start_index == 8
        assert toc.end_index == 30

        # "After" starts at 30
        assert p_after.start_index == 30
        assert p_after.end_index == 36  # "After"(5) + \n(1)

    def test_empty_toc(self):
        """Empty TOC: start marker(1) + end marker(1) = 2."""
        children = _parse_and_index("<toc></toc>")
        assert len(children) == 1
        toc = children[0]
        assert isinstance(toc, TocBlock)
        assert toc.start_index == 1
        assert toc.end_index == 3  # 1 + 2 = 3

    def test_equation_uses_length_attribute(self):
        """<equation length="23"/> consumes 23 index units."""
        children = _parse_and_index(
            '<p><equation length="23"/> This is an equation</p>'
        )
        p = children[0]
        # equation(23) + " This is an equation"(20) + \n(1) = 44
        assert p.end_index - p.start_index == 44

    def test_equation_default_length_one(self):
        """<equation/> without length attribute defaults to 1."""
        children = _parse_and_index("<p><equation/> Text</p>")
        p = children[0]
        # equation(1) + " Text"(5) + \n(1) = 7
        assert p.end_index - p.start_index == 7

    def test_equation_shifts_subsequent_indexes(self):
        """Content after a paragraph with equation gets correct indexes."""
        children = _parse_and_index('<p><equation length="23"/>eq</p><p>After</p>')
        p1, p2 = children
        # p1: equation(23) + "eq"(2) + \n(1) = 26, starts at 1 → ends at 27
        assert p1.start_index == 1
        assert p1.end_index == 27
        # p2: "After"(5) + \n(1) = 6, starts at 27 → ends at 33
        assert p2.start_index == 27
        assert p2.end_index == 33

    def test_richlink_counts_as_one(self):
        """<richlink/> counts as 1 index unit."""
        children = _parse_and_index(
            '<p>See <richlink url="https://example.com" title="Example"/> here</p>'
        )
        p = children[0]
        # "See "(4) + richlink(1) + " here"(5) + \n(1) = 11
        assert p.end_index - p.start_index == 11
