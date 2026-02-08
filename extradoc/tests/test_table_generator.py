"""Tests for v2/generators/table.py."""

import xml.etree.ElementTree as ET

from extradoc.generators.content import ContentGenerator
from extradoc.generators.table import (
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
from extradoc.types import ChangeNode, ChangeOp, NodeType, SegmentContext


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

    def test_row_delete_with_cell_mod_ordering(self):
        """Cell mods must appear before deleteTableRow in the request list.

        When a row is deleted and another row's cells are modified in the
        same table, the cell modifications (which use pristine body indices)
        must execute before the row delete (which shrinks the body and
        invalidates those indices).
        """
        content_gen = ContentGenerator()
        gen = TableGenerator(content_gen)

        # 3-row, 2-col table. Table starts at body index 10.
        # Row 0: header (unchanged)
        # Row 1: to be deleted
        # Row 2: cell modified (Alpha → Beta)
        before_xml = (
            '<table id="t1">'
            '<tr id="r0"><td id="c00"><p>H1</p></td><td id="c01"><p>H2</p></td></tr>'
            '<tr id="r1"><td id="c10"><p>Del1</p></td><td id="c11"><p>Del2</p></td></tr>'
            '<tr id="r2"><td id="c20"><p>Alpha</p></td><td id="c21"><p>Keep</p></td></tr>'
            "</table>"
        )
        after_xml = (
            '<table id="t1">'
            '<tr id="r0"><td id="c00"><p>H1</p></td><td id="c01"><p>H2</p></td></tr>'
            '<tr id="r2"><td id="c20"><p>Beta</p></td><td id="c21"><p>Keep</p></td></tr>'
            "</table>"
        )

        # Calculate pristine cell indices for row 2, col 0:
        # table_start(1) + row0_marker(1) + c00_marker(1) + "H1\n"(3) +
        # c01_marker(1) + "H2\n"(3) + row1_marker(1) + c10_marker(1) +
        # "Del1\n"(5) + c11_marker(1) + "Del2\n"(5) + row2_marker(1) +
        # c20_marker(1) = table_start + 26
        # So cell c20 content starts at 10 + 26 = 36
        # Cell c20 content is "Alpha\n" = 6 chars, ends at 42
        table_start = 10
        cell_c20_start = table_start + 26
        cell_c20_end = cell_c20_start + 6  # "Alpha\n"

        # Build the change tree
        cell_change = ChangeNode(
            node_type=NodeType.TABLE_CELL,
            op=ChangeOp.MODIFIED,
            node_id="c20",
            col_index=0,
            before_xml='<td id="c20"><p>Alpha</p></td>',
            after_xml='<td id="c20"><p>Beta</p></td>',
            pristine_start=cell_c20_start,
            pristine_end=cell_c20_end,
        )

        row_modified = ChangeNode(
            node_type=NodeType.TABLE_ROW,
            op=ChangeOp.MODIFIED,
            node_id="r2",
            row_index=1,  # In the final table, this is row 1
            before_xml='<tr id="r2"><td id="c20"><p>Alpha</p></td><td id="c21"><p>Keep</p></td></tr>',
            after_xml='<tr id="r2"><td id="c20"><p>Beta</p></td><td id="c21"><p>Keep</p></td></tr>',
            pristine_start=cell_c20_start - 1,  # row marker before first cell
            pristine_end=cell_c20_end + 6,  # includes c21 content
            children=[cell_change],
        )

        row_deleted = ChangeNode(
            node_type=NodeType.TABLE_ROW,
            op=ChangeOp.DELETED,
            node_id="r1",
            row_index=1,  # Pristine row index
            before_xml='<tr id="r1"><td id="c10"><p>Del1</p></td><td id="c11"><p>Del2</p></td></tr>',
        )

        table_node = ChangeNode(
            node_type=NodeType.TABLE,
            op=ChangeOp.MODIFIED,
            before_xml=before_xml,
            after_xml=after_xml,
            pristine_start=table_start,
            pristine_end=table_start + 50,
            table_start=table_start,
            children=[row_deleted, row_modified],
        )

        reqs = gen.emit(table_node, _body_ctx(segment_end=200))

        # Find the positions of cell mod requests and deleteTableRow
        delete_row_indices = [i for i, r in enumerate(reqs) if "deleteTableRow" in r]
        cell_mod_indices = [
            i
            for i, r in enumerate(reqs)
            if "deleteContentRange" in r or "insertText" in r
        ]

        assert len(delete_row_indices) >= 1, "Should have at least one deleteTableRow"
        assert len(cell_mod_indices) >= 1, "Should have at least one cell mod request"

        # All cell mods must come before all row deletes
        max_cell_mod = max(cell_mod_indices)
        min_row_delete = min(delete_row_indices)
        assert max_cell_mod < min_row_delete, (
            f"Cell mods (last at index {max_cell_mod}) must come before "
            f"row deletes (first at index {min_row_delete}). "
            f"Request types: {[next(iter(r.keys())) for r in reqs]}"
        )

    def test_column_delete_with_cell_mod_ordering(self):
        """Cell mods must appear before deleteTableColumn in the request list.

        Same issue as row deletes: column deletes shrink the body and
        invalidate pristine body indices used by cell modifications.
        """
        content_gen = ContentGenerator()
        gen = TableGenerator(content_gen)

        # 2-row, 3-col table. Column 1 deleted, cell (0, 2) modified.
        before_xml = (
            '<table id="t1">'
            '<tr id="r0"><td id="c00"><p>A</p></td><td id="c01"><p>B</p></td><td id="c02"><p>Old</p></td></tr>'
            '<tr id="r1"><td id="c10"><p>D</p></td><td id="c11"><p>E</p></td><td id="c12"><p>F</p></td></tr>'
            "</table>"
        )
        after_xml = (
            '<table id="t1">'
            '<tr id="r0"><td id="c00"><p>A</p></td><td id="c02"><p>New</p></td></tr>'
            '<tr id="r1"><td id="c10"><p>D</p></td><td id="c12"><p>F</p></td></tr>'
            "</table>"
        )

        table_start = 10
        # Cell c02 in pristine: after table(1) + row0(1) + c00(1) + "A\n"(2)
        # + c01(1) + "B\n"(2) + c02(1) = 10 + 9 = 19
        cell_c02_start = table_start + 9
        cell_c02_end = cell_c02_start + 4  # "Old\n"

        cell_change = ChangeNode(
            node_type=NodeType.TABLE_CELL,
            op=ChangeOp.MODIFIED,
            node_id="c02",
            col_index=2,
            before_xml='<td id="c02"><p>Old</p></td>',
            after_xml='<td id="c02"><p>New</p></td>',
            pristine_start=cell_c02_start,
            pristine_end=cell_c02_end,
        )

        row_modified = ChangeNode(
            node_type=NodeType.TABLE_ROW,
            op=ChangeOp.MODIFIED,
            node_id="r0",
            row_index=0,
            before_xml='<tr id="r0"><td id="c00"><p>A</p></td><td id="c01"><p>B</p></td><td id="c02"><p>Old</p></td></tr>',
            after_xml='<tr id="r0"><td id="c00"><p>A</p></td><td id="c02"><p>New</p></td></tr>',
            pristine_start=table_start + 1,
            pristine_end=cell_c02_end,
            children=[cell_change],
        )

        col_deleted = ChangeNode(
            node_type=NodeType.TABLE_COLUMN,
            op=ChangeOp.DELETED,
            col_index=1,
        )

        table_node = ChangeNode(
            node_type=NodeType.TABLE,
            op=ChangeOp.MODIFIED,
            before_xml=before_xml,
            after_xml=after_xml,
            pristine_start=table_start,
            pristine_end=table_start + 30,
            table_start=table_start,
            children=[col_deleted, row_modified],
        )

        reqs = gen.emit(table_node, _body_ctx(segment_end=200))

        delete_col_indices = [i for i, r in enumerate(reqs) if "deleteTableColumn" in r]
        cell_mod_indices = [
            i
            for i, r in enumerate(reqs)
            if "deleteContentRange" in r or "insertText" in r
        ]

        # Cell mods for non-deleted columns should exist
        # (col 2 is modified, col 1 is deleted — cell in col 2 should be modified)
        assert len(cell_mod_indices) >= 1, "Should have cell mod requests"
        assert len(delete_col_indices) >= 1, "Should have deleteTableColumn"

        max_cell_mod = max(cell_mod_indices)
        min_col_delete = min(delete_col_indices)
        assert max_cell_mod < min_col_delete, (
            f"Cell mods (last at index {max_cell_mod}) must come before "
            f"column deletes (first at index {min_col_delete}). "
            f"Request types: {[next(iter(r.keys())) for r in reqs]}"
        )
