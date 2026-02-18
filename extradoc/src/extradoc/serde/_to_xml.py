"""Convert a Document (API types) to XML models (TabXml + StylesXml).

This is the serialize direction: Document → pydantic-xml intermediate models.
"""

from __future__ import annotations

import json
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
    SoftBreakNode,
    TabFiles,
    TableXml,
    TabXml,
    TNode,
    TocXml,
)
from ._styles import (
    StyleCollector,
    determine_link_href,
    determine_sugar_tag,
    extract_cell_style,
    extract_col_style,
    extract_nesting_level,
    extract_para_style,
    extract_row_style,
    extract_text_style,
)
from ._tab_extras import (
    DocStyleXml,
    InlineObjectsXml,
    NamedRangesXml,
    NamedStylesXml,
    PositionedObjectsXml,
)
from ._utils import dim_to_str, sanitize_tab_name

if TYPE_CHECKING:
    from extradoc.api_types._generated import (
        Document,
        DocumentTab,
        Paragraph,
        ParagraphElement,
        SectionBreak,
        StructuralElement,
        Tab,
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
) -> dict[str, TabFiles]:
    """Convert a Document to XML models.

    Returns dict mapping folder_name → TabFiles for each tab.
    The folder_name is derived from the tab title.
    """
    result: dict[str, TabFiles] = {}
    _convert_tabs_recursive(doc.tabs or [], result)
    return result


def _convert_tabs_recursive(
    tabs: list[Tab],
    result: dict[str, TabFiles],
) -> None:
    """Convert tabs (and their children) to TabFiles, adding to result."""
    for tab in tabs:
        tab_props = tab.tab_properties
        tab_id = (tab_props.tab_id or "t.0") if tab_props else "t.0"
        tab_title = (tab_props.title or "Tab 1") if tab_props else "Tab 1"
        folder = sanitize_tab_name(tab_title)

        # Ensure unique folder names
        base_folder = folder
        counter = 2
        while folder in result:
            folder = f"{base_folder}_{counter}"
            counter += 1

        tab_index = tab_props.index if tab_props else None

        doc_tab = tab.document_tab
        if doc_tab:
            collector = StyleCollector()
            tab_xml = _convert_tab(tab_id, tab_title, doc_tab, collector)
            tab_xml.index = tab_index
            defaults = collector.promote_defaults()
            styles_xml = collector.build()
            _strip_default_classes(tab_xml, defaults)
            tab_files = TabFiles(tab=tab_xml, styles=styles_xml)
            tab_files.doc_style = _extract_doc_style(doc_tab)
            tab_files.named_styles = _extract_named_styles(doc_tab)
            tab_files.inline_objects = _extract_inline_objects(doc_tab)
            tab_files.positioned_objects = _extract_positioned_objects(doc_tab)
            tab_files.named_ranges = _extract_named_ranges(doc_tab)
            result[folder] = tab_files

        # Process child tabs recursively
        if tab.child_tabs:
            _convert_tabs_recursive(tab.child_tabs, result)


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
                    bullet_alignment=(
                        nl.bullet_alignment.value if nl.bullet_alignment else None
                    ),
                    start_number=nl.start_number,
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
            blocks.append(_convert_section_break(se.section_break))
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
    return _strip_trailing_empty_para(blocks)


def _strip_trailing_empty_para(blocks: list[BlockNode]) -> list[BlockNode]:
    """Strip synthetic trailing empty paragraph from a segment.

    Google Docs requires every segment to end with a paragraph. When a segment
    ends with a table, TOC, or section break, the API adds an empty trailing
    paragraph. We strip it so agents don't see this internal detail.

    Also handles the edge case where a segment contains only an empty paragraph
    (empty segment).
    """
    if not blocks:
        return blocks

    last = blocks[-1]
    # Check if last is an empty paragraph (no inlines)
    if not isinstance(last, ParagraphXml) or last.inlines:
        return blocks

    # Segment with only an empty paragraph → return empty list
    if len(blocks) == 1:
        return []

    # Empty paragraph following a non-paragraph element → strip it
    second_last = blocks[-2]
    if isinstance(second_last, TableXml | TocXml | SectionBreakXml):
        return blocks[:-1]

    return blocks


def _convert_section_break(sb: SectionBreak) -> SectionBreakXml:
    """Convert a SectionBreak to SectionBreakXml, preserving SectionStyle."""
    xml = SectionBreakXml()
    ss = sb.section_style
    if not ss:
        return xml
    if ss.section_type:
        xml.section_type = ss.section_type.value
    if ss.content_direction:
        xml.content_direction = ss.content_direction.value
    xml.default_header_id = ss.default_header_id
    xml.default_footer_id = ss.default_footer_id
    xml.first_page_header_id = ss.first_page_header_id
    xml.first_page_footer_id = ss.first_page_footer_id
    xml.even_page_header_id = ss.even_page_header_id
    xml.even_page_footer_id = ss.even_page_footer_id
    xml.use_first_page_header_footer = ss.use_first_page_header_footer
    xml.flip_page_orientation = ss.flip_page_orientation
    xml.page_number_start = ss.page_number_start
    xml.margin_top = dim_to_str(ss.margin_top)
    xml.margin_bottom = dim_to_str(ss.margin_bottom)
    xml.margin_left = dim_to_str(ss.margin_left)
    xml.margin_right = dim_to_str(ss.margin_right)
    xml.margin_header = dim_to_str(ss.margin_header)
    xml.margin_footer = dim_to_str(ss.margin_footer)
    if ss.column_properties:
        col_props = []
        for cp in ss.column_properties:
            col_props.append(cp.model_dump(by_alias=True, exclude_none=True))
        if col_props:
            xml.column_properties = json.dumps(col_props, separators=(",", ":"))
    if ss.column_separator_style:
        xml.column_separator_style = ss.column_separator_style.value
    return xml


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
            nodes = _split_soft_breaks(text, pe.text_run.text_style, collector)
            inlines.extend(nodes)
        elif pe.inline_object_element:
            obj_id = pe.inline_object_element.inline_object_id or ""
            inlines.append(ImageNode(object_id=obj_id))
        elif pe.footnote_reference:
            fn_id = pe.footnote_reference.footnote_id or ""
            inlines.append(FootnoteRefNode(id=fn_id))
        elif pe.person:
            email = ""
            name = None
            person_id = None
            if pe.person.person_properties:
                email = pe.person.person_properties.email or ""
                name = pe.person.person_properties.name
            person_id = pe.person.person_id
            inlines.append(PersonNode(email=email, name=name, person_id=person_id))
        elif pe.date_element:
            de = pe.date_element
            dep = de.date_element_properties
            inlines.append(
                DateNode(
                    date_id=de.date_id,
                    timestamp=dep.timestamp if dep else None,
                    date_format=dep.date_format.value
                    if dep and dep.date_format
                    else None,
                    time_format=dep.time_format.value
                    if dep and dep.time_format
                    else None,
                    locale=dep.locale if dep else None,
                    time_zone_id=dep.time_zone_id if dep else None,
                    display_text=dep.display_text if dep else None,
                )
            )
        elif pe.rich_link:
            url = ""
            title = None
            mime_type = None
            if pe.rich_link.rich_link_properties:
                url = pe.rich_link.rich_link_properties.uri or ""
                title = pe.rich_link.rich_link_properties.title
                mime_type = pe.rich_link.rich_link_properties.mime_type
            inlines.append(RichLinkNode(url=url, title=title, mime_type=mime_type))
        elif pe.auto_text:
            auto_type = pe.auto_text.type.value if pe.auto_text.type else None
            inlines.append(AutoTextNode(type=auto_type))
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
        return TNode(text=text)

    # Check for link first — links use LinkNode with class for non-link styles
    href, remaining_after_link, link_type = determine_link_href(all_attrs)
    if href:
        class_name = collector.add_text_style(remaining_after_link)
        return LinkNode(
            href=href,
            children=[TNode(text=text)],
            class_name=class_name,
            link_type=link_type,
        )

    # Check for sugar tag
    sugar_tag, remaining = determine_sugar_tag(all_attrs)
    if sugar_tag:
        class_name = collector.add_text_style(remaining)
        return TNode(text=text, class_name=class_name, sugar_tag=sugar_tag)

    # No sugar tag — TNode with class
    class_name = collector.add_text_style(all_attrs)
    return TNode(text=text, class_name=class_name)


def _split_soft_breaks(
    text: str,
    text_style: TextStyle | None,
    collector: StyleCollector,
) -> list[InlineNode]:
    """Split text at \\x0b (soft line break) into TNode + SoftBreakNode sequences.

    \\x0b is invalid in XML 1.0, so we represent it as a <br/> element instead.
    """
    if "\x0b" not in text:
        return [_convert_text_run(text, text_style, collector)]
    parts = text.split("\x0b")
    result: list[InlineNode] = []
    for i, part in enumerate(parts):
        if part:
            result.append(_convert_text_run(part, text_style, collector))
        if i < len(parts) - 1:
            result.append(SoftBreakNode())
    return result


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
            # colspan/rowspan from TableCellStyle (only store non-default values)
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


# ---------------------------------------------------------------------------
# Default style stripping
# ---------------------------------------------------------------------------


def _strip_default_classes(tab_xml: TabXml, defaults: dict[str, str]) -> None:
    """Walk TabXml and set class_name to None where it matches a promoted default."""
    if not defaults:
        return

    para_default = defaults.get("para")
    cell_default = defaults.get("cell")
    row_default = defaults.get("row")
    col_default = defaults.get("col")
    listlevel_default = defaults.get("listlevel")

    # List definitions
    if listlevel_default:
        for list_def in tab_xml.lists:
            for level in list_def.levels:
                if level.class_name == listlevel_default:
                    level.class_name = None

    # All block containers
    all_blocks = list(tab_xml.body)
    for seg in tab_xml.headers:
        all_blocks.extend(seg.blocks)
    for seg in tab_xml.footers:
        all_blocks.extend(seg.blocks)
    for seg in tab_xml.footnotes:
        all_blocks.extend(seg.blocks)

    _strip_blocks(all_blocks, para_default, cell_default, row_default, col_default)


def _strip_blocks(
    blocks: list[BlockNode],
    para_default: str | None,
    cell_default: str | None,
    row_default: str | None,
    col_default: str | None,
) -> None:
    """Recursively strip default class names from blocks."""
    for block in blocks:
        if isinstance(block, ParagraphXml):
            if para_default and block.class_name == para_default:
                block.class_name = None
        elif isinstance(block, TableXml):
            if col_default:
                for col in block.cols:
                    if col.class_name == col_default:
                        col.class_name = None
            for row in block.rows:
                if row_default and row.class_name == row_default:
                    row.class_name = None
                for cell in row.cells:
                    if cell_default and cell.class_name == cell_default:
                        cell.class_name = None
                    _strip_blocks(
                        cell.blocks,
                        para_default,
                        cell_default,
                        row_default,
                        col_default,
                    )
        elif isinstance(block, TocXml):
            _strip_blocks(
                block.blocks, para_default, cell_default, row_default, col_default
            )


# ---------------------------------------------------------------------------
# Tab extras extraction
# ---------------------------------------------------------------------------


def _extract_doc_style(doc_tab: DocumentTab) -> DocStyleXml | None:
    """Extract DocumentStyle from a DocumentTab as JSON."""
    if not doc_tab.document_style:
        return None
    data = doc_tab.document_style.model_dump(by_alias=True, exclude_none=True)
    return DocStyleXml(data=data) if data else None


def _extract_named_styles(doc_tab: DocumentTab) -> NamedStylesXml | None:
    """Extract NamedStyles from a DocumentTab as JSON."""
    if not doc_tab.named_styles:
        return None
    data = doc_tab.named_styles.model_dump(by_alias=True, exclude_none=True)
    return NamedStylesXml(data=data) if data else None


def _extract_inline_objects(doc_tab: DocumentTab) -> InlineObjectsXml | None:
    """Extract inlineObjects from a DocumentTab as JSON."""
    if not doc_tab.inline_objects:
        return None
    data = {
        k: v.model_dump(by_alias=True, exclude_none=True)
        for k, v in doc_tab.inline_objects.items()
    }
    return InlineObjectsXml(data=data) if data else None


def _extract_positioned_objects(doc_tab: DocumentTab) -> PositionedObjectsXml | None:
    """Extract positionedObjects from a DocumentTab as JSON."""
    if not doc_tab.positioned_objects:
        return None
    data = {
        k: v.model_dump(by_alias=True, exclude_none=True)
        for k, v in doc_tab.positioned_objects.items()
    }
    return PositionedObjectsXml(data=data) if data else None


def _extract_named_ranges(doc_tab: DocumentTab) -> NamedRangesXml | None:
    """Extract namedRanges from a DocumentTab as JSON."""
    if not doc_tab.named_ranges:
        return None
    data = {
        k: v.model_dump(by_alias=True, exclude_none=True)
        for k, v in doc_tab.named_ranges.items()
    }
    return NamedRangesXml(data=data) if data else None
