"""Convert XML models (TabXml + StylesXml) back to a Document.

This is the deserialize direction: pydantic-xml models → Document.
The resulting Document will NOT have indices set — call reindex_document()
from reconcile._core if indices are needed.
"""

from __future__ import annotations

import json
from typing import Any

from extradoc.api_types._generated import (
    Document,
    Paragraph,
    ParagraphStyleNamedStyleType,
    StructuralElement,
    Tab,
    Table,
)

from ._models import (
    AutoTextNode,
    BlockNode,
    ColumnBreakNode,
    DateNode,
    EquationNode,
    FootnoteRefNode,
    HrXml,
    ImageNode,
    InlineNode,
    LinkNode,
    ListDefXml,
    PageBreakXml,
    ParagraphXml,
    PersonNode,
    RichLinkNode,
    SectionBreakXml,
    TabFiles,
    TableXml,
    TNode,
    TocXml,
)
from ._styles import (
    StylesXml,
    resolve_cell_style,
    resolve_col_style,
    resolve_nesting_level,
    resolve_para_style,
    resolve_row_style,
    resolve_text_style,
)

# XML tag → ParagraphStyleNamedStyleType
_TAG_TO_NAMED_STYLE: dict[str, ParagraphStyleNamedStyleType] = {
    "title": ParagraphStyleNamedStyleType.TITLE,
    "subtitle": ParagraphStyleNamedStyleType.SUBTITLE,
    "h1": ParagraphStyleNamedStyleType.HEADING_1,
    "h2": ParagraphStyleNamedStyleType.HEADING_2,
    "h3": ParagraphStyleNamedStyleType.HEADING_3,
    "h4": ParagraphStyleNamedStyleType.HEADING_4,
    "h5": ParagraphStyleNamedStyleType.HEADING_5,
    "h6": ParagraphStyleNamedStyleType.HEADING_6,
}

# Sugar tag → TextStyle attribute name + value
_SUGAR_TO_STYLE: dict[str, tuple[str, str]] = {
    "b": ("bold", "true"),
    "i": ("italic", "true"),
    "u": ("underline", "true"),
    "s": ("strikethrough", "true"),
    "sup": ("superscript", "true"),
    "sub": ("subscript", "true"),
}


def tabs_to_document(
    tabs: dict[str, TabFiles],
    document_id: str = "",
    title: str = "",
    revision_id: str | None = None,
) -> Document:
    """Convert XML models to a Document."""
    doc = Document.model_validate({"documentId": document_id, "title": title})
    if revision_id:
        doc.revision_id = revision_id
    doc.tabs = []

    for _folder, tab_files in tabs.items():
        tab = _convert_tab(tab_files)
        doc.tabs.append(tab)

    return doc


def _convert_tab(tab_files: TabFiles) -> Tab:
    """Convert a TabFiles to a Tab."""
    tab_xml = tab_files.tab
    styles = tab_files.styles
    doc_tab_d: dict[str, Any] = {}

    # Lists
    if tab_xml.lists:
        lists_d: dict[str, Any] = {}
        for list_def in tab_xml.lists:
            lists_d[list_def.id] = _convert_list_def_d(list_def, styles)
        doc_tab_d["lists"] = lists_d

    # Body
    if tab_xml.body:
        body_content = _ensure_trailing_paragraph(_convert_blocks(tab_xml.body, styles))
        doc_tab_d["body"] = {
            "content": [
                se.model_dump(by_alias=True, exclude_none=True) for se in body_content
            ]
        }

    # Headers
    if tab_xml.headers:
        headers_d: dict[str, Any] = {}
        for seg in tab_xml.headers:
            content = _ensure_trailing_paragraph(_convert_blocks(seg.blocks, styles))
            headers_d[seg.id] = {
                "headerId": seg.id,
                "content": [
                    se.model_dump(by_alias=True, exclude_none=True) for se in content
                ],
            }
        doc_tab_d["headers"] = headers_d

    # Footers
    if tab_xml.footers:
        footers_d: dict[str, Any] = {}
        for seg in tab_xml.footers:
            content = _ensure_trailing_paragraph(_convert_blocks(seg.blocks, styles))
            footers_d[seg.id] = {
                "footerId": seg.id,
                "content": [
                    se.model_dump(by_alias=True, exclude_none=True) for se in content
                ],
            }
        doc_tab_d["footers"] = footers_d

    # Footnotes
    if tab_xml.footnotes:
        footnotes_d: dict[str, Any] = {}
        for seg in tab_xml.footnotes:
            content = _ensure_trailing_paragraph(_convert_blocks(seg.blocks, styles))
            footnotes_d[seg.id] = {
                "footnoteId": seg.id,
                "content": [
                    se.model_dump(by_alias=True, exclude_none=True) for se in content
                ],
            }
        doc_tab_d["footnotes"] = footnotes_d

    # Tab extras: documentStyle, namedStyles, inlineObjects, positionedObjects, namedRanges
    if tab_files.doc_style:
        doc_tab_d["documentStyle"] = tab_files.doc_style.data
    if tab_files.named_styles:
        doc_tab_d["namedStyles"] = tab_files.named_styles.data
    if tab_files.inline_objects:
        doc_tab_d["inlineObjects"] = tab_files.inline_objects.data
    if tab_files.positioned_objects:
        doc_tab_d["positionedObjects"] = tab_files.positioned_objects.data
    if tab_files.named_ranges:
        doc_tab_d["namedRanges"] = tab_files.named_ranges.data

    tab_props: dict[str, Any] = {"tabId": tab_xml.id, "title": tab_xml.title}
    if tab_xml.index is not None:
        tab_props["index"] = tab_xml.index

    return Tab.model_validate(
        {
            "tabProperties": tab_props,
            "documentTab": doc_tab_d,
        }
    )


def _convert_list_def_d(list_def: ListDefXml, styles: StylesXml) -> dict[str, Any]:
    """Convert a ListDefXml to a List dict."""
    nesting_levels: list[dict[str, Any]] = []
    for level_def in list_def.levels:
        style_attrs: dict[str, str] = {}
        if level_def.class_name:
            style_attrs = styles.lookup("listlevel", level_def.class_name)
        else:
            style_attrs = styles.lookup("listlevel", "_default")

        nl = resolve_nesting_level(
            style_attrs,
            glyph_type=level_def.glyph_type,
            glyph_format=level_def.glyph_format,
            glyph_symbol=level_def.glyph_symbol,
            bullet_alignment=level_def.bullet_alignment,
            start_number=level_def.start_number,
        )
        nesting_levels.append(nl.model_dump(by_alias=True, exclude_none=True))

    return {"listProperties": {"nestingLevels": nesting_levels or None}}


def _convert_blocks(
    blocks: list[BlockNode],
    styles: StylesXml,
) -> list[StructuralElement]:
    """Convert a list of BlockNodes to StructuralElements."""
    elements: list[StructuralElement] = []
    for block in blocks:
        if isinstance(block, SectionBreakXml):
            sb_d = _convert_section_break_d(block)
            elements.append(StructuralElement.model_validate({"sectionBreak": sb_d}))
        elif isinstance(block, ParagraphXml):
            para = _convert_paragraph(block, styles)
            elements.append(
                StructuralElement.model_validate(
                    {
                        "paragraph": para.model_dump(by_alias=True, exclude_none=True),
                    }
                )
            )
        elif isinstance(block, HrXml):
            elements.append(
                StructuralElement.model_validate(
                    {
                        "paragraph": {
                            "elements": [
                                {"horizontalRule": {}},
                                {"textRun": {"content": "\n", "textStyle": {}}},
                            ]
                        }
                    }
                )
            )
        elif isinstance(block, PageBreakXml):
            elements.append(
                StructuralElement.model_validate(
                    {
                        "paragraph": {
                            "elements": [
                                {"pageBreak": {}},
                                {"textRun": {"content": "\n", "textStyle": {}}},
                            ]
                        }
                    }
                )
            )
        elif isinstance(block, TableXml):
            table = _convert_table(block, styles)
            elements.append(
                StructuralElement.model_validate(
                    {
                        "table": table.model_dump(by_alias=True, exclude_none=True),
                    }
                )
            )
        elif isinstance(block, TocXml):
            toc_content = (
                _convert_blocks(block.blocks, styles) if block.blocks else None
            )
            toc_d: dict[str, Any] = {}
            if toc_content:
                toc_d["content"] = [
                    se.model_dump(by_alias=True, exclude_none=True)
                    for se in toc_content
                ]
            elements.append(
                StructuralElement.model_validate({"tableOfContents": toc_d})
            )
    return elements


def _ensure_trailing_paragraph(
    elements: list[StructuralElement],
) -> list[StructuralElement]:
    """Ensure a segment ends with a paragraph (Google Docs requirement).

    If the segment is empty or ends with a non-paragraph element (table, TOC,
    section break), append a synthetic empty paragraph.
    """
    if not elements or not elements[-1].paragraph:
        elements.append(
            StructuralElement.model_validate(
                {
                    "paragraph": {
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                        "elements": [{"textRun": {"content": "\n", "textStyle": {}}}],
                    }
                }
            )
        )
    return elements


def _convert_paragraph(
    para_xml: ParagraphXml,
    styles: StylesXml,
) -> Paragraph:
    """Convert a ParagraphXml to a Paragraph."""
    named_style = _TAG_TO_NAMED_STYLE.get(para_xml.tag)
    if named_style is None and para_xml.tag == "p":
        named_style = ParagraphStyleNamedStyleType.NORMAL_TEXT

    para_attrs: dict[str, str] = {}
    if para_xml.class_name:
        para_attrs = styles.lookup("para", para_xml.class_name)
    else:
        para_attrs = styles.lookup("para", "_default")

    ps = resolve_para_style(para_attrs, named_style)

    if para_xml.heading_id:
        ps.heading_id = para_xml.heading_id

    # Bullet for <li>
    bullet_d: dict[str, Any] | None = None
    if para_xml.tag == "li" and para_xml.parent is not None:
        bullet_d = {"listId": para_xml.parent, "nestingLevel": para_xml.level}

    # Convert inline elements
    pe_dicts: list[dict[str, Any]] = []
    for inline in para_xml.inlines:
        pe_dicts.extend(_convert_inline(inline, styles))

    # Add trailing newline — append to last textRun if possible,
    # otherwise add a standalone \n element (matches API behavior)
    if pe_dicts and "textRun" in pe_dicts[-1]:
        pe_dicts[-1]["textRun"]["content"] += "\n"
    else:
        pe_dicts.append({"textRun": {"content": "\n", "textStyle": {}}})

    para_d: dict[str, Any] = {
        "paragraphStyle": ps.model_dump(by_alias=True, exclude_none=True),
        "elements": pe_dicts,
    }
    if bullet_d:
        para_d["bullet"] = bullet_d

    return Paragraph.model_validate(para_d)


def _convert_inline(
    node: InlineNode,
    styles: StylesXml,
) -> list[dict[str, Any]]:
    """Convert an inline node to ParagraphElement dicts."""
    if isinstance(node, TNode):
        attrs: dict[str, str] = {}
        if node.class_name:
            attrs = dict(styles.lookup("text", node.class_name))
        if node.sugar_tag and node.sugar_tag in _SUGAR_TO_STYLE:
            attr_name, attr_val = _SUGAR_TO_STYLE[node.sugar_tag]
            attrs[attr_name] = attr_val
        if attrs:
            ts = resolve_text_style(attrs)
            ts_d = ts.model_dump(by_alias=True, exclude_none=True)
            return [{"textRun": {"content": node.text, "textStyle": ts_d}}]
        return [{"textRun": {"content": node.text, "textStyle": {}}}]

    if isinstance(node, LinkNode):
        link_attrs: dict[str, str] = {}
        if node.class_name:
            link_attrs = dict(styles.lookup("text", node.class_name))
        # Use the correct link attribute key for round-trip fidelity
        link_key = node.link_type or "link"
        link_attrs[link_key] = node.href
        ts = resolve_text_style(link_attrs)
        ts_d = ts.model_dump(by_alias=True, exclude_none=True)
        return [
            {"textRun": {"content": child.text, "textStyle": ts_d}}
            for child in node.children
        ]

    if isinstance(node, ImageNode):
        return [{"inlineObjectElement": {"inlineObjectId": node.object_id}}]

    if isinstance(node, FootnoteRefNode):
        return [{"footnoteReference": {"footnoteId": node.id}}]

    if isinstance(node, PersonNode):
        pp: dict[str, Any] = {"email": node.email}
        if node.name:
            pp["name"] = node.name
        person_d: dict[str, Any] = {"personProperties": pp}
        if node.person_id:
            person_d["personId"] = node.person_id
        return [{"person": person_d}]

    if isinstance(node, DateNode):
        de_d: dict[str, Any] = {}
        if node.date_id:
            de_d["dateId"] = node.date_id
        dep: dict[str, Any] = {}
        if node.timestamp:
            dep["timestamp"] = node.timestamp
        if node.date_format:
            dep["dateFormat"] = node.date_format
        if node.time_format:
            dep["timeFormat"] = node.time_format
        if node.locale:
            dep["locale"] = node.locale
        if node.time_zone_id:
            dep["timeZoneId"] = node.time_zone_id
        if node.display_text:
            dep["displayText"] = node.display_text
        if dep:
            de_d["dateElementProperties"] = dep
        return [{"dateElement": de_d}]

    if isinstance(node, RichLinkNode):
        rlp: dict[str, Any] = {"uri": node.url}
        if node.title:
            rlp["title"] = node.title
        if node.mime_type:
            rlp["mimeType"] = node.mime_type
        return [{"richLink": {"richLinkProperties": rlp}}]

    if isinstance(node, AutoTextNode):
        at_d: dict[str, Any] = {}
        if node.type:
            at_d["type"] = node.type
        return [{"autoText": at_d}]

    if isinstance(node, EquationNode):
        return [{"equation": {}}]

    if isinstance(node, ColumnBreakNode):
        return [{"columnBreak": {}}]

    return []


def _convert_table(
    table_xml: TableXml,
    styles: StylesXml,
) -> Table:
    """Convert a TableXml to a Table."""
    table_d: dict[str, Any] = {}

    if table_xml.cols:
        col_props = []
        for col in table_xml.cols:
            if col.class_name:
                col_attrs = styles.lookup("col", col.class_name)
            else:
                col_attrs = styles.lookup("col", "_default")
            cp = resolve_col_style(col_attrs)
            col_props.append(cp.model_dump(by_alias=True, exclude_none=True))
        table_d["tableStyle"] = {"tableColumnProperties": col_props or None}

    table_rows: list[dict[str, Any]] = []
    for row_xml in table_xml.rows:
        row_d: dict[str, Any] = {}
        if row_xml.class_name:
            row_attrs = styles.lookup("row", row_xml.class_name)
        else:
            row_attrs = styles.lookup("row", "_default")
        rs = resolve_row_style(row_attrs)
        row_style_d = rs.model_dump(by_alias=True, exclude_none=True)
        # API default: minRowHeight with just unit, no magnitude
        row_style_d.setdefault("minRowHeight", {"unit": "PT"})
        row_d["tableRowStyle"] = row_style_d

        cells: list[dict[str, Any]] = []
        for cell_xml in row_xml.cells:
            cell_d: dict[str, Any] = {}
            if cell_xml.class_name:
                cell_attrs = styles.lookup("cell", cell_xml.class_name)
            else:
                cell_attrs = styles.lookup("cell", "_default")
            cs = resolve_cell_style(cell_attrs)
            cell_style_d = cs.model_dump(by_alias=True, exclude_none=True)
            # API defaults: empty backgroundColor, columnSpan=1, rowSpan=1
            cell_style_d.setdefault("backgroundColor", {})
            if cell_xml.colspan is not None and cell_xml.colspan > 1:
                cell_style_d["columnSpan"] = cell_xml.colspan
            else:
                cell_style_d.setdefault("columnSpan", 1)
            if cell_xml.rowspan is not None and cell_xml.rowspan > 1:
                cell_style_d["rowSpan"] = cell_xml.rowspan
            else:
                cell_style_d.setdefault("rowSpan", 1)
            cell_d["tableCellStyle"] = cell_style_d

            if cell_xml.blocks:
                content = _ensure_trailing_paragraph(
                    _convert_blocks(cell_xml.blocks, styles)
                )
                cell_d["content"] = [
                    se.model_dump(by_alias=True, exclude_none=True) for se in content
                ]
            else:
                # Empty cell still needs a trailing paragraph
                empty_para = StructuralElement.model_validate(
                    {
                        "paragraph": {
                            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                            "elements": [
                                {"textRun": {"content": "\n", "textStyle": {}}}
                            ],
                        }
                    }
                )
                cell_d["content"] = [
                    empty_para.model_dump(by_alias=True, exclude_none=True)
                ]
            cells.append(cell_d)

        row_d["tableCells"] = cells or None
        table_rows.append(row_d)

    table_d["tableRows"] = table_rows or None
    table_d["rows"] = len(table_rows)
    if table_rows and table_rows[0].get("tableCells"):
        table_d["columns"] = len(table_rows[0]["tableCells"])

    return Table.model_validate(table_d)


def _convert_section_break_d(sb: SectionBreakXml) -> dict[str, Any]:
    """Convert a SectionBreakXml to a sectionBreak dict."""
    ss_d: dict[str, Any] = {}
    if sb.section_type:
        ss_d["sectionType"] = sb.section_type
    if sb.content_direction:
        ss_d["contentDirection"] = sb.content_direction
    if sb.default_header_id:
        ss_d["defaultHeaderId"] = sb.default_header_id
    if sb.default_footer_id:
        ss_d["defaultFooterId"] = sb.default_footer_id
    if sb.first_page_header_id:
        ss_d["firstPageHeaderId"] = sb.first_page_header_id
    if sb.first_page_footer_id:
        ss_d["firstPageFooterId"] = sb.first_page_footer_id
    if sb.even_page_header_id:
        ss_d["evenPageHeaderId"] = sb.even_page_header_id
    if sb.even_page_footer_id:
        ss_d["evenPageFooterId"] = sb.even_page_footer_id
    if sb.use_first_page_header_footer is not None:
        ss_d["useFirstPageHeaderFooter"] = sb.use_first_page_header_footer
    if sb.flip_page_orientation is not None:
        ss_d["flipPageOrientation"] = sb.flip_page_orientation
    if sb.page_number_start is not None:
        ss_d["pageNumberStart"] = sb.page_number_start
    for xml_key, api_key in [
        ("margin_top", "marginTop"),
        ("margin_bottom", "marginBottom"),
        ("margin_left", "marginLeft"),
        ("margin_right", "marginRight"),
        ("margin_header", "marginHeader"),
        ("margin_footer", "marginFooter"),
    ]:
        val = getattr(sb, xml_key)
        if val:
            num = val.rstrip("pt")
            ss_d[api_key] = {"magnitude": float(num), "unit": "PT"}
    if sb.column_properties:
        ss_d["columnProperties"] = json.loads(sb.column_properties)
    if sb.column_separator_style:
        ss_d["columnSeparatorStyle"] = sb.column_separator_style
    if ss_d:
        return {"sectionStyle": ss_d}
    return {}
