"""Content request generation for Google Docs batchUpdate.

Generates requests for text content operations including:
- Text insertion (insertText)
- Text style updates (updateTextStyle)
- Paragraph style updates (updateParagraphStyle)
- Bullet creation (createParagraphBullets)
- Special element insertion (pagebreak, section break)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

from extradoc.indexer import utf16_len
from extradoc.style_converter import (
    PARAGRAPH_STYLE_PROPS,
    TEXT_STYLE_PROPS,
    convert_styles,
)

# Heading tags that map to named paragraph styles
HEADING_STYLES: dict[str, str] = {
    "title": "TITLE",
    "subtitle": "SUBTITLE",
    "h1": "HEADING_1",
    "h2": "HEADING_2",
    "h3": "HEADING_3",
    "h4": "HEADING_4",
    "h5": "HEADING_5",
    "h6": "HEADING_6",
}

# Inline formatting tags
INLINE_STYLE_TAGS: dict[str, str] = {
    "b": "bold",
    "i": "italic",
    "u": "underline",
    "s": "strikethrough",
    "sup": "superscript",
    "sub": "subscript",
}

# Special elements that consume 1 index
SPECIAL_ELEMENT_TAGS: frozenset[str] = frozenset(
    {
        "hr",
        "pagebreak",
        "columnbreak",
        "image",
        "footnote",
        "footnoteref",
        "person",
        "autotext",
        "date",
        "equation",
    }
)

# Bullet type to Google Docs preset mapping
BULLET_PRESETS: dict[str, str] = {
    "bullet": "BULLET_DISC_CIRCLE_SQUARE",
    "decimal": "NUMBERED_DECIMAL_NESTED",
    "alpha": "NUMBERED_UPPERCASE_ALPHA",
    "roman": "NUMBERED_UPPERCASE_ROMAN",
    "checkbox": "BULLET_CHECKBOX",
}


@dataclass
class TextRun:
    """A text run with style information."""

    text: str
    start_offset: int  # Offset within the content block
    end_offset: int  # End offset within the content block
    styles: dict[str, str] = field(default_factory=dict)


@dataclass
class ParagraphInfo:
    """Information about a paragraph."""

    start_offset: int  # Start offset within content block
    end_offset: int  # End offset (after newline)
    tag: str  # Original tag (p, h1, li, etc.)
    named_style: str = "NORMAL_TEXT"
    bullet_type: str | None = None
    bullet_level: int = 0
    styles: dict[str, str] = field(default_factory=dict)


@dataclass
class SpecialElement:
    """A special element (pagebreak, hr, etc.)."""

    element_type: str
    offset: int  # Offset within content block
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedContent:
    """Parsed content block ready for request generation.

    Attributes:
        plain_text: Text content with newlines between paragraphs
        text_runs: List of TextRun objects with style info
        paragraphs: List of ParagraphInfo objects
        special_elements: List of SpecialElement objects
    """

    plain_text: str
    text_runs: list[TextRun] = field(default_factory=list)
    paragraphs: list[ParagraphInfo] = field(default_factory=list)
    special_elements: list[SpecialElement] = field(default_factory=list)


def parse_content_xml(xml_content: str) -> ParsedContent:
    """Parse ContentBlock XML into structured data for request generation.

    The XML content is a sequence of paragraph elements (p, h1, li, etc.).
    This function extracts:
    - Plain text with newlines between paragraphs
    - Text runs with style information
    - Paragraph metadata (named style, bullets)
    - Special elements (pagebreak, hr, etc.)

    Args:
        xml_content: XML string containing paragraph elements

    Returns:
        ParsedContent with extracted information
    """
    # Wrap in a root element for parsing
    wrapped = f"<root>{xml_content}</root>"
    try:
        root = ET.fromstring(wrapped)
    except ET.ParseError:
        return ParsedContent(plain_text="")

    plain_text_parts: list[str] = []
    text_runs: list[TextRun] = []
    paragraphs: list[ParagraphInfo] = []
    special_elements: list[SpecialElement] = []

    current_offset = 0  # UTF-16 offset tracking

    for para_elem in root:
        tag = para_elem.tag
        para_start = current_offset

        # Determine paragraph type
        named_style = HEADING_STYLES.get(tag, "NORMAL_TEXT")
        bullet_type = None
        bullet_level = 0

        if tag == "li":
            bullet_type = para_elem.get("type", "bullet")
            bullet_level = int(para_elem.get("level", "0"))

        # Extract text runs from this paragraph
        para_text, para_specials, para_runs = _extract_paragraph_content(
            para_elem, current_offset
        )

        # For nested bullets, prepend leading tabs (Google Docs uses tabs for nesting)
        if bullet_level > 0:
            tabs = "\t" * bullet_level
            tab_len = utf16_len(tabs)
            para_text = tabs + para_text
            # Adjust offsets for specials and runs
            para_specials = [
                SpecialElement(s.element_type, s.offset + tab_len, s.attributes)
                for s in para_specials
            ]
            para_runs = [
                TextRun(
                    r.text, r.start_offset + tab_len, r.end_offset + tab_len, r.styles
                )
                for r in para_runs
            ]

        plain_text_parts.append(para_text)
        special_elements.extend(para_specials)
        text_runs.extend(para_runs)

        # Calculate paragraph end (after newline)
        para_end = current_offset + utf16_len(para_text) + 1  # +1 for newline

        # Create paragraph info
        para_styles = dict(para_elem.attrib)
        paragraphs.append(
            ParagraphInfo(
                start_offset=para_start,
                end_offset=para_end,
                tag=tag,
                named_style=named_style,
                bullet_type=bullet_type,
                bullet_level=bullet_level,
                styles=para_styles,
            )
        )

        # Update offset (text + newline)
        current_offset = para_end

    # Join paragraphs with newlines
    plain_text = "\n".join(plain_text_parts)
    if plain_text_parts:
        plain_text += "\n"  # Trailing newline for last paragraph

    return ParsedContent(
        plain_text=plain_text,
        text_runs=text_runs,
        paragraphs=paragraphs,
        special_elements=special_elements,
    )


def _extract_paragraph_content(
    para_elem: ET.Element,
    base_offset: int,
) -> tuple[str, list[SpecialElement], list[TextRun]]:
    """Extract text, special elements, and text runs from a paragraph element.

    Args:
        para_elem: The paragraph XML element
        base_offset: The starting offset for this paragraph

    Returns:
        Tuple of (plain_text, special_elements, text_runs)
    """
    plain_text_parts: list[str] = []
    special_elements: list[SpecialElement] = []
    text_runs: list[TextRun] = []

    current_offset = base_offset

    def process_node(
        node: ET.Element,
        inherited_styles: dict[str, str],
    ) -> None:
        nonlocal current_offset

        tag = node.tag
        node_styles = inherited_styles.copy()

        # Update styles based on tag
        if tag in INLINE_STYLE_TAGS:
            node_styles[INLINE_STYLE_TAGS[tag]] = "1"
        elif tag == "a":
            href = node.get("href", "")
            if href:
                node_styles["link"] = href
        elif tag == "span":
            # Span with class - copy all attributes as potential styles
            for attr, value in node.attrib.items():
                if attr != "class":
                    node_styles[attr] = value

        # Handle text content
        if node.text:
            text = node.text
            text_len = utf16_len(text)
            plain_text_parts.append(text)

            # Create text run if we have styles
            if node_styles:
                text_runs.append(
                    TextRun(
                        text=text,
                        start_offset=current_offset,
                        end_offset=current_offset + text_len,
                        styles=node_styles.copy(),
                    )
                )

            current_offset += text_len

        # Process children
        for child in node:
            child_tag = child.tag

            # Special elements
            if child_tag in SPECIAL_ELEMENT_TAGS:
                attrs = dict(child.attrib)
                special_elements.append(
                    SpecialElement(
                        element_type=child_tag,
                        offset=current_offset,
                        attributes=attrs,
                    )
                )
                # Don't add to plain_text - will be inserted separately
            else:
                # Recurse for inline formatting
                process_node(child, node_styles)

            # Handle tail text (text after child element)
            if child.tail:
                tail = child.tail
                tail_len = utf16_len(tail)
                plain_text_parts.append(tail)

                # Tail inherits parent styles (not child's)
                if inherited_styles:
                    text_runs.append(
                        TextRun(
                            text=tail,
                            start_offset=current_offset,
                            end_offset=current_offset + tail_len,
                            styles=inherited_styles.copy(),
                        )
                    )

                current_offset += tail_len

    # Handle paragraph element's direct text
    if para_elem.text:
        text = para_elem.text
        text_len = utf16_len(text)
        plain_text_parts.append(text)
        current_offset += text_len

    # Process children
    for child in para_elem:
        child_tag = child.tag

        if child_tag in SPECIAL_ELEMENT_TAGS:
            attrs = dict(child.attrib)
            special_elements.append(
                SpecialElement(
                    element_type=child_tag,
                    offset=current_offset,
                    attributes=attrs,
                )
            )
        else:
            process_node(child, {})

        if child.tail:
            tail = child.tail
            tail_len = utf16_len(tail)
            plain_text_parts.append(tail)
            current_offset += tail_len

    return "".join(plain_text_parts), special_elements, text_runs


def generate_content_requests(
    xml_content: str,
    segment_id: str | None,
    insert_index: int,
    strip_trailing_newline: bool = False,
) -> list[dict[str, Any]]:
    """Generate batchUpdate requests for content XML.

    Strategy:
    1. Parse XML to extract plain text, styles, and paragraph info
    2. Insert plain text - newlines automatically create paragraphs
    3. Reset formatting on inserted text
    4. Insert special elements from highest offset to lowest
    5. Apply paragraph styles (headings)
    6. Apply bullets
    7. Apply text styles (bold, italic, links)

    Args:
        xml_content: The ContentBlock XML (sequence of paragraph elements)
        segment_id: The segment ID (header/footer/footnote ID, or None for body)
        insert_index: The index at which to insert content
        strip_trailing_newline: If True, strip the trailing newline from the text

    Returns:
        List of batchUpdate requests
    """
    if not xml_content or not xml_content.strip():
        return []

    parsed = parse_content_xml(xml_content)

    # Strip trailing newline if requested
    plain_text = parsed.plain_text
    if strip_trailing_newline and plain_text.endswith("\n"):
        plain_text = plain_text[:-1]

    if not plain_text:
        return []

    requests: list[dict[str, Any]] = []

    # Helper to build location/range objects
    def make_location(offset: int) -> dict[str, Any]:
        loc: dict[str, Any] = {"index": insert_index + offset}
        if segment_id:
            loc["segmentId"] = segment_id
        return loc

    def make_range(start: int, end: int) -> dict[str, Any]:
        rng: dict[str, Any] = {
            "startIndex": insert_index + start,
            "endIndex": insert_index + end,
        }
        if segment_id:
            rng["segmentId"] = segment_id
        return rng

    # 1. Insert plain text
    requests.append(
        {
            "insertText": {
                "location": make_location(0),
                "text": plain_text,
            }
        }
    )

    # 2. Reset formatting on inserted text to prevent style inheritance
    text_len = utf16_len(plain_text)
    requests.append(
        {
            "updateTextStyle": {
                "range": make_range(0, text_len),
                "textStyle": {
                    "bold": False,
                    "italic": False,
                    "underline": False,
                    "strikethrough": False,
                    "baselineOffset": "NONE",
                },
                "fields": "bold,italic,underline,strikethrough,baselineOffset",
            }
        }
    )

    # 3. Insert special elements (highest offset first to maintain index stability)
    for special in sorted(
        parsed.special_elements, key=lambda x: x.offset, reverse=True
    ):
        special_req = _generate_special_element_request(
            special, insert_index, segment_id
        )
        if special_req:
            requests.append(special_req)

    # 4. Apply paragraph styles (headings, etc.)
    for para in parsed.paragraphs:
        # Named style (headings)
        if para.named_style != "NORMAL_TEXT":
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": make_range(para.start_offset, para.end_offset),
                        "paragraphStyle": {"namedStyleType": para.named_style},
                        "fields": "namedStyleType",
                    }
                }
            )

        # Additional paragraph styles from attributes
        para_style, para_fields = convert_styles(para.styles, PARAGRAPH_STYLE_PROPS)
        if para_fields:
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": make_range(para.start_offset, para.end_offset),
                        "paragraphStyle": para_style,
                        "fields": ",".join(para_fields),
                    }
                }
            )

    # 5. Apply bullets - consolidate consecutive bullets of same type into single request
    # This is required because createParagraphBullets removes leading tabs, shifting indices
    bullet_groups: list[tuple[int, int, str]] = []  # (start, end, preset)
    for para in parsed.paragraphs:
        if para.bullet_type:
            preset = BULLET_PRESETS.get(para.bullet_type, "BULLET_DISC_CIRCLE_SQUARE")
            # Only extend if bullets are adjacent (prev_end == current_start) and same type
            if (
                bullet_groups
                and bullet_groups[-1][2] == preset
                and bullet_groups[-1][1] == para.start_offset
            ):
                # Extend the previous group
                bullet_groups[-1] = (bullet_groups[-1][0], para.end_offset, preset)
            else:
                # Start a new group
                bullet_groups.append((para.start_offset, para.end_offset, preset))

    # Create one request per group
    for group_start, group_end, preset in bullet_groups:
        requests.append(
            {
                "createParagraphBullets": {
                    "range": make_range(group_start, group_end),
                    "bulletPreset": preset,
                }
            }
        )
    # Note: Nesting level is determined by leading tabs in the inserted text
    # (handled in parse_content_xml). Tabs are removed by createParagraphBullets.

    # 6. Apply text styles (bold, italic, links, etc.)
    for run in parsed.text_runs:
        text_style, text_fields = convert_styles(run.styles, TEXT_STYLE_PROPS)
        if text_fields:
            requests.append(
                {
                    "updateTextStyle": {
                        "range": make_range(run.start_offset, run.end_offset),
                        "textStyle": text_style,
                        "fields": ",".join(text_fields),
                    }
                }
            )

    return requests


def _generate_special_element_request(
    special: SpecialElement,
    insert_index: int,
    segment_id: str | None,
) -> dict[str, Any] | None:
    """Generate a request for a special element.

    Args:
        special: The SpecialElement to insert
        insert_index: Base insertion index
        segment_id: Optional segment ID

    Returns:
        A batchUpdate request dict, or None if not supported
    """
    location: dict[str, Any] = {"index": insert_index + special.offset}
    if segment_id:
        location["segmentId"] = segment_id

    element_type = special.element_type

    if element_type == "pagebreak":
        return {"insertPageBreak": {"location": location}}

    elif element_type == "columnbreak":
        # Column break is inserted via insertSectionBreak with CONTINUOUS type
        return {
            "insertSectionBreak": {
                "location": location,
                "sectionType": "CONTINUOUS",
            }
        }

    elif element_type in ("footnote", "footnoteref"):
        # Footnote creation - returns a request with placeholder ID
        # Both "footnote" (inline with content) and "footnoteref" (reference only) use the same request
        # For "footnote", the content will be populated in a second batch after the footnote is created
        placeholder = special.attributes.get("id", "")
        req: dict[str, Any] = {
            "createFootnote": {
                "location": location,
            }
        }
        if placeholder:
            req["_placeholderFootnoteId"] = placeholder
        return req

    # Note: hr, image, person, autotext, date, equation require different handling
    # hr: Cannot be inserted via API, handled via paragraph border styling
    # image: Requires separate upload flow
    # person: Requires specific personProperties
    # autotext: Cannot be inserted via batchUpdate
    # date: Cannot be inserted via batchUpdate
    # equation: Requires specific equation content

    return None


def generate_delete_content_request(
    start_index: int,
    end_index: int,
    segment_id: str | None = None,
    segment_end_index: int = 0,
) -> dict[str, Any] | None:
    """Generate a deleteContentRange request.

    Args:
        start_index: Start index in the document
        end_index: End index in the document
        segment_id: Optional segment ID for headers/footers/footnotes
        segment_end_index: End index of the containing segment (for boundary detection)

    Returns:
        A deleteContentRange request dict, or None if range is invalid

    Note:
        Google Docs API does not allow deleting the final newline of a segment.
        If end_index equals segment_end_index, we reduce it by 1 to preserve
        that final newline.
    """
    # Adjust end_index if it would delete the segment's final newline
    if segment_end_index > 0 and end_index >= segment_end_index:
        end_index = segment_end_index - 1

    if start_index >= end_index:
        return None

    range_spec: dict[str, Any] = {
        "startIndex": start_index,
        "endIndex": end_index,
    }
    if segment_id:
        range_spec["segmentId"] = segment_id

    return {"deleteContentRange": {"range": range_spec}}
