"""Convert Google Docs JSON to ExtraDoc XML format.

Implements the conversion from Google Docs API response to the XML format
specified in extradoc-spec.md, with:
- Sugar elements (h1-h6, title, subtitle, li)
- Style classes from factorization
- Multi-element style wrappers
"""

from __future__ import annotations

import hashlib
import html
from dataclasses import dataclass, field
from typing import Any

from .style_factorizer import (
    FactorizedStyles,
    extract_cell_style,
    extract_text_style,
    factorize_styles,
)

# Base62 characters for content-based ID generation
_BASE62_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _int_to_base62(num: int, min_length: int = 3) -> str:
    """Convert integer to base62 string with minimum length."""
    if num == 0:
        return "0" * min_length
    base = len(_BASE62_CHARS)
    result = []
    while num > 0:
        result.append(_BASE62_CHARS[num % base])
        num //= base
    while len(result) < min_length:
        result.append("0")
    return "".join(reversed(result))


def content_hash_id(content: str) -> str:
    """Generate a short content-based ID using hash.

    Uses SHA256 hash of content, then encodes first 5 bytes as base62
    to create a 4+ character stable ID. IDs are stable across pulls
    if content is unchanged.
    """
    h = hashlib.sha256(content.encode()).digest()
    num = int.from_bytes(h[:5], "big")
    return _int_to_base62(num, min_length=4)


@dataclass
class ConversionContext:
    """Tracks state during conversion."""

    styles: FactorizedStyles
    inline_objects: dict[str, dict[str, Any]] = field(default_factory=dict)
    footnotes: dict[str, dict[str, Any]] = field(default_factory=dict)
    lists: dict[str, Any] = field(default_factory=dict)


def convert_document_to_xml(
    document: dict[str, Any],
) -> tuple[str, str]:
    """Convert a Google Docs document to ExtraDoc XML format.

    Args:
        document: Raw document JSON from Google Docs API

    Returns:
        Tuple of (document_xml, styles_xml)
    """
    # Factorize styles first
    styles = factorize_styles(document)

    ctx = ConversionContext(styles=styles)
    ctx.inline_objects = document.get("inlineObjects", {})

    # Get document metadata
    doc_id = document.get("documentId", "")
    title = document.get("title", "Untitled")
    revision_id = document.get("revisionId", "")

    # Build document XML
    parts: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<doc id="{_escape(doc_id)}" revision="{_escape(revision_id)}">',
        "  <meta>",
        f"    <title>{_escape(title)}</title>",
        "  </meta>",
    ]

    # Check for tabs (modern API) vs legacy body
    tabs = document.get("tabs", [])

    if tabs:
        for tab in tabs:
            tab_xml = _convert_tab(tab, document, ctx)
            parts.append(tab_xml)
    else:
        # Legacy single-tab document
        body = document.get("body", {})
        content = body.get("content", [])
        lists = document.get("lists", {})
        headers = document.get("headers", {})
        footers = document.get("footers", {})
        footnotes = document.get("footnotes", {})

        # Set context for footnote inlining
        ctx.footnotes = footnotes
        ctx.lists = lists

        # Convert body (footnotes are inlined where references appear)
        parts.append('  <body class="_base">')
        body_xml = _convert_body_content(content, lists, ctx, indent=4)
        parts.append(body_xml)
        parts.append("  </body>")

        # Convert headers
        for header_id, header in headers.items():
            header_xml = _convert_header_or_footer(
                header, header_id, "header", lists, ctx
            )
            parts.append(header_xml)

        # Convert footers
        for footer_id, footer in footers.items():
            footer_xml = _convert_header_or_footer(
                footer, footer_id, "footer", lists, ctx
            )
            parts.append(footer_xml)

        # Note: Footnotes are NOT converted separately - they are inlined
        # in the body where the footnote reference appears

    parts.append("</doc>")

    document_xml = "\n".join(parts)
    styles_xml = styles.to_xml()

    return document_xml, styles_xml


def _escape(text: str) -> str:
    """Escape text for XML, handling special Google Docs characters.

    XML 1.0 only allows: #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]

    Google Docs uses special control characters:
    - U+000B (vertical tab) = column break - replace with <columnbreak/> element
    - Other invalid chars are stripped
    """
    result = []
    for c in text:
        if c == "\x0b":
            # Column break - use a self-closing element that will be 1 char for index
            result.append("<columnbreak/>")
        elif c in ("\t", "\n", "\r") or (ord(c) >= 0x20 and ord(c) != 0x7F):
            result.append(html.escape(c, quote=True))
        # Other control chars are stripped (shouldn't happen in practice)
    return "".join(result)


def _convert_tab(
    tab: dict[str, Any],
    document: dict[str, Any],
    ctx: ConversionContext,
) -> str:
    """Convert a tab to XML."""
    tab_props = tab.get("tabProperties", {})
    tab_id = tab_props.get("tabId", "")
    tab_title = tab_props.get("title", "")

    doc_tab = tab.get("documentTab", {})
    body = doc_tab.get("body", {})
    content = body.get("content", [])
    lists = doc_tab.get("lists", {}) or document.get("lists", {})
    headers = doc_tab.get("headers", {})
    footers = doc_tab.get("footers", {})
    footnotes = doc_tab.get("footnotes", {})

    # Set context for footnote inlining
    ctx.footnotes = footnotes
    ctx.lists = lists

    parts: list[str] = []

    # Tab element with attributes
    attrs = [f'id="{_escape(tab_id)}"']
    if tab_title:
        attrs.append(f'title="{_escape(tab_title)}"')
    attrs.append('class="_base"')
    parts.append(f"  <tab {' '.join(attrs)}>")

    # Body content (footnotes are inlined where references appear)
    parts.append("    <body>")
    body_xml = _convert_body_content(content, lists, ctx, indent=6)
    parts.append(body_xml)
    parts.append("    </body>")

    parts.append("  </tab>")

    # Headers
    for header_id, header in headers.items():
        header_xml = _convert_header_or_footer(header, header_id, "header", lists, ctx)
        parts.append(header_xml)

    # Footers
    for footer_id, footer in footers.items():
        footer_xml = _convert_header_or_footer(footer, footer_id, "footer", lists, ctx)
        parts.append(footer_xml)

    # Note: Footnotes are NOT converted separately - they are inlined
    # in the body where the footnote reference appears

    return "\n".join(parts)


def _convert_header_or_footer(
    section: dict[str, Any],
    section_id: str,
    tag_name: str,
    lists: dict[str, Any],
    ctx: ConversionContext,
) -> str:
    """Convert a header or footer to XML."""
    content = section.get("content", [])
    inner_xml = _convert_body_content(content, lists, ctx, indent=4)
    return f'  <{tag_name} id="{_escape(section_id)}" class="_base">\n{inner_xml}\n  </{tag_name}>'


def _convert_body_content(
    content: list[dict[str, Any]],
    lists: dict[str, Any],
    ctx: ConversionContext,
    indent: int = 0,
) -> str:
    """Convert body content to XML."""
    parts: list[str] = []
    prefix = " " * indent

    for element in content:
        if "sectionBreak" in element:
            continue

        elif "paragraph" in element:
            para = element["paragraph"]
            bullet = para.get("bullet")

            if bullet:
                # List item
                li_xml = _convert_list_item(para, bullet, lists, ctx)
                parts.append(prefix + li_xml)
            else:
                # Regular paragraph
                para_xml = _convert_paragraph(para, ctx)
                parts.append(prefix + para_xml)

        elif "table" in element:
            table_start_index = element.get("startIndex", 0)
            table_xml = _convert_table(element["table"], lists, ctx, table_start_index)
            for line in table_xml.split("\n"):
                parts.append(prefix + line)

        elif "tableOfContents" in element:
            toc = element["tableOfContents"]
            toc_content = toc.get("content", [])
            inner = _convert_body_content(toc_content, lists, ctx, indent=0)
            parts.append(prefix + "<toc>")
            for line in inner.split("\n"):
                if line:
                    parts.append(prefix + "  " + line)
            parts.append(prefix + "</toc>")

    return "\n".join(parts)


def _convert_paragraph(para: dict[str, Any], ctx: ConversionContext) -> str:
    """Convert a paragraph to XML."""
    style = para.get("paragraphStyle", {})
    named_style = style.get("namedStyleType", "NORMAL_TEXT")

    # If the paragraph is visually just a horizontal rule (no text/elements, only a
    # bottom border), emit <hr/> directly.
    border = style.get("borderBottom", {})
    if (
        not para.get("elements")
        and border
        and (border.get("width", {}).get("magnitude", 0) or border.get("color"))
    ):
        return "<p><hr/></p>"

    # Convert paragraph elements to inline content
    content = _convert_paragraph_elements(para.get("elements", []), ctx)

    # Determine tag based on named style
    if named_style == "TITLE":
        tag = "title"
    elif named_style == "SUBTITLE":
        tag = "subtitle"
    elif named_style == "HEADING_1":
        tag = "h1"
    elif named_style == "HEADING_2":
        tag = "h2"
    elif named_style == "HEADING_3":
        tag = "h3"
    elif named_style == "HEADING_4":
        tag = "h4"
    elif named_style == "HEADING_5":
        tag = "h5"
    elif named_style == "HEADING_6":
        tag = "h6"
    else:
        tag = "p"

    # Check if paragraph has custom styling (beyond what named style provides)
    # For now, we'll add class attribute if paragraph has specific styling
    # This is simplified - full implementation would check paragraph style properties
    class_attr = ""

    # Preserve whitespace content for accurate index calculation
    # Even spaces matter for Google Docs UTF-16 indexes
    if not content:
        return f"<{tag}{class_attr}></{tag}>"

    return f"<{tag}{class_attr}>{content}</{tag}>"


def _convert_list_item(
    para: dict[str, Any],
    bullet: dict[str, Any],
    lists: dict[str, Any],
    ctx: ConversionContext,
) -> str:
    """Convert a bulleted/numbered paragraph to a list item."""
    list_id = bullet.get("listId", "")
    nesting = bullet.get("nestingLevel", 0)

    # Determine list type from list definition
    list_type = "bullet"
    if list_id and list_id in lists:
        list_props = lists[list_id].get("listProperties", {})
        nesting_levels = list_props.get("nestingLevels", [])
        if nesting < len(nesting_levels):
            level_props = nesting_levels[nesting]
            glyph_type = level_props.get("glyphType", "")
            glyph_symbol = level_props.get("glyphSymbol", "")

            if glyph_type == "DECIMAL":
                list_type = "decimal"
            elif glyph_type in ("ALPHA", "UPPER_ALPHA"):
                list_type = "alpha"
            elif glyph_type in ("ROMAN", "UPPER_ROMAN"):
                list_type = "roman"
            elif glyph_symbol in ("\u2610", "\u2611", "\u2612"):
                list_type = "checkbox"

    # Convert content
    content = _convert_paragraph_elements(para.get("elements", []), ctx)

    return f'<li type="{list_type}" level="{nesting}">{content}</li>'


def _convert_paragraph_elements(
    elements: list[dict[str, Any]], ctx: ConversionContext
) -> str:
    """Convert paragraph elements to inline XML content."""
    parts: list[str] = []

    for elem in elements:
        if "textRun" in elem:
            text_xml = _convert_text_run(elem["textRun"], ctx)
            parts.append(text_xml)

        elif "horizontalRule" in elem:
            parts.append("<hr/>")

        elif "pageBreak" in elem:
            parts.append("<pagebreak/>")

        elif "columnBreak" in elem:
            parts.append("<columnbreak/>")

        elif "footnoteReference" in elem:
            ref = elem["footnoteReference"]
            fn_id = ref.get("footnoteId", "")
            # Inline the footnote content at the reference location
            if fn_id and fn_id in ctx.footnotes:
                footnote = ctx.footnotes[fn_id]
                fn_content = footnote.get("content", [])
                # Convert footnote content (using ctx.lists for list formatting)
                inner_xml = _convert_body_content(fn_content, ctx.lists, ctx, indent=0)
                # Wrap in footnote tag - content is inline, no extra newlines
                inner_xml = inner_xml.strip()
                parts.append(f'<footnote id="{_escape(fn_id)}">{inner_xml}</footnote>')
            else:
                # Fallback: footnote not found, emit empty tag
                parts.append(f'<footnote id="{_escape(fn_id)}"></footnote>')

        elif "inlineObjectElement" in elem:
            obj_elem = elem["inlineObjectElement"]
            obj_id = obj_elem.get("inlineObjectId", "")
            if obj_id in ctx.inline_objects:
                obj = ctx.inline_objects[obj_id]
                img_xml = _convert_inline_object(obj, obj_id)
                parts.append(img_xml)
            else:
                parts.append(f'<image data-id="{_escape(obj_id)}"/>')

        elif "person" in elem:
            person = elem["person"]
            props = person.get("personProperties", {})
            email = props.get("email", "")
            name = props.get("name", email)
            parts.append(f'<person email="{_escape(email)}" name="{_escape(name)}"/>')

        elif "richLink" in elem:
            rich_link = elem["richLink"]
            props = rich_link.get("richLinkProperties", {})
            url = props.get("uri", "")
            link_title = props.get("title", url)
            # Rich links are treated as regular links in the XML format
            parts.append(f'<a href="{_escape(url)}">{_escape(link_title)}</a>')

        elif "dateElement" in elem:
            parts.append("<date/>")

        elif "equation" in elem:
            parts.append("<equation/>")

        elif "autoText" in elem:
            auto = elem["autoText"]
            auto_type = auto.get("type", "")
            parts.append(f'<autotext type="{_escape(auto_type)}"/>')

    return "".join(parts)


def _convert_text_run(text_run: dict[str, Any], ctx: ConversionContext) -> str:
    """Convert a text run to XML with inline formatting."""
    content: str = text_run.get("content", "")
    style = text_run.get("textStyle", {})

    # Strip trailing newline
    if content.endswith("\n"):
        content = content[:-1]

    if not content:
        return ""

    # Escape content
    result = _escape(content)

    # Check for link
    link = style.get("link")
    if link:
        url = link.get("url", "")
        heading_id = link.get("headingId")
        bookmark_id = link.get("bookmarkId")

        if url:
            href = url
        elif heading_id:
            href = f"#{heading_id}"
        elif bookmark_id:
            href = f"#{bookmark_id}"
        else:
            href = ""

        if href:
            result = f'<a href="{_escape(href)}">{result}</a>'

    # Apply formatting (nested from innermost to outermost)
    if style.get("strikethrough"):
        result = f"<s>{result}</s>"
    if style.get("underline") and not link:  # Links already underlined
        result = f"<u>{result}</u>"
    if style.get("italic"):
        result = f"<i>{result}</i>"
    if style.get("bold"):
        result = f"<b>{result}</b>"
    if style.get("baselineOffset") == "SUPERSCRIPT":
        result = f"<sup>{result}</sup>"
    if style.get("baselineOffset") == "SUBSCRIPT":
        result = f"<sub>{result}</sub>"

    # Check for style class (font, color, etc.)
    text_styles = extract_text_style(style)
    if text_styles:
        style_id = ctx.styles.get_style_id(text_styles)
        if style_id != "_base":
            result = f'<span class="{style_id}">{result}</span>'

    return result


def _convert_inline_object(obj: dict[str, Any], obj_id: str) -> str:
    """Convert an inline object (usually an image) to XML."""
    props = obj.get("inlineObjectProperties", {})
    embedded = props.get("embeddedObject", {})

    image_props = embedded.get("imageProperties", {})
    if image_props:
        content_uri = image_props.get("contentUri", "")
        source_uri = image_props.get("sourceUri", "")
        url = content_uri or source_uri

        size = embedded.get("size", {})
        width = size.get("width", {}).get("magnitude", "")
        height = size.get("height", {}).get("magnitude", "")

        attrs = [f'src="{_escape(url)}"']
        if width:
            attrs.append(f'width="{width}pt"')
        if height:
            attrs.append(f'height="{height}pt"')

        title = embedded.get("title", "")
        desc = embedded.get("description", "")
        if title:
            attrs.append(f'title="{_escape(title)}"')
        if desc:
            attrs.append(f'alt="{_escape(desc)}"')

        return f"<image {' '.join(attrs)}/>"

    return f'<image data-id="{_escape(obj_id)}"/>'


def _convert_table(
    table: dict[str, Any],
    lists: dict[str, Any],
    ctx: ConversionContext,
    table_start_index: int = 0,  # noqa: ARG001 - kept for API compatibility
) -> str:
    """Convert a table to XML with content-based IDs.

    IDs are computed from content hash:
    - Cell ID: hash of cell content
    - Row ID: hash of row content (all cells)
    - Table ID: hash of table content (all rows)

    This ensures stable IDs across pulls if content is unchanged.
    Table dimensions (rows/cols) and indexes are NOT stored in XML -
    they can be derived from structure at diff time.
    """
    rows = table.get("tableRows", [])

    # Extract column width properties
    table_style = table.get("tableStyle", {})
    col_props = table_style.get("tableColumnProperties", [])
    col_elements: list[str] = []

    for i, col_prop in enumerate(col_props):
        width_type = col_prop.get("widthType", "EVENLY_DISTRIBUTED")
        if width_type == "FIXED_WIDTH":
            width = col_prop.get("width", {})
            magnitude = width.get("magnitude", 0)
            unit = width.get("unit", "PT")
            # Convert unit to lowercase for XML
            unit_str = "pt" if unit == "PT" else unit.lower()
            col_id = content_hash_id(f"col:{i}:{magnitude}{unit_str}")
            col_elements.append(
                f'  <col id="{col_id}" index="{i}" width="{magnitude}{unit_str}"/>'
            )

    # Build rows with content-based IDs (bottom-up: cells first, then rows)
    row_parts: list[str] = []

    for row in rows:
        cell_parts: list[str] = []
        cells = row.get("tableCells", [])

        for cell in cells:
            cell_style = cell.get("tableCellStyle", {})
            colspan = cell_style.get("columnSpan", 1)
            rowspan = cell_style.get("rowSpan", 1)

            # Convert cell content first (without ID)
            cell_content = cell.get("content", [])
            cell_xml = _convert_body_content(cell_content, lists, ctx, indent=0)

            # Compute cell ID from content
            cell_id = content_hash_id(cell_xml)

            # Extract cell style and get style class
            cell_style_props = extract_cell_style(cell_style)
            cell_style_id = ctx.styles.get_cell_style_id(cell_style_props)

            # Build cell attributes
            attrs = [f'id="{cell_id}"']
            if cell_style_id:
                attrs.append(f'class="{cell_style_id}"')
            if colspan > 1:
                attrs.append(f'colspan="{colspan}"')
            if rowspan > 1:
                attrs.append(f'rowspan="{rowspan}"')
            attr_str = " ".join(attrs)

            if "\n" in cell_xml:
                # Multi-line cell content
                cell_lines = [f"    <td {attr_str}>"]
                for line in cell_xml.split("\n"):
                    if line:
                        cell_lines.append(f"      {line}")
                cell_lines.append("    </td>")
                cell_parts.append("\n".join(cell_lines))
            else:
                cell_parts.append(f"    <td {attr_str}>{cell_xml}</td>")

        # Compute row ID from all cells content
        row_content = "\n".join(cell_parts)
        row_id = content_hash_id(row_content)
        row_parts.append(f'  <tr id="{row_id}">')
        row_parts.extend(cell_parts)
        row_parts.append("  </tr>")

    # Compute table ID from all rows content (include col elements for stability)
    table_content = "\n".join(col_elements + row_parts)
    table_id = content_hash_id(table_content)

    # Only include the content-based ID - no rows/cols/startIndex
    parts: list[str] = [f'<table id="{table_id}">']
    # Add column width elements if any columns have fixed widths
    parts.extend(col_elements)
    parts.extend(row_parts)
    parts.append("</table>")

    return "\n".join(parts)
