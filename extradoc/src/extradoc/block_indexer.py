"""Single UTF-16 index calculator for ExtraDoc v2.

Replaces three separate implementations from v1:
1. block_diff.py: _calculate_block_indexes + helpers
2. diff_engine.py: _calculate_cell_content_length + helpers
3. indexer.py: calculate_table_indexes (on desugared objects)

Operates on the typed block tree from parser.py, mutating
start_index and end_index in place.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from extradoc.indexer import utf16_len

from .types import (
    DocumentBlock,
    ParagraphBlock,
    SegmentBlock,
    SegmentType,
    TableBlock,
    TableCellBlock,
    TocBlock,
)

# Tags that count as special elements (each consumes 1 index)
SPECIAL_TAGS = frozenset(
    {
        "hr",
        "pagebreak",
        "columnbreak",
        "image",
        "footnote",
        "person",
        "date",
        "richlink",
    }
)

# Tags that represent paragraph-like elements
PARAGRAPH_TAGS = frozenset(
    {"p", "h1", "h2", "h3", "h4", "h5", "h6", "title", "subtitle", "li"}
)


class BlockIndexer:
    """Computes UTF-16 indexes on the block tree (mutates in-place)."""

    def compute(self, doc: DocumentBlock) -> None:
        """Compute start_index and end_index for all blocks.

        Index spaces:
        - BODY starts at index 1 (after initial sectionBreak)
        - HEADER/FOOTER/FOOTNOTE start at index 0
        """
        for tab in doc.tabs:
            for segment in tab.segments:
                if segment.segment_type == SegmentType.BODY:
                    self._index_segment(segment, start=1)
                else:
                    self._index_segment(segment, start=0)

    def _index_segment(self, segment: SegmentBlock, start: int) -> None:
        """Walk children and set start/end indexes."""
        current = start
        segment.start_index = current

        for block in segment.children:
            if isinstance(block, ParagraphBlock):
                block.start_index = current
                length = self._paragraph_length(block)
                block.end_index = current + length
                current = block.end_index
            elif isinstance(block, TableBlock):
                block.start_index = current
                length = self._table_length(block)
                block.end_index = current + length
                current = block.end_index
            elif isinstance(block, TocBlock):
                block.start_index = current
                length = self._toc_length(block)
                block.end_index = current + length
                current = block.end_index

        segment.end_index = current

    def _paragraph_length(self, para: ParagraphBlock) -> int:
        """Calculate UTF-16 length of a paragraph.

        Length = text_content + special_elements + equation_lengths + 1 (newline)
        """
        try:
            root = ET.fromstring(para.xml)
        except ET.ParseError:
            return 1  # Minimum: just the newline

        text_length = self._text_length_from_xml(root)
        special_count = sum(1 for elem in root.iter() if elem.tag in SPECIAL_TAGS)
        equation_length = sum(
            int(elem.get("length", "1"))
            for elem in root.iter()
            if elem.tag == "equation"
        )

        return text_length + special_count + equation_length + 1

    def _table_length(self, table: TableBlock) -> int:
        """Calculate UTF-16 length of a table and set child indexes.

        Table structure:
        - 1 for table start marker
        - For each row: 1 for row marker
          - For each cell: 1 for cell marker + cell content
        - 1 for table end marker
        """
        current = table.start_index + 1  # after table start marker

        for row in table.rows:
            row.start_index = current
            current += 1  # row marker

            for cell in row.cells:
                current += 1  # cell marker
                cell.start_index = current

                cell_len = self._cell_content_length(cell)
                cell.end_index = current + cell_len
                current = cell.end_index

            row.end_index = current

        current += 1  # table end marker
        return current - table.start_index

    def _toc_length(self, toc: TocBlock) -> int:
        """Calculate UTF-16 length of a table of contents.

        TOC structure:
        - 1 for TOC start marker
        - Sum of paragraph lengths for each child paragraph
        - 1 for TOC end marker
        """
        try:
            root = ET.fromstring(toc.xml)
        except ET.ParseError:
            return 2  # Minimum: start + end markers

        length = 1  # TOC start marker

        for child in root:
            if child.tag in PARAGRAPH_TAGS:
                xml = ET.tostring(child, encoding="unicode")
                try:
                    para_root = ET.fromstring(xml)
                except ET.ParseError:
                    length += 1
                    continue
                text_len = self._text_length_from_xml(para_root)
                special_count = sum(
                    1 for elem in para_root.iter() if elem.tag in SPECIAL_TAGS
                )
                length += text_len + special_count + 1

        length += 1  # TOC end marker
        return length

    def _cell_content_length(self, cell: TableCellBlock) -> int:
        """Calculate UTF-16 length of cell content and set child indexes."""
        if not cell.children:
            return 1  # empty cell has default paragraph with newline

        length = 0
        current = cell.start_index
        for child in cell.children:
            if isinstance(child, ParagraphBlock):
                child.start_index = current
                plen = self._paragraph_length(child)
                child.end_index = current + plen
                current = child.end_index
                length += plen
            elif isinstance(child, TableBlock):
                # Nested table — need to calculate without setting indexes
                nested_len = self._nested_table_length_from_xml(child.xml)
                current += nested_len
                length += nested_len

        return max(length, 1)

    def _nested_table_length_from_xml(self, table_xml: str) -> int:
        """Calculate table length from XML (for nested tables in cells)."""
        try:
            root = ET.fromstring(table_xml)
        except ET.ParseError:
            return 2

        length = 1  # table start marker

        for tr in root.findall("tr"):
            length += 1  # row marker
            for td in tr.findall("td"):
                length += 1  # cell marker
                length += self._cell_content_length_from_xml(td)

        length += 1  # table end marker
        return length

    def _cell_content_length_from_xml(self, td_elem: ET.Element) -> int:
        """Calculate cell content length from a raw XML element."""
        children = list(td_elem)
        if not children:
            return 1  # empty cell

        length = 0
        for child in children:
            if child.tag in PARAGRAPH_TAGS:
                xml = ET.tostring(child, encoding="unicode")
                try:
                    root = ET.fromstring(xml)
                except ET.ParseError:
                    length += 1
                    continue
                text_len = self._text_length_from_xml(root)
                special_count = sum(
                    1 for elem in root.iter() if elem.tag in SPECIAL_TAGS
                )
                equation_length = sum(
                    int(elem.get("length", "1"))
                    for elem in root.iter()
                    if elem.tag == "equation"
                )
                length += text_len + special_count + equation_length + 1
            elif child.tag == "table":
                xml = ET.tostring(child, encoding="unicode")
                length += self._nested_table_length_from_xml(xml)

        return max(length, 1)

    def _text_length_from_xml(self, elem: ET.Element) -> int:
        """Recursively calculate text length, ignoring special elements and equations."""
        length = 0

        if elem.text:
            length += utf16_len(elem.text)

        for child in elem:
            if child.tag not in SPECIAL_TAGS and child.tag != "equation":
                length += self._text_length_from_xml(child)
            if child.tail:
                length += utf16_len(child.tail)

        return length
