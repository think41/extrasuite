"""Convert a Document (API types) to XML models (TabXml + StylesXml).

This is the serialize direction: Document → pydantic-xml intermediate models.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._models import (
    AutoTextNode,
    BlockNode,
    CellXml,
    ColumnBreakNode,
    ColXml,
    DateNode,
    EquationNode,
    FootnoteRefNode,
    FormattingNode,
    HrXml,
    ImageNode,
    InlineNode,
    LevelDefXml,
    LinkNode,
    ListDefXml,
    PageBreakXml,
    ParagraphXml,
    PersonNode,
    RichLinkNode,
    RowXml,
    SectionBreakXml,
    SegmentXml,
    SpanNode,
    TableXml,
    TabXml,
    TNode,
    TocXml,
)
from ._styles import (
    StyleCollector,
    StylesXml,
    determine_link_href,
    determine_sugar_tag,
    extract_cell_style,
    extract_col_style,
    extract_nesting_level,
    extract_para_style,
    extract_row_style,
    extract_text_style,
)
from ._utils import sanitize_tab_name

if TYPE_CHECKING:
    from extradoc.api_types._generated import (
        Document,
        DocumentTab,
        Paragraph,
        ParagraphElement,
        StructuralElement,
        Table,
        TextStyle,
    )
    from extradoc.api_types._generated import (
        List as DocList,
    )

# Mapping from ParagraphStyleNamedStyleType to XML tag
_NAMED_STYLE_TO_TAG: dict[str, str] = {
    "TITLE": "title",
    "SUBTITLE": "subtitle",
    "HEADING_1": "h1",
    "HEADING_2": "h2",
    "HEADING_3": "h3",
    "HEADING_4": "h4",
    "HEADING_5": "h5",
    "HEADING_6": "h6",
}


def document_to_xml(
    doc: Document,
) -> dict[str, tuple[TabXml, StylesXml]]:
    """Convert a Document to XML models.

    Returns dict mapping folder_name → (TabXml, StylesXml) for each tab.
    The folder_name is derived from the tab title.
    """
    result: dict[str, tuple[TabXml, StylesXml]] = {}

    for tab in doc.tabs or []:
        tab_props = tab.tab_properties
        tab_id = tab_props.tab_id or "t.0" if tab_props else "t.0"
        tab_title = tab_props.title or "Tab 1" if tab_props else "Tab 1"
        folder = sanitize_tab_name(tab_title)

        # Ensure unique folder names
        base_folder = folder
        counter = 2
        while folder in result:
            folder = f"{base_folder}_{counter}"
            counter += 1

        doc_tab = tab.document_tab
        if not doc_tab:
            continue

        collector = StyleCollector()
        tab_xml = _convert_tab(tab_id, tab_title, doc_tab, collector)
        styles_xml = collector.build()
        result[folder] = (tab_xml, styles_xml)

    return result


def _convert_tab(
    tab_id: str,
    tab_title: str,
    doc_tab: DocumentTab,
    collector: StyleCollector,
) -> TabXml:
    """Convert a single DocumentTab to TabXml."""
    tab_xml = TabXml(id=tab_id, title=tab_title)

    # Convert list definitions
    if doc_tab.lists:
        for list_id, doc_list in doc_tab.lists.items():
            tab_xml.lists.append(_convert_list_def(list_id, doc_list, collector))

    # Convert body
    if doc_tab.body and doc_tab.body.content:
        tab_xml.body = _convert_content(doc_tab.body.content, collector)

    # Convert headers
    if doc_tab.headers:
        for header_id, header in doc_tab.headers.items():
            if header.content:
                blocks = _convert_content(header.content, collector)
                tab_xml.headers.append(
                    SegmentXml(id=header_id, segment_type="header", blocks=blocks)
                )

    # Convert footers
    if doc_tab.footers:
        for footer_id, footer in doc_tab.footers.items():
            if footer.content:
                blocks = _convert_content(footer.content, collector)
                tab_xml.footers.append(
                    SegmentXml(id=footer_id, segment_type="footer", blocks=blocks)
                )

    # Convert footnotes
    if doc_tab.footnotes:
        for fn_id, footnote in doc_tab.footnotes.items():
            if footnote.content:
                blocks = _convert_content(footnote.content, collector)
                tab_xml.footnotes.append(
                    SegmentXml(id=fn_id, segment_type="footnote", blocks=blocks)
                )

    return tab_xml


def _convert_list_def(
    list_id: str,
    doc_list: DocList,
    collector: StyleCollector,
) -> ListDefXml:
    """Convert a List to ListDefXml."""
    levels: list[LevelDefXml] = []
    if doc_list.list_properties and doc_list.list_properties.nesting_levels:
        for idx, nl in enumerate(doc_list.list_properties.nesting_levels):
            style_attrs = extract_nesting_level(nl)
            class_name = collector.add_listlevel_style(style_attrs)
            levels.append(
                LevelDefXml(
                    index=idx,
                    glyph_type=nl.glyph_type.value if nl.glyph_type else None,
                    glyph_format=nl.glyph_format,
                    glyph_symbol=nl.glyph_symbol,
                    class_name=class_name,
                )
            )
    return ListDefXml(id=list_id, levels=levels)


def _convert_content(
    content: list[StructuralElement],
    collector: StyleCollector,
) -> list[BlockNode]:
    """Convert a list of StructuralElements to BlockNodes."""
    blocks: list[BlockNode] = []
    for se in content:
        if se.section_break:
            blocks.append(SectionBreakXml())
        elif se.paragraph:
            block = _convert_paragraph(se.paragraph, collector)
            if block is not None:
                blocks.append(block)
        elif se.table:
            blocks.append(_convert_table(se.table, collector))
        elif se.table_of_contents:
            toc_blocks: list[BlockNode] = []
            if se.table_of_contents.content:
                toc_blocks = _convert_content(se.table_of_contents.content, collector)
            blocks.append(TocXml(blocks=toc_blocks))
    return blocks


def _convert_paragraph(
    para: Paragraph,
    collector: StyleCollector,
) -> BlockNode | None:
    """Convert a Paragraph to a BlockNode.

    Returns None for empty paragraphs that are just section break trailing paras.
    """
    # Check for special single-element paragraphs
    elements = para.elements or []
    for pe in elements:
        if pe.horizontal_rule:
            return HrXml()
        if pe.page_break:
            return PageBreakXml()

    # Determine tag from named style
    ps = para.paragraph_style
    tag = "p"
    named_style = None
    if ps and ps.named_style_type:
        named_style = ps.named_style_type
        tag = _NAMED_STYLE_TO_TAG.get(named_style.value, "p")

    # If paragraph has a bullet, use <li>
    bullet = para.bullet
    if bullet:
        tag = "li"

    # Extract paragraph style (excluding named style type and heading ID)
    para_attrs = extract_para_style(ps)
    para_class = collector.add_para_style(para_attrs)

    # Convert inline elements
    inlines = _convert_elements(elements, collector)

    para_xml = ParagraphXml(
        tag=tag,
        inlines=inlines,
        class_name=para_class,
    )

    # Heading ID
    if (
        ps
        and ps.heading_id
        and tag
        in {
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "title",
            "subtitle",
        }
    ):
        para_xml.heading_id = ps.heading_id

    # List item attributes
    if bullet:
        para_xml.parent = bullet.list_id
        para_xml.level = bullet.nesting_level

    return para_xml


def _convert_elements(
    elements: list[ParagraphElement],
    collector: StyleCollector,
) -> list[InlineNode]:
    """Convert paragraph elements to inline nodes."""
    inlines: list[InlineNode] = []
    for pe in elements:
        if pe.text_run:
            text = pe.text_run.content or ""
            # Strip trailing newline (paragraph-ending)
            text = text.rstrip("\n")
            if not text:
                continue
            node = _convert_text_run(text, pe.text_run.text_style, collector)
            inlines.append(node)
        elif pe.inline_object_element:
            obj_id = pe.inline_object_element.inline_object_id or ""
            inlines.append(ImageNode(object_id=obj_id))
        elif pe.footnote_reference:
            fn_id = pe.footnote_reference.footnote_id or ""
            inlines.append(FootnoteRefNode(id=fn_id))
        elif pe.person:
            email = ""
            if pe.person.person_properties:
                email = pe.person.person_properties.email or ""
            inlines.append(PersonNode(email=email))
        elif pe.date_element:
            inlines.append(DateNode())
        elif pe.rich_link:
            url = ""
            if pe.rich_link.rich_link_properties:
                url = pe.rich_link.rich_link_properties.uri or ""
            inlines.append(RichLinkNode(url=url))
        elif pe.auto_text:
            inlines.append(AutoTextNode())
        elif pe.equation:
            inlines.append(EquationNode())
        elif pe.column_break:
            inlines.append(ColumnBreakNode())
    return inlines


def _convert_text_run(
    text: str,
    text_style: TextStyle | None,
    collector: StyleCollector,
) -> InlineNode:
    """Convert a text run to an inline node with appropriate sugar tag."""
    all_attrs = extract_text_style(text_style)

    if not all_attrs:
        # Plain text, no styles
        return TNode(text=text)

    t_nodes = [TNode(text=text)]

    # Check for link first
    href, remaining_after_link = determine_link_href(all_attrs)
    if href:
        class_name = collector.add_text_style(remaining_after_link)
        return LinkNode(href=href, children=t_nodes, class_name=class_name)

    # Check for sugar tag
    sugar_tag, remaining = determine_sugar_tag(all_attrs)
    if sugar_tag:
        class_name = collector.add_text_style(remaining)
        return FormattingNode(tag=sugar_tag, children=t_nodes, class_name=class_name)

    # No sugar tag — use <span>
    class_name = collector.add_text_style(all_attrs)
    if class_name:
        return SpanNode(class_name=class_name, children=t_nodes)

    # Fallback: plain text (shouldn't reach here if all_attrs is non-empty)
    return TNode(text=text)


def _convert_table(
    table: Table,
    collector: StyleCollector,
) -> TableXml:
    """Convert a Table to TableXml."""
    table_xml = TableXml()

    # Column styles from tableStyle
    if table.table_style and table.table_style.table_column_properties:
        for tcp in table.table_style.table_column_properties:
            col_attrs = extract_col_style(tcp)
            class_name = collector.add_col_style(col_attrs)
            table_xml.cols.append(ColXml(class_name=class_name))

    # Rows
    for tr in table.table_rows or []:
        row_attrs = extract_row_style(tr.table_row_style)
        row_class = collector.add_row_style(row_attrs)
        row_xml = RowXml(class_name=row_class)

        for tc in tr.table_cells or []:
            cell_attrs = extract_cell_style(tc.table_cell_style)
            cell_class = collector.add_cell_style(cell_attrs)
            cell_blocks: list[BlockNode] = []
            if tc.content:
                cell_blocks = _convert_content(tc.content, collector)
            cell_xml = CellXml(
                blocks=cell_blocks,
                class_name=cell_class,
            )
            # colspan/rowspan from TableCellStyle
            if tc.table_cell_style:
                cs = tc.table_cell_style.column_span
                rs = tc.table_cell_style.row_span
                if cs is not None and cs > 1:
                    cell_xml.colspan = cs
                if rs is not None and rs > 1:
                    cell_xml.rowspan = rs
            row_xml.cells.append(cell_xml)

        table_xml.rows.append(row_xml)

    return table_xml
