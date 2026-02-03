"""Convert Google Docs JSON to HTML format.

This module converts Google Docs API responses to a clean HTML representation
that allows:
1. LLM-friendly editing (semantic HTML with custom elements)
2. Index reconstruction without explicit index attributes
3. Diff generation for batchUpdate requests

Key Design Principles:
1. Paragraphs map to HTML elements based on their style (h1-h6, p, li)
2. Text runs with different styles map to inline elements (strong, em, a)
3. Google Docs-specific elements use custom self-closing tags (PageBreak, Person, etc.)
4. Indexes are implicitly derivable by walking the HTML in document order
5. Metadata embedded in <script> tag in <head>
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from typing import Any

from .indexer import utf16_len


@dataclass
class ConversionContext:
    """Tracks state during conversion."""

    # List tracking: list_id -> current nesting level
    active_lists: dict[str, int] = field(default_factory=dict)

    # Inline objects referenced in the document
    inline_objects: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Styles extracted for the styles.json
    styles: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Current list context for nested lists
    list_stack: list[str] = field(default_factory=list)

    # Current tab ID (for multi-tab documents)
    current_tab_id: str | None = None


def convert_document_to_html(document: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Convert a Google Docs document to HTML.

    Args:
        document: Raw document JSON from Google Docs API

    Returns:
        Tuple of (html_string, styles_dict)
        - html_string: The HTML representation
        - styles_dict: Extracted styling information for styles.json
    """
    ctx = ConversionContext()

    # Extract inline objects for reference
    ctx.inline_objects = document.get("inlineObjects", {})

    # Get document metadata
    doc_id = document.get("documentId", "")
    title = document.get("title", "Untitled")
    revision_id = document.get("revisionId", "")

    # Build metadata JSON
    metadata = {
        "documentId": doc_id,
        "title": title,
        "revisionId": revision_id,
    }

    html_parts = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        '  <meta charset="utf-8">',
        f"  <title>{html.escape(title)}</title>",
        '  <script type="application/json" id="doc-metadata">',
        f"  {json.dumps(metadata, indent=2)}",
        "  </script>",
        "</head>",
        "<body>",
    ]

    # Check for tabs (modern API) vs legacy body
    tabs = document.get("tabs", [])

    if tabs:
        # Convert each tab to <article>
        for tab in tabs:
            tab_content = convert_tab(tab, document, ctx)
            html_parts.append(tab_content)
    else:
        # Legacy single-tab document (body at root level)
        body = document.get("body", {})
        content = body.get("content", [])
        lists = document.get("lists", {})
        headers = document.get("headers", {})
        footers = document.get("footers", {})
        footnotes = document.get("footnotes", {})

        # Legacy docs don't have tab IDs
        html_parts.append("<article>")

        # Convert headers
        for header_id, header in headers.items():
            header_html = convert_header_or_footer(
                header, header_id, "Header", lists, ctx
            )
            html_parts.append(header_html)

        # Convert body
        html_parts.append("<main>")
        body_html = convert_body_content(content, lists, ctx)
        html_parts.append(body_html)
        html_parts.append("</main>")

        # Convert footers
        for footer_id, footer in footers.items():
            footer_html = convert_header_or_footer(
                footer, footer_id, "Footer", lists, ctx
            )
            html_parts.append(footer_html)

        # Convert footnotes
        for fn_id, footnote in footnotes.items():
            fn_html = convert_footnote(footnote, fn_id, lists, ctx)
            html_parts.append(fn_html)

        html_parts.append("</article>")

    html_parts.extend(
        [
            "</body>",
            "</html>",
        ]
    )

    return "\n".join(html_parts), ctx.styles


def convert_tab(
    tab: dict[str, Any],
    document: dict[str, Any],
    ctx: ConversionContext,
) -> str:
    """Convert a tab to HTML.

    Args:
        tab: Tab object from the API
        document: Full document for looking up lists, etc.
        ctx: Conversion context

    Returns:
        HTML string for the tab (as <article> element)
    """
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

    ctx.current_tab_id = tab_id

    parts: list[str] = []

    # Always use <article> with id and data-title attributes
    attrs = [f'id="{html.escape(tab_id)}"']
    if tab_title:
        attrs.append(f'data-title="{html.escape(tab_title)}"')
    parts.append(f"<article {' '.join(attrs)}>")

    # Convert headers
    for header_id, header in headers.items():
        header_html = convert_header_or_footer(header, header_id, "Header", lists, ctx)
        parts.append(header_html)

    # Convert body
    parts.append("<main>")
    body_html = convert_body_content(content, lists, ctx)
    parts.append(body_html)
    parts.append("</main>")

    # Convert footers
    for footer_id, footer in footers.items():
        footer_html = convert_header_or_footer(footer, footer_id, "Footer", lists, ctx)
        parts.append(footer_html)

    # Convert footnotes
    for fn_id, footnote in footnotes.items():
        fn_html = convert_footnote(footnote, fn_id, lists, ctx)
        parts.append(fn_html)

    parts.append("</article>")

    return "\n".join(parts)


def convert_header_or_footer(
    section: dict[str, Any],
    section_id: str,
    tag_name: str,
    lists: dict[str, Any],
    ctx: ConversionContext,
) -> str:
    """Convert a header or footer to HTML.

    Args:
        section: Header or footer object
        section_id: The section ID (e.g., "kix.abc123")
        tag_name: "Header" or "Footer"
        lists: List definitions
        ctx: Conversion context

    Returns:
        HTML string for the section
    """
    content = section.get("content", [])
    inner_html = convert_body_content(content, lists, ctx)
    return f'<{tag_name} id="{html.escape(section_id)}">\n{inner_html}\n</{tag_name}>'


def convert_footnote(
    footnote: dict[str, Any],
    footnote_id: str,
    lists: dict[str, Any],
    ctx: ConversionContext,
) -> str:
    """Convert a footnote to HTML.

    Args:
        footnote: Footnote object
        footnote_id: The footnote ID
        lists: List definitions
        ctx: Conversion context

    Returns:
        HTML string for the footnote
    """
    content = footnote.get("content", [])
    inner_html = convert_body_content(content, lists, ctx)
    return f'<Footnote id="{html.escape(footnote_id)}">\n{inner_html}\n</Footnote>'


def convert_body_content(
    content: list[dict[str, Any]], lists: dict[str, Any], ctx: ConversionContext
) -> str:
    """Convert body content to HTML.

    Args:
        content: List of structural elements
        lists: List definitions from the document
        ctx: Conversion context

    Returns:
        HTML string for the body content
    """
    html_parts: list[str] = []

    # Track list state for grouping list items
    current_list_id: str | None = None
    current_list_items: list[tuple[int, str]] = []

    for element in content:
        if "sectionBreak" in element:
            # Section breaks are implicit in HTML - skip
            continue

        elif "paragraph" in element:
            para = element["paragraph"]
            bullet = para.get("bullet")

            if bullet:
                # This is a list item
                list_id = bullet.get("listId", "")
                nesting = bullet.get("nestingLevel", 0)

                if current_list_id != list_id:
                    # Finish previous list if any
                    if current_list_items:
                        html_parts.append(
                            wrap_list_items(current_list_items, lists, current_list_id)
                        )
                        current_list_items = []
                    current_list_id = list_id

                # Add list item
                para_html = convert_paragraph_to_li(para, ctx)
                current_list_items.append((nesting, para_html))
            else:
                # Not a list item - close any open list
                if current_list_items:
                    html_parts.append(
                        wrap_list_items(current_list_items, lists, current_list_id)
                    )
                    current_list_items = []
                    current_list_id = None

                # Convert regular paragraph
                para_html = convert_paragraph(para, ctx)
                html_parts.append(para_html)

        elif "table" in element:
            # Close any open list
            if current_list_items:
                html_parts.append(
                    wrap_list_items(current_list_items, lists, current_list_id)
                )
                current_list_items = []
                current_list_id = None

            table_html = convert_table(element["table"], lists, ctx)
            html_parts.append(table_html)

        elif "tableOfContents" in element:
            # Close any open list
            if current_list_items:
                html_parts.append(
                    wrap_list_items(current_list_items, lists, current_list_id)
                )
                current_list_items = []
                current_list_id = None

            toc_html = convert_toc(element["tableOfContents"], lists, ctx)
            html_parts.append(toc_html)

    # Close final list if any
    if current_list_items:
        html_parts.append(wrap_list_items(current_list_items, lists, current_list_id))

    return "\n".join(html_parts)


def wrap_list_items(
    items: list[tuple[int, str]],
    lists: dict[str, Any],
    list_id: str | None,
) -> str:
    """Wrap list items in appropriate ul/ol tags with nesting.

    Args:
        items: List of (nesting_level, li_html) tuples
        lists: List definitions
        list_id: The list ID

    Returns:
        HTML string with proper list nesting
    """
    if not items:
        return ""

    # Determine list type and class from list definition
    list_tag = "ul"
    list_class = "bullet"  # Default

    if list_id and list_id in lists:
        list_props = lists[list_id].get("listProperties", {})
        nesting_levels = list_props.get("nestingLevels", [])
        if nesting_levels:
            glyph_type = nesting_levels[0].get("glyphType", "")
            glyph_symbol = nesting_levels[0].get("glyphSymbol", "")

            # Map glyph types to tag and class
            if glyph_type == "DECIMAL":
                list_tag = "ol"
                list_class = "decimal"
            elif glyph_type in ("ALPHA", "UPPER_ALPHA"):
                list_tag = "ol"
                list_class = "alpha"
            elif glyph_type in ("ROMAN", "UPPER_ROMAN"):
                list_tag = "ol"
                list_class = "roman"
            elif glyph_symbol:
                # Checkbox lists use specific symbols
                # Common checkbox symbols: ☐ (U+2610), ☑ (U+2611), ☒ (U+2612)
                if glyph_symbol in ("☐", "☑", "☒", "\u2610", "\u2611", "\u2612"):
                    list_tag = "ul"
                    list_class = "checkbox"
                else:
                    list_tag = "ul"
                    list_class = "bullet"
            else:
                list_tag = "ul"
                list_class = "bullet"

    # Opening tag with class
    open_tag = f'<{list_tag} class="{list_class}">'
    close_tag = f"</{list_tag}>"

    # Build nested list structure
    html_parts: list[str] = []
    current_level = 0

    html_parts.append(open_tag)

    for nesting, li_html in items:
        while current_level < nesting:
            html_parts.append(open_tag)
            current_level += 1
        while current_level > nesting:
            html_parts.append(close_tag)
            current_level -= 1
        html_parts.append(li_html)

    while current_level > 0:
        html_parts.append(close_tag)
        current_level -= 1

    html_parts.append(close_tag)

    return "\n".join(html_parts)


def convert_paragraph_to_li(para: dict[str, Any], ctx: ConversionContext) -> str:
    """Convert a bulleted paragraph to an <li> element.

    Args:
        para: Paragraph object
        ctx: Conversion context

    Returns:
        HTML <li> element
    """
    content = convert_paragraph_elements(para.get("elements", []), ctx)
    return f"<li>{content}</li>"


def convert_paragraph(para: dict[str, Any], ctx: ConversionContext) -> str:
    """Convert a paragraph to HTML.

    Args:
        para: Paragraph object from the API
        ctx: Conversion context

    Returns:
        HTML string for the paragraph
    """
    style = para.get("paragraphStyle", {})
    named_style = style.get("namedStyleType", "NORMAL_TEXT")
    heading_id = style.get("headingId", "")

    # Convert paragraph elements to HTML
    content = convert_paragraph_elements(para.get("elements", []), ctx)

    # Determine tag and class based on named style
    tag = "p"
    css_class = ""

    if named_style == "TITLE":
        tag = "h1"
        css_class = "title"
    elif named_style == "SUBTITLE":
        tag = "p"
        css_class = "subtitle"
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

    # Build attributes
    attrs: list[str] = []
    if heading_id:
        attrs.append(f'id="{html.escape(heading_id)}"')
    if css_class:
        attrs.append(f'class="{css_class}"')

    attr_str = " " + " ".join(attrs) if attrs else ""

    # Handle empty paragraphs (just newline)
    if not content.strip():
        return f"<{tag}{attr_str}></{tag}>"

    return f"<{tag}{attr_str}>{content}</{tag}>"


def convert_paragraph_elements(
    elements: list[dict[str, Any]], ctx: ConversionContext
) -> str:
    """Convert paragraph elements to HTML inline content.

    Args:
        elements: List of paragraph elements
        ctx: Conversion context

    Returns:
        HTML string for inline content
    """
    html_parts: list[str] = []

    for elem in elements:
        if "textRun" in elem:
            text_html = convert_text_run(elem["textRun"])
            html_parts.append(text_html)

        elif "horizontalRule" in elem:
            # Standard HTML element - already atomic/self-closing
            html_parts.append("<hr/>")

        elif "pageBreak" in elem:
            # Custom element - atomic
            html_parts.append("<PageBreak/>")

        elif "columnBreak" in elem:
            html_parts.append("<ColumnBreak/>")

        elif "footnoteReference" in elem:
            ref = elem["footnoteReference"]
            fn_id = ref.get("footnoteId", "")
            fn_num = ref.get("footnoteNumber", "")
            # Custom element with attributes
            html_parts.append(
                f'<FootnoteRef id="{html.escape(fn_id)}" num="{html.escape(fn_num)}"/>'
            )

        elif "inlineObjectElement" in elem:
            obj_elem = elem["inlineObjectElement"]
            obj_id = obj_elem.get("inlineObjectId", "")
            # Look up the inline object
            if obj_id in ctx.inline_objects:
                obj = ctx.inline_objects[obj_id]
                img_html = convert_inline_object(obj, obj_id)
                html_parts.append(img_html)
            else:
                html_parts.append(f'<Image data-id="{html.escape(obj_id)}"/>')

        elif "person" in elem:
            person = elem["person"]
            props = person.get("personProperties", {})
            email = props.get("email", "")
            name = props.get("name", email)
            # Custom element - atomic
            html_parts.append(
                f'<Person email="{html.escape(email)}" name="{html.escape(name)}"/>'
            )

        elif "richLink" in elem:
            rich_link = elem["richLink"]
            props = rich_link.get("richLinkProperties", {})
            url = props.get("uri", "")
            title = props.get("title", url)
            # Custom element - atomic
            html_parts.append(
                f'<RichLink url="{html.escape(url)}" title="{html.escape(title)}"/>'
            )

        elif "dateElement" in elem:
            # Custom element - atomic
            html_parts.append("<Date/>")

        elif "equation" in elem:
            # Custom element - atomic (not editable)
            html_parts.append("<Equation/>")

        elif "autoText" in elem:
            # Auto text (page numbers, etc.)
            auto = elem["autoText"]
            auto_type = auto.get("type", "")
            html_parts.append(f'<AutoText type="{html.escape(auto_type)}"/>')

    return "".join(html_parts)


def convert_text_run(text_run: dict[str, Any]) -> str:
    """Convert a text run to HTML.

    Args:
        text_run: TextRun object

    Returns:
        HTML string for the text run
    """
    content: str = text_run.get("content", "")
    style = text_run.get("textStyle", {})

    # Strip trailing newline - it's implicit in HTML block elements
    if content.endswith("\n"):
        content = content[:-1]

    # Skip empty content
    if not content:
        return ""

    # Escape HTML entities
    escaped = html.escape(content)

    # Apply inline styles
    result: str = escaped

    # Check for link
    link = style.get("link")
    if link:
        url = link.get("url", "")
        heading_id = link.get("headingId")
        bookmark_id = link.get("bookmarkId")

        if url:
            result = f'<a href="{html.escape(url)}">{result}</a>'
        elif heading_id:
            result = f'<a href="#{html.escape(heading_id)}">{result}</a>'
        elif bookmark_id:
            result = f'<a href="#{html.escape(bookmark_id)}">{result}</a>'

    # Apply formatting (inside link if present)
    bold = style.get("bold", False)
    italic = style.get("italic", False)
    underline = style.get("underline", False)
    strikethrough = style.get("strikethrough", False)
    superscript = style.get("baselineOffset") == "SUPERSCRIPT"
    subscript = style.get("baselineOffset") == "SUBSCRIPT"

    if strikethrough:
        result = f"<s>{result}</s>"
    if underline and not link:  # Links already underlined
        result = f"<u>{result}</u>"
    if italic:
        result = f"<em>{result}</em>"
    if bold:
        result = f"<strong>{result}</strong>"
    if superscript:
        result = f"<sup>{result}</sup>"
    if subscript:
        result = f"<sub>{result}</sub>"

    return result


def convert_inline_object(obj: dict[str, Any], obj_id: str) -> str:
    """Convert an inline object (usually an image) to HTML.

    Args:
        obj: InlineObject from inlineObjects dict
        obj_id: The object ID

    Returns:
        HTML string for the inline object (custom <Image/> element)
    """
    props = obj.get("inlineObjectProperties", {})
    embedded = props.get("embeddedObject", {})

    # Check for image
    image_props = embedded.get("imageProperties", {})
    if image_props:
        content_uri = image_props.get("contentUri", "")
        source_uri = image_props.get("sourceUri", "")
        url = content_uri or source_uri

        # Get size if available
        size = embedded.get("size", {})
        width = size.get("width", {}).get("magnitude", "")
        height = size.get("height", {}).get("magnitude", "")

        attrs = [f'src="{html.escape(url)}"']
        if width:
            attrs.append(f'width="{width}pt"')
        if height:
            attrs.append(f'height="{height}pt"')

        title = embedded.get("title", "")
        desc = embedded.get("description", "")
        if title:
            attrs.append(f'title="{html.escape(title)}"')
        if desc:
            attrs.append(f'alt="{html.escape(desc)}"')

        return f"<Image {' '.join(attrs)}/>"

    # Fallback for unknown inline objects
    return f'<Image data-id="{html.escape(obj_id)}"/>'


def convert_table(
    table: dict[str, Any], lists: dict[str, Any], ctx: ConversionContext
) -> str:
    """Convert a table to HTML.

    Args:
        table: Table object
        lists: List definitions
        ctx: Conversion context

    Returns:
        HTML string for the table
    """
    html_parts: list[str] = ["<table>"]

    rows = table.get("tableRows", [])
    for row in rows:
        html_parts.append("  <tr>")

        cells = row.get("tableCells", [])
        for cell in cells:
            cell_style = cell.get("tableCellStyle", {})
            colspan = cell_style.get("columnSpan", 1)
            rowspan = cell_style.get("rowSpan", 1)

            attrs = []
            if colspan > 1:
                attrs.append(f'colspan="{colspan}"')
            if rowspan > 1:
                attrs.append(f'rowspan="{rowspan}"')

            attr_str = " " + " ".join(attrs) if attrs else ""

            # Convert cell content
            cell_content = cell.get("content", [])
            cell_html = convert_body_content(cell_content, lists, ctx)

            html_parts.append(f"    <td{attr_str}>{cell_html}</td>")

        html_parts.append("  </tr>")

    html_parts.append("</table>")
    return "\n".join(html_parts)


def convert_toc(
    toc: dict[str, Any], lists: dict[str, Any], ctx: ConversionContext
) -> str:
    """Convert a table of contents to HTML.

    Args:
        toc: TableOfContents object
        lists: List definitions
        ctx: Conversion context

    Returns:
        HTML string for the TOC (using <nav> element)
    """
    content = toc.get("content", [])
    toc_html = convert_body_content(content, lists, ctx)
    return f"<nav>\n{toc_html}\n</nav>"


# --- Index Reconstruction ---


@dataclass
class IndexPosition:
    """Tracks position during index reconstruction."""

    index: int = 0


def reconstruct_indexes_from_document(
    document: dict[str, Any],
) -> dict[str, tuple[int, int]]:
    """Walk the document structure and compute indexes for each element.

    This demonstrates that indexes can be derived from document structure.

    Args:
        document: The document JSON

    Returns:
        Dict mapping element paths to (startIndex, endIndex) tuples
    """
    indexes: dict[str, tuple[int, int]] = {}

    body = document.get("body", {})
    content = body.get("content", [])

    current_index = 0

    for i, element in enumerate(content):
        path = f"body.content[{i}]"
        start = current_index

        if "sectionBreak" in element:
            current_index += 1
            indexes[path] = (start, current_index)

        elif "paragraph" in element:
            para = element["paragraph"]
            para_start = current_index

            for j, elem in enumerate(para.get("elements", [])):
                elem_path = f"{path}.paragraph.elements[{j}]"
                elem_start = current_index

                if "textRun" in elem:
                    text = elem["textRun"].get("content", "")
                    current_index += utf16_len(text)
                elif (
                    "horizontalRule" in elem
                    or "pageBreak" in elem
                    or "columnBreak" in elem
                    or "footnoteReference" in elem
                    or "inlineObjectElement" in elem
                    or "person" in elem
                    or "richLink" in elem
                    or "dateElement" in elem
                ):
                    current_index += 1
                elif "equation" in elem:
                    # Equations have variable length - use actual
                    actual_end = elem.get("endIndex", elem_start + 1)
                    current_index = actual_end
                elif "autoText" in elem:
                    actual_end = elem.get("endIndex", elem_start + 1)
                    current_index = actual_end

                indexes[elem_path] = (elem_start, current_index)

            indexes[path] = (para_start, current_index)

        elif "table" in element:
            table = element["table"]
            table_start = current_index
            current_index += 1  # Table start marker

            for row_idx, row in enumerate(table.get("tableRows", [])):
                row_path = f"{path}.table.tableRows[{row_idx}]"
                row_start = current_index
                current_index += 1  # Row start marker

                for cell_idx, cell in enumerate(row.get("tableCells", [])):
                    cell_path = f"{row_path}.tableCells[{cell_idx}]"
                    cell_start = current_index
                    current_index += 1  # Cell start marker

                    # Recursively process cell content
                    for _k, _cell_elem in enumerate(cell.get("content", [])):
                        # Simplified - would need full recursion
                        pass

                    # Use actual end for cells
                    cell_end = cell.get("endIndex", current_index)
                    current_index = cell_end
                    indexes[cell_path] = (cell_start, cell_end)

                row_end = row.get("endIndex", current_index)
                current_index = row_end
                indexes[row_path] = (row_start, row_end)

            current_index += 1  # Table end marker
            indexes[path] = (table_start, current_index)

    return indexes
