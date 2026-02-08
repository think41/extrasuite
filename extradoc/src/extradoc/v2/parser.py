"""XML to Block tree parser for ExtraDoc v2.

Parses document.xml into a typed block tree structure.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .types import (
    ColumnDef,
    DocumentBlock,
    FootnoteRef,
    ParagraphBlock,
    SegmentBlock,
    SegmentType,
    StructuralBlock,
    TabBlock,
    TableBlock,
    TableCellBlock,
    TableRowBlock,
)

# Tags that represent paragraph-like elements
PARAGRAPH_TAGS = frozenset(
    {"p", "h1", "h2", "h3", "h4", "h5", "h6", "title", "subtitle", "li"}
)


class BlockParser:
    """Parses ExtraDoc XML into a typed block tree."""

    def parse(self, xml_content: str) -> DocumentBlock:
        """Parse XML content into a DocumentBlock tree.

        Args:
            xml_content: The document.xml content

        Returns:
            A DocumentBlock with typed children organized by tabs
        """
        root = ET.fromstring(xml_content)

        doc = DocumentBlock(
            doc_id=root.get("id", ""),
            revision=root.get("revision", ""),
        )

        # Parse tabs
        for tab_elem in root.findall("tab"):
            tab_block = TabBlock(
                tab_id=tab_elem.get("id", ""),
                title=tab_elem.get("title", ""),
                xml=ET.tostring(tab_elem, encoding="unicode"),
            )

            # Body within tab
            body = tab_elem.find("body")
            if body is not None:
                segment = self._parse_segment(body, SegmentType.BODY, "body")
                tab_block.segments.append(segment)

            # Headers within tab
            for header in tab_elem.findall("header"):
                segment = self._parse_segment(
                    header, SegmentType.HEADER, header.get("id", "")
                )
                tab_block.segments.append(segment)

            # Footers within tab
            for footer in tab_elem.findall("footer"):
                segment = self._parse_segment(
                    footer, SegmentType.FOOTER, footer.get("id", "")
                )
                tab_block.segments.append(segment)

            # Footnotes within tab
            for footnote in tab_elem.findall("footnote"):
                segment = self._parse_segment(
                    footnote, SegmentType.FOOTNOTE, footnote.get("id", "")
                )
                tab_block.segments.append(segment)

            doc.tabs.append(tab_block)

        return doc

    def _parse_segment(
        self,
        elem: ET.Element,
        segment_type: SegmentType,
        segment_id: str,
    ) -> SegmentBlock:
        """Parse a segment element (body, header, footer, footnote)."""
        segment = SegmentBlock(
            segment_type=segment_type,
            segment_id=segment_id,
            class_attr=elem.get("class", "_base"),
        )
        segment.children = self._parse_structural_elements(elem)
        return segment

    def _parse_structural_elements(self, parent: ET.Element) -> list[StructuralBlock]:
        """Parse structural elements into typed blocks."""
        blocks: list[StructuralBlock] = []

        for child in parent:
            tag = child.tag

            if tag in PARAGRAPH_TAGS:
                blocks.append(self._parse_paragraph(child))

            elif tag == "table":
                blocks.append(self._parse_table(child))

            elif tag == "style":
                # Style wrapper — transfer class to children that lack their own
                wrapper_class = child.get("class")
                for styled_child in child:
                    if wrapper_class and not styled_child.get("class"):
                        styled_child.set("class", wrapper_class)
                    if styled_child.tag in PARAGRAPH_TAGS:
                        blocks.append(self._parse_paragraph(styled_child))
                    elif styled_child.tag == "table":
                        blocks.append(self._parse_table(styled_child))

            # toc, sectionBreak etc. are currently ignored in v2
            # (they're rare and read-only in practice)

        return blocks

    def _parse_paragraph(self, elem: ET.Element) -> ParagraphBlock:
        """Parse a single paragraph element."""
        # Strip tail whitespace — it's just XML formatting between elements
        # and would pollute content hashes (e.g. "\n      " differs by indent).
        saved_tail = elem.tail
        elem.tail = None
        xml = ET.tostring(elem, encoding="unicode")
        elem.tail = saved_tail

        para = ParagraphBlock(
            tag=elem.tag,
            xml=xml,
        )

        # Extract inline footnotes
        for fn in elem.iter("footnote"):
            fn_id = fn.get("id", "")
            fn_xml = ET.tostring(fn, encoding="unicode")
            # Collect children XML for footnote content
            children_xml = [ET.tostring(c, encoding="unicode") for c in fn]
            para.footnotes.append(
                FootnoteRef(
                    footnote_id=fn_id,
                    xml=fn_xml,
                    children_xml=children_xml,
                )
            )

        return para

    def _parse_table(self, table_elem: ET.Element) -> TableBlock:
        """Parse a table element into a TableBlock."""
        table_id = table_elem.get("id", "")
        xml = ET.tostring(table_elem, encoding="unicode")

        # Parse column definitions
        columns: list[ColumnDef] = []
        for col_elem in table_elem.findall("col"):
            col_id = col_elem.get("id", col_elem.get("index", str(len(columns))))
            width = col_elem.get("width", "")
            index = int(col_elem.get("index", str(len(columns))))
            columns.append(ColumnDef(col_id=col_id, width=width, index=index))

        # Parse rows
        rows: list[TableRowBlock] = []
        for row_idx, tr in enumerate(table_elem.findall("tr")):
            row_id = tr.get("id", f"r{row_idx}")
            row_xml = ET.tostring(tr, encoding="unicode")

            # Parse cells
            cells: list[TableCellBlock] = []
            for col_idx, td in enumerate(tr.findall("td")):
                cell_id = td.get("id", f"{row_idx},{col_idx}")
                cell_xml = ET.tostring(td, encoding="unicode")

                # Recursively parse cell content
                cell_children = self._parse_structural_elements(td)

                cells.append(
                    TableCellBlock(
                        cell_id=cell_id,
                        col_index=col_idx,
                        xml=cell_xml,
                        children=cell_children,
                    )
                )

            rows.append(
                TableRowBlock(
                    row_id=row_id,
                    row_index=row_idx,
                    xml=row_xml,
                    cells=cells,
                )
            )

        return TableBlock(
            table_id=table_id,
            xml=xml,
            columns=columns,
            rows=rows,
        )
