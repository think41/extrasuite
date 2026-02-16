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
import json
from dataclasses import dataclass, field
from typing import Any

from .style_factorizer import (
    PARAGRAPH_STYLE_PROPS as PARA_EXTRACTORS,
)
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
class CommentAnchor:
    """A comment anchored to a position in the document."""

    comment_id: str
    start_index: int  # UTF-16 doc position
    end_index: int  # UTF-16 doc position
    message: str  # truncated comment content
    reply_count: int
    resolved: bool


@dataclass
class ConversionContext:
    """Tracks state during conversion."""

    styles: FactorizedStyles
    inline_objects: dict[str, dict[str, Any]] = field(default_factory=dict)
    footnotes: dict[str, dict[str, Any]] = field(default_factory=dict)
    lists: dict[str, Any] = field(default_factory=dict)
    # Named style → paragraph property defaults (from document namedStyles)
    named_style_para_defaults: dict[str, dict[str, str]] = field(default_factory=dict)
    # Comment anchors sorted by start_index
    comment_anchors: list[CommentAnchor] = field(default_factory=list)


def convert_document_to_xml(
    document: dict[str, Any],
    comments: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """Convert a Google Docs document to ExtraDoc XML format.

    Args:
        document: Raw document JSON from Google Docs API
        comments: Optional list of comment dicts from Drive API v3

    Returns:
        Tuple of (document_xml, styles_xml)
    """
    # Factorize styles first
    styles = factorize_styles(document)

    ctx = ConversionContext(styles=styles)
    ctx.inline_objects = document.get("inlineObjects", {})
    ctx.named_style_para_defaults = _build_named_style_para_defaults(document)

    # Parse comment anchors if provided
    if comments:
        ctx.comment_anchors = _parse_comment_anchors(comments, document)

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

    # Convert tabs
    tabs = document.get("tabs", [])
    if not tabs and "body" in document:
        # Legacy format (no includeTabsContent): synthesize a tab
        tabs = [
            {
                "tabProperties": {"tabId": "t.0", "title": ""},
                "documentTab": {
                    "body": document["body"],
                    "headers": document.get("headers", {}),
                    "footers": document.get("footers", {}),
                    "footnotes": document.get("footnotes", {}),
                    "lists": document.get("lists", {}),
                },
            }
        ]
    for tab in tabs:
        tab_xml = _convert_tab(tab, document, ctx)
        parts.append(tab_xml)

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

    # Headers (inside tab)
    for header_id, header in headers.items():
        header_xml = _convert_header_or_footer(
            header, header_id, "header", lists, ctx, indent=4
        )
        parts.append(header_xml)

    # Footers (inside tab)
    for footer_id, footer in footers.items():
        footer_xml = _convert_header_or_footer(
            footer, footer_id, "footer", lists, ctx, indent=4
        )
        parts.append(footer_xml)

    # Note: Footnotes are NOT converted separately - they are inlined
    # in the body where the footnote reference appears

    parts.append("  </tab>")

    return "\n".join(parts)


def _convert_header_or_footer(
    section: dict[str, Any],
    section_id: str,
    tag_name: str,
    lists: dict[str, Any],
    ctx: ConversionContext,
    indent: int = 2,
) -> str:
    """Convert a header or footer to XML."""
    content = section.get("content", [])
    prefix = " " * indent
    inner_xml = _convert_body_content(content, lists, ctx, indent=indent + 2)
    return f'{prefix}<{tag_name} id="{_escape(section_id)}" class="_base">\n{inner_xml}\n{prefix}</{tag_name}>'


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


# Map extractor names (from PARAGRAPH_STYLE_PROPS) to XML attribute names.
# This is the authoritative mapping for paragraph-level properties on pull.
_PARA_PROP_TO_ATTR: dict[str, str] = {
    "alignment": "align",
    "lineSpacing": "lineSpacing",
    "spaceAbove": "spaceAbove",
    "spaceBelow": "spaceBelow",
    "indentLeft": "indentLeft",
    "indentRight": "indentRight",
    "indentFirstLine": "indentFirst",
    # Boolean paragraph properties
    "keepTogether": "keepTogether",
    "keepNext": "keepNext",
    "avoidWidow": "avoidWidow",
    # Direction
    "direction": "direction",
    # Paragraph background (shading)
    "bgColor": "bgColor",
    # Paragraph borders
    "borderTop": "borderTop",
    "borderBottom": "borderBottom",
    "borderLeft": "borderLeft",
    "borderRight": "borderRight",
}


def _build_paragraph_attrs(
    style: dict[str, Any],
    named_style: str,
    ctx: ConversionContext,
) -> str:
    """Build XML attribute string for paragraph-level property overrides.

    Only includes properties that differ from the named style's defaults
    to keep the XML clean.
    """
    overrides = _extract_paragraph_overrides(style, named_style, ctx)
    if not overrides:
        return ""
    parts: list[str] = []
    for prop_name, attr_name in _PARA_PROP_TO_ATTR.items():
        if prop_name in overrides:
            parts.append(f'{attr_name}="{_escape(overrides[prop_name])}"')
    if not parts:
        return ""
    return " " + " ".join(parts)


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

    # Extract paragraph-level property overrides (alignment, spacing, etc.)
    # Only includes properties that differ from the named style's defaults.
    para_attrs = _build_paragraph_attrs(style, named_style, ctx)

    # Preserve whitespace content for accurate index calculation
    # Even spaces matter for Google Docs UTF-16 indexes
    if not content:
        return f"<{tag}{para_attrs}></{tag}>"

    return f"<{tag}{para_attrs}>{content}</{tag}>"


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

    # Extract paragraph-level property overrides for list items too
    style = para.get("paragraphStyle", {})
    para_attrs = _build_paragraph_attrs(style, "NORMAL_TEXT", ctx)

    return f'<li type="{list_type}" level="{nesting}"{para_attrs}>{content}</li>'


def _convert_paragraph_elements(
    elements: list[dict[str, Any]], ctx: ConversionContext
) -> str:
    """Convert paragraph elements to inline XML content."""
    parts: list[str] = []

    # Track which comment anchors are currently open (started but not closed)
    open_comments: list[CommentAnchor] = []

    for elem in elements:
        elem_start = elem.get("startIndex", 0)
        elem_end = elem.get("endIndex", 0)

        if "textRun" in elem:
            text_run = elem["textRun"]
            if ctx.comment_anchors:
                text_xml = _convert_text_run_with_comments(
                    text_run, elem_start, elem_end, ctx, open_comments
                )
            else:
                text_xml = _convert_text_run(text_run, ctx)
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
            # Rich links (chips) take exactly 1 index unit in Google Docs
            parts.append(
                f'<richlink url="{_escape(url)}" title="{_escape(link_title)}"/>'
            )

        elif "dateElement" in elem:
            date_elem = elem["dateElement"]
            date_props = date_elem.get("dateElementProperties", {})
            date_attrs: list[str] = []
            timestamp = date_props.get("timestamp", "")
            if timestamp:
                date_attrs.append(f'timestamp="{_escape(timestamp)}"')
            date_format = date_props.get("dateFormat", "")
            if date_format and date_format != "DATE_FORMAT_UNSPECIFIED":
                date_attrs.append(f'dateFormat="{_escape(date_format)}"')
            locale = date_props.get("locale", "")
            if locale:
                date_attrs.append(f'locale="{_escape(locale)}"')
            time_format = date_props.get("timeFormat", "")
            if time_format and time_format != "TIME_FORMAT_UNSPECIFIED":
                date_attrs.append(f'timeFormat="{_escape(time_format)}"')
            time_zone_id = date_props.get("timeZoneId", "")
            if time_zone_id:
                date_attrs.append(f'timeZoneId="{_escape(time_zone_id)}"')
            if date_attrs:
                parts.append(f"<date {' '.join(date_attrs)}/>")
            else:
                parts.append("<date/>")

        elif "equation" in elem:
            # Equations are opaque — the API gives no content, only
            # startIndex/endIndex.  Store the length so the block
            # indexer can account for the index span.
            eq_start = elem.get("startIndex", 0)
            eq_end = elem.get("endIndex", 0)
            eq_len = eq_end - eq_start
            parts.append(f'<equation length="{eq_len}"/>')

        elif "autoText" in elem:
            auto = elem["autoText"]
            auto_type = auto.get("type", "")
            parts.append(f'<autotext type="{_escape(auto_type)}"/>')

    # Close any still-open comments at end of paragraph
    for _ in open_comments:
        parts.append("</comment-ref>")
    open_comments.clear()

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


def _format_text_fragment(
    text: str, style: dict[str, Any], ctx: ConversionContext
) -> str:
    """Apply formatting to a text fragment (same logic as _convert_text_run).

    Used when splitting a text run at comment boundaries.
    """
    if not text:
        return ""

    result = _escape(text)

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

    if style.get("strikethrough"):
        result = f"<s>{result}</s>"
    if style.get("underline") and not link:
        result = f"<u>{result}</u>"
    if style.get("italic"):
        result = f"<i>{result}</i>"
    if style.get("bold"):
        result = f"<b>{result}</b>"
    if style.get("baselineOffset") == "SUPERSCRIPT":
        result = f"<sup>{result}</sup>"
    if style.get("baselineOffset") == "SUBSCRIPT":
        result = f"<sub>{result}</sub>"

    text_styles = extract_text_style(style)
    if text_styles:
        style_id = ctx.styles.get_style_id(text_styles)
        if style_id != "_base":
            result = f'<span class="{style_id}">{result}</span>'

    return result


def _convert_text_run_with_comments(
    text_run: dict[str, Any],
    run_start: int,
    run_end: int,
    ctx: ConversionContext,
    open_comments: list[CommentAnchor],
) -> str:
    """Convert a text run, injecting <comment-ref> tags where comments overlap.

    Args:
        text_run: The text run dict from API
        run_start: UTF-16 start index of the text run in document
        run_end: UTF-16 end index of the text run in document
        ctx: Conversion context with comment_anchors
        open_comments: Mutable list tracking currently open comment-refs
    """
    content: str = text_run.get("content", "")
    style = text_run.get("textStyle", {})

    # Strip trailing newline (paragraph terminator)
    has_newline = content.endswith("\n")
    if has_newline:
        content = content[:-1]
        run_end = run_end - 1  # newline is 1 UTF-16 unit

    if not content:
        return ""

    # Find all comment boundaries that intersect this text run
    # A boundary is a position where a comment starts or ends
    boundaries: list[
        tuple[int, str, CommentAnchor]
    ] = []  # (pos, "open"/"close", anchor)

    for anchor in ctx.comment_anchors:
        # Comment overlaps this run if anchor.start < run_end and anchor.end > run_start
        if anchor.start_index < run_end and anchor.end_index > run_start:
            # Open boundary (if starts within this run)
            if anchor.start_index >= run_start:
                boundaries.append((anchor.start_index, "open", anchor))
            elif anchor not in open_comments:
                # Comment started before this run — open at run start
                boundaries.append((run_start, "open", anchor))
            # Close boundary (if ends within this run)
            if anchor.end_index <= run_end:
                boundaries.append((anchor.end_index, "close", anchor))

    # Also close any open comments that end within this run
    for anchor in list(open_comments):
        if anchor.end_index <= run_end and not any(
            b[0] == anchor.end_index and b[1] == "close" and b[2] is anchor
            for b in boundaries
        ):
            boundaries.append((anchor.end_index, "close", anchor))

    if not boundaries:
        # No comment boundaries in this run — just format normally
        # But we may be inside an already-open comment, which is fine
        return _format_text_fragment(content, style, ctx)

    # Sort: by position, then closes before opens at same position
    boundaries.sort(key=lambda b: (b[0], 0 if b[1] == "close" else 1))

    # Split text at boundaries and wrap with comment-ref tags
    parts: list[str] = []
    cursor = run_start  # current position in UTF-16 index space

    for pos, action, anchor in boundaries:
        # Emit text before this boundary
        if pos > cursor:
            fragment = _substr_by_utf16(content, cursor - run_start, pos - run_start)
            if fragment:
                parts.append(_format_text_fragment(fragment, style, ctx))

        if action == "close":
            parts.append("</comment-ref>")
            if anchor in open_comments:
                open_comments.remove(anchor)
        else:  # open
            parts.append(_comment_ref_open_tag(anchor))
            open_comments.append(anchor)

        cursor = pos

    # Emit remaining text after last boundary
    if cursor < run_end:
        fragment = _substr_by_utf16(content, cursor - run_start, run_end - run_start)
        if fragment:
            parts.append(_format_text_fragment(fragment, style, ctx))

    return "".join(parts)


def _substr_by_utf16(text: str, start_units: int, end_units: int) -> str:
    """Extract a substring by UTF-16 code unit offsets.

    Args:
        text: The Python string
        start_units: Start offset in UTF-16 code units
        end_units: End offset in UTF-16 code units

    Returns:
        The substring
    """
    if start_units >= end_units:
        return ""

    char_start = 0
    char_end = len(text)
    units = 0

    for i, ch in enumerate(text):
        if units == start_units:
            char_start = i
        code_point = ord(ch)
        units += 2 if code_point > 0xFFFF else 1
        if units >= end_units:
            char_end = i + 1
            break

    return text[char_start:char_end]


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


def _build_named_style_para_defaults(
    document: dict[str, Any],
) -> dict[str, dict[str, str]]:
    """Build a mapping from named style type to paragraph property defaults.

    Extracts paragraph-level properties (alignment, spacing, indentation) from
    the document's namedStyles definitions so we can detect explicit overrides
    on individual paragraphs.
    """
    named_styles = document.get("namedStyles")
    if not named_styles:
        tabs = document.get("tabs", [])
        if tabs:
            doc_tab = tabs[0].get("documentTab", {})
            named_styles = doc_tab.get("namedStyles")
    if not named_styles:
        return {}

    result: dict[str, dict[str, str]] = {}
    for style_def in named_styles.get("styles", []):
        style_type = style_def.get("namedStyleType", "")
        if not style_type:
            continue
        para_style = style_def.get("paragraphStyle", {})
        props = _extract_para_props_raw(para_style)
        result[style_type] = props
    return result


def _extract_para_props_raw(para_style: dict[str, Any]) -> dict[str, str]:
    """Extract paragraph properties from a paragraphStyle dict."""
    props: dict[str, str] = {}
    for prop_name, extractor in PARA_EXTRACTORS:
        value = extractor(para_style)
        if value:
            props[prop_name] = value
    return props


def _extract_paragraph_overrides(
    para_style: dict[str, Any],
    named_style_type: str,
    ctx: ConversionContext,
) -> dict[str, str]:
    """Extract paragraph properties that override the named style defaults.

    Only returns properties that differ from what the named style defines,
    so the XML stays clean (no redundant attributes).
    """
    current = _extract_para_props_raw(para_style)
    if not current:
        return {}

    defaults = ctx.named_style_para_defaults.get(named_style_type, {})
    overrides: dict[str, str] = {}
    for prop, value in current.items():
        if defaults.get(prop) != value:
            overrides[prop] = value
    return overrides


def _parse_comment_anchors(
    comments: list[dict[str, Any]],
    document: dict[str, Any],
) -> list[CommentAnchor]:
    """Parse comment data from Drive API into CommentAnchor list.

    Uses quotedFileContent to find comment positions in the document by
    searching through text runs. The Drive API v3 anchor field is opaque
    for Google Docs (a kix ID), so we match quoted text instead.

    Returns anchors sorted by start_index.
    """
    # Build a text index from the document for quoted text search
    text_index = _build_text_index(document)

    anchors: list[CommentAnchor] = []
    for comment in comments:
        if comment.get("deleted", False):
            continue

        start_index: int | None = None
        end_index: int | None = None

        # Strategy 1: Try parsing anchor as JSON (API-created comments)
        anchor_str = comment.get("anchor", "")
        if anchor_str:
            start_index, end_index = _parse_anchor_json(anchor_str)

        # Strategy 2: Fall back to quotedFileContent text search (UI-created comments)
        if start_index is None:
            quoted_fc = comment.get("quotedFileContent", {})
            quoted_text = quoted_fc.get("value", "") if quoted_fc else ""
            if quoted_text:
                quoted_text = html.unescape(quoted_text)
                pos = _find_quoted_text(text_index, quoted_text)
                if pos is not None:
                    start_index, end_index = pos

        if start_index is None or end_index is None:
            continue

        content = comment.get("content", "")
        # Truncate message to ~20 chars
        message = content[:20] + "..." if len(content) > 20 else content

        replies = comment.get("replies", [])
        non_deleted = [r for r in replies if not r.get("deleted", False)]

        anchors.append(
            CommentAnchor(
                comment_id=comment["id"],
                start_index=start_index,
                end_index=end_index,
                message=message,
                reply_count=len(non_deleted),
                resolved=comment.get("resolved", False),
            )
        )

    anchors.sort(key=lambda a: a.start_index)
    return anchors


def _build_text_index(document: dict[str, Any]) -> str:
    """Build a full-text string from the document, preserving API positions.

    Returns a string where character at position i corresponds to document
    index i. This allows simple substring search to find positions.
    """
    max_index = 0

    def _scan_content(content_list: list[dict[str, Any]]) -> None:
        nonlocal max_index
        for elem in content_list:
            ei = elem.get("endIndex", 0)
            if ei > max_index:
                max_index = ei
            if "paragraph" in elem:
                for pe in elem["paragraph"].get("elements", []):
                    ei = pe.get("endIndex", 0)
                    if ei > max_index:
                        max_index = ei
            elif "table" in elem:
                for row in elem["table"].get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        _scan_content(cell.get("content", []))

    # Scan all tabs to find max index
    for tab in document.get("tabs", []):
        doc_tab = tab.get("documentTab", {})
        body = doc_tab.get("body", {})
        _scan_content(body.get("content", []))

    # Build character array (null chars as placeholders)
    chars = ["\x00"] * max_index

    def _fill_content(content_list: list[dict[str, Any]]) -> None:
        for elem in content_list:
            if "paragraph" in elem:
                for pe in elem["paragraph"].get("elements", []):
                    tr = pe.get("textRun", {})
                    text = tr.get("content", "")
                    si = pe.get("startIndex", 0)
                    for j, ch in enumerate(text):
                        idx = si + j
                        if idx < len(chars):
                            chars[idx] = ch
            elif "table" in elem:
                for row in elem["table"].get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        _fill_content(cell.get("content", []))

    for tab in document.get("tabs", []):
        doc_tab = tab.get("documentTab", {})
        body = doc_tab.get("body", {})
        _fill_content(body.get("content", []))

    return "".join(chars)


def _parse_anchor_json(anchor_str: str) -> tuple[int | None, int | None]:
    """Try to parse anchor as JSON with position info.

    API-created comments use JSON format: {"r":"head","a":[{"txt":{"o":42,"l":13}}]}
    UI-created comments use opaque kix IDs which will fail JSON parsing.
    """
    try:
        anchor = json.loads(anchor_str)
        anchors = anchor.get("a", [])
        if anchors:
            txt = anchors[0].get("txt", {})
            offset = txt.get("o")
            length = txt.get("l")
            if offset is not None and length is not None:
                return int(offset), int(offset) + int(length)
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        pass
    return None, None


def _find_quoted_text(text_index: str, quoted_text: str) -> tuple[int, int] | None:
    """Find the position of quoted text in the document text index.

    Returns (start_index, end_index) or None if not found.
    """
    pos = text_index.find(quoted_text)
    if pos == -1:
        return None
    return pos, pos + len(quoted_text)


def _comment_ref_open_tag(anchor: CommentAnchor) -> str:
    """Produce <comment-ref ...> open tag."""
    msg = _escape(anchor.message)
    return (
        f'<comment-ref id="{_escape(anchor.comment_id)}"'
        f' message="{msg}"'
        f' replies="{anchor.reply_count}"'
        f' resolved="{"true" if anchor.resolved else "false"}">'
    )
