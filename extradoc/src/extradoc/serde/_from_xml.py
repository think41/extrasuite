"""Convert XML models (TabXml + StylesXml) back to a Document.

This is the deserialize direction: pydantic-xml models → Document.
The resulting Document will NOT have indices set — call reindex_document()
from reconcile._core if indices are needed.
"""

from __future__ import annotations

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
    FormattingNode,
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
    SpanNode,
    TableXml,
    TabXml,
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
    tabs: dict[str, tuple[TabXml, StylesXml]],
    document_id: str = "",
    title: str = "",
) -> Document:
    """Convert XML models to a Document."""
    doc = Document.model_validate({"documentId": document_id, "title": title})
    doc.tabs = []

    for _folder, (tab_xml, styles_xml) in tabs.items():
        tab = _convert_tab(tab_xml, styles_xml)
        doc.tabs.append(tab)

    return doc


def _convert_tab(tab_xml: TabXml, styles: StylesXml) -> Tab:
    """Convert a TabXml + StylesXml to a Tab."""
    doc_tab_d: dict[str, Any] = {}

    # Lists
    if tab_xml.lists:
        lists_d: dict[str, Any] = {}
        for list_def in tab_xml.lists:
            lists_d[list_def.id] = _convert_list_def_d(list_def, styles)
        doc_tab_d["lists"] = lists_d

    # Body
    if tab_xml.body:
        body_content = _convert_blocks(tab_xml.body, styles)
        doc_tab_d["body"] = {
            "content": [
                se.model_dump(by_alias=True, exclude_none=True) for se in body_content
            ]
        }

    # Headers
    if tab_xml.headers:
        headers_d: dict[str, Any] = {}
        for seg in tab_xml.headers:
            content = _convert_blocks(seg.blocks, styles)
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
            content = _convert_blocks(seg.blocks, styles)
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
            content = _convert_blocks(seg.blocks, styles)
            footnotes_d[seg.id] = {
                "footnoteId": seg.id,
                "content": [
                    se.model_dump(by_alias=True, exclude_none=True) for se in content
                ],
            }
        doc_tab_d["footnotes"] = footnotes_d

    return Tab.model_validate(
        {
            "tabProperties": {"tabId": tab_xml.id, "title": tab_xml.title},
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

        nl = resolve_nesting_level(
            style_attrs,
            glyph_type=level_def.glyph_type,
            glyph_format=level_def.glyph_format,
            glyph_symbol=level_def.glyph_symbol,
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
            elements.append(StructuralElement.model_validate({"sectionBreak": {}}))
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
                                {"textRun": {"content": "\n"}},
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
                                {"textRun": {"content": "\n"}},
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

    # Add trailing newline
    pe_dicts.append({"textRun": {"content": "\n"}})

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
        return [{"textRun": {"content": node.text}}]

    if isinstance(node, FormattingNode):
        sugar_attr, sugar_val = _SUGAR_TO_STYLE[node.tag]
        class_attrs: dict[str, str] = {}
        if node.class_name:
            class_attrs = dict(styles.lookup("text", node.class_name))
        class_attrs[sugar_attr] = sugar_val
        ts = resolve_text_style(class_attrs)
        ts_d = ts.model_dump(by_alias=True, exclude_none=True)
        return [
            {"textRun": {"content": child.text, "textStyle": ts_d}}
            for child in node.children
        ]

    if isinstance(node, SpanNode):
        span_attrs = styles.lookup("text", node.class_name)
        ts = resolve_text_style(span_attrs)
        ts_d = ts.model_dump(by_alias=True, exclude_none=True)
        return [
            {"textRun": {"content": child.text, "textStyle": ts_d}}
            for child in node.children
        ]

    if isinstance(node, LinkNode):
        link_attrs: dict[str, str] = {}
        if node.class_name:
            link_attrs = dict(styles.lookup("text", node.class_name))
        link_attrs["link"] = node.href
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
        return [{"person": {"personProperties": {"email": node.email}}}]

    if isinstance(node, DateNode):
        return [{"dateElement": {}}]

    if isinstance(node, RichLinkNode):
        return [{"richLink": {"richLinkProperties": {"uri": node.url}}}]

    if isinstance(node, AutoTextNode):
        return [{"autoText": {}}]

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
            col_attrs = styles.lookup("col", col.class_name) if col.class_name else {}
            cp = resolve_col_style(col_attrs)
            col_props.append(cp.model_dump(by_alias=True, exclude_none=True))
        table_d["tableStyle"] = {"tableColumnProperties": col_props or None}

    table_rows: list[dict[str, Any]] = []
    for row_xml in table_xml.rows:
        row_d: dict[str, Any] = {}
        if row_xml.class_name:
            row_attrs = styles.lookup("row", row_xml.class_name)
            rs = resolve_row_style(row_attrs)
            row_d["tableRowStyle"] = rs.model_dump(by_alias=True, exclude_none=True)

        cells: list[dict[str, Any]] = []
        for cell_xml in row_xml.cells:
            cell_d: dict[str, Any] = {}
            if cell_xml.class_name:
                cell_attrs = styles.lookup("cell", cell_xml.class_name)
                cs = resolve_cell_style(cell_attrs)
                cell_style_d = cs.model_dump(by_alias=True, exclude_none=True)
            else:
                cell_style_d = {}

            if cell_xml.colspan is not None and cell_xml.colspan > 1:
                cell_style_d["columnSpan"] = cell_xml.colspan
            if cell_xml.rowspan is not None and cell_xml.rowspan > 1:
                cell_style_d["rowSpan"] = cell_xml.rowspan

            if cell_style_d:
                cell_d["tableCellStyle"] = cell_style_d

            if cell_xml.blocks:
                content = _convert_blocks(cell_xml.blocks, styles)
                cell_d["content"] = [
                    se.model_dump(by_alias=True, exclude_none=True) for se in content
                ]
            cells.append(cell_d)

        row_d["tableCells"] = cells or None
        table_rows.append(row_d)

    table_d["tableRows"] = table_rows or None
    table_d["rows"] = len(table_rows)
    if table_rows and table_rows[0].get("tableCells"):
        table_d["columns"] = len(table_rows[0]["tableCells"])

    return Table.model_validate(table_d)
