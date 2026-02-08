"""Tests for v2/generators/table.py."""

import xml.etree.ElementTree as ET

from extradoc.v2.generators.content import ContentGenerator
from extradoc.v2.generators.table import (
    TableGenerator,
    _calculate_cell_content_length,
    _calculate_nested_table_length,
    _calculate_new_table_cell_starts,
    _extract_cell_inner_content,
    _extract_column_widths,
    _get_cell_xml_from_table,
    _get_pristine_cell_length,
    _parse_table_xml,
)
from extradoc.v2.types import ChangeNode, ChangeOp, NodeType, SegmentContext


def _body_ctx(segment_end: int = 100) -> SegmentContext:
    return SegmentContext(segment_id=None, segment_end=segment_end, tab_id="t.0")


class TestParseTableXml:
    def test_basic_table(self):
        xml = '<table id="t1"><tr id="r1"><td id="0,0"><p>A</p></td><td id="0,1"><p>B</p></td></tr></table>'
        result = _parse_table_xml(xml)
        assert result["rows"] == 1
        assert result["cols"] == 2
        assert result["id"] == "t1"

    def test_multi_row_table(self):
        xml = (
            '<table id="t1">'
            '<tr id="r1"><td id="0,0"><p>A</p></td></tr>'
            '<tr id="r2"><td id="1,0"><p>B</p></td></tr>'
            "</table>"
        )
        result = _parse_table_xml(xml)
        assert result["rows"] == 2
        assert result["cols"] == 1


class TestCalculateNewTableCellStarts:
    def test_1x1_table(self):
        starts = _calculate_new_table_cell_starts(1, 1, 1)
        # idx = 1 + 1(newline) + 1(table) = 3; +1(row) = 4; +1(cell) = 5
        assert starts[(0, 0)] == 5

    def test_2x2_table(self):
        starts = _calculate_new_table_cell_starts(1, 2, 2)
        # All 4 cells should have entries
        assert (0, 0) in starts
        assert (0, 1) in starts
        assert (1, 0) in starts
        assert (1, 1) in starts
        # Cell (0,0) < Cell (0,1) < Cell (1,0) < Cell (1,1)
        assert starts[(0, 0)] < starts[(0, 1)]
        assert starts[(0, 1)] < starts[(1, 0)]
        assert starts[(1, 0)] < starts[(1, 1)]


class TestNestedTableLength:
    def test_1x1_empty_cell(self):
        """1x1 table with empty cell: table(1) + row(1) + cell(1) + content(1) + end(1) = 5."""
        root = ET.fromstring(
            '<table id="t1"><tr id="r1"><td id="0,0"></td></tr></table>'
        )
        length = _calculate_nested_table_length(root)
        assert length == 5  # 1+1+1+1+1

    def test_1x1_with_paragraph(self):
        """1x1 table with 'AB': table(1) + row(1) + cell(1) + (AB=2 + nl=1) + end(1) = 7."""
        root = ET.fromstring(
            '<table id="t1"><tr id="r1"><td id="0,0"><p>AB</p></td></tr></table>'
        )
        length = _calculate_nested_table_length(root)
        assert length == 7


class TestCellContentLength:
    def test_empty_cell(self):
        td = ET.fromstring('<td id="0,0"></td>')
        assert _calculate_cell_content_length(td) == 1

    def test_cell_with_paragraph(self):
        td = ET.fromstring('<td id="0,0"><p>ABC</p></td>')
        assert _calculate_cell_content_length(td) == 4  # 3 chars + 1 newline


class TestExtractCellInnerContent:
    def test_basic_cell(self):
        result = _extract_cell_inner_content('<td id="0,0"><p>Hello</p></td>')
        assert "<p>Hello</p>" in result

    def test_empty_cell(self):
        result = _extract_cell_inner_content('<td id="0,0"></td>')
        assert result == ""


class TestGetCellXmlFromTable:
    def test_valid_cell(self):
        xml = '<table id="t1"><tr id="r1"><td id="0,0"><p>A</p></td><td id="0,1"><p>B</p></td></tr></table>'
        result = _get_cell_xml_from_table(xml, 0, 1)
        assert result is not None
        assert "B" in result

    def test_invalid_row(self):
        xml = '<table id="t1"><tr id="r1"><td id="0,0"><p>A</p></td></tr></table>'
        assert _get_cell_xml_from_table(xml, 5, 0) is None

    def test_invalid_col(self):
        xml = '<table id="t1"><tr id="r1"><td id="0,0"><p>A</p></td></tr></table>'
        assert _get_cell_xml_from_table(xml, 0, 5) is None


class TestGetPristineCellLength:
    def test_basic_cell(self):
        xml = '<table id="t1"><tr id="r1"><td id="0,0"><p>AB</p></td></tr></table>'
        length = _get_pristine_cell_length(xml, 0, 0)
        assert length == 3  # "AB"(2) + newline(1)


class TestExtractColumnWidths:
    def test_no_columns(self):
        xml = '<table id="t1"><tr id="r1"><td id="0,0"><p>A</p></td></tr></table>'
        assert _extract_column_widths(xml) == {}

    def test_with_columns(self):
        xml = '<table id="t1"><col id="c1" index="0" width="100pt"/><col id="c2" index="1" width="200pt"/><tr id="r1"><td id="0,0"><p>A</p></td></tr></table>'
        widths = _extract_column_widths(xml)
        assert widths == {0: "100pt", 1: "200pt"}

    def test_none_input(self):
        assert _extract_column_widths(None) == {}


class TestTableGeneratorAdd:
    def test_add_table(self):
        content_gen = ContentGenerator()
        gen = TableGenerator(content_gen)
        node = ChangeNode(
            node_type=NodeType.TABLE,
            op=ChangeOp.ADDED,
            after_xml='<table id="t1"><tr id="r1"><td id="0,0"><p>Cell</p></td></tr></table>',
            pristine_start=5,
            pristine_end=5,
            table_start=5,
        )
        reqs = gen.emit(node, _body_ctx())
        assert len(reqs) > 0
        assert "insertTable" in reqs[0]
        insert = reqs[0]["insertTable"]
        assert insert["rows"] == 1
        assert insert["columns"] == 1


class TestTableGeneratorDelete:
    def test_delete_table(self):
        content_gen = ContentGenerator()
        gen = TableGenerator(content_gen)
        node = ChangeNode(
            node_type=NodeType.TABLE,
            op=ChangeOp.DELETED,
            before_xml='<table id="t1"><tr id="r1"><td id="0,0"><p>AB</p></td></tr></table>',
            pristine_start=5,
            pristine_end=12,
            table_start=5,
        )
        reqs = gen.emit(node, _body_ctx())
        assert len(reqs) == 1
        assert "deleteContentRange" in reqs[0]
        rng = reqs[0]["deleteContentRange"]["range"]
        assert rng["startIndex"] == 5


class TestTableGeneratorModify:
    def test_column_width_change(self):
        """Column width change should produce updateTableColumnProperties."""
        content_gen = ContentGenerator()
        gen = TableGenerator(content_gen)
        node = ChangeNode(
            node_type=NodeType.TABLE,
            op=ChangeOp.MODIFIED,
            before_xml='<table id="t1"><col id="c1" index="0" width="100pt"/><tr id="r1"><td id="0,0"><p>A</p></td></tr></table>',
            after_xml='<table id="t1"><col id="c1" index="0" width="200pt"/><tr id="r1"><td id="0,0"><p>A</p></td></tr></table>',
            pristine_start=5,
            pristine_end=12,
            table_start=5,
            children=[],
        )
        reqs = gen.emit(node, _body_ctx())
        width_reqs = [r for r in reqs if "updateTableColumnProperties" in r]
        assert len(width_reqs) == 1
