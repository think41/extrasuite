"""Snap-fit comment anchor offsets to serde XML element boundaries.

Computes character offsets for each block element in a serde document.xml
<body> and maps anchor (start, end) ranges to the set of elements that
overlap with that range.

The snap-fit expands the range to whole element boundaries — a comment
anchored to 2 words in a paragraph expands to cover the whole paragraph.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

# Tags that are block-level elements in the serde XML body
_BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "title", "subtitle", "li"}

# Inline special tags that consume 1 character each
_SPECIAL_INLINE_TAGS = {
    "img",
    "hr",
    "footnote-ref",
    "person",
    "rich-link",
    "column-break",
    "page-break",
    "soft-break",
    "date",
    "auto-text",
    "equation",
}


@dataclass
class ElementSpan:
    """A block element and its character span in the document."""

    element: ET.Element
    start: int  # inclusive, 0-based from body start
    end: int  # exclusive


def compute_element_spans(body_elem: ET.Element) -> list[ElementSpan]:
    """Walk the <body> element and compute character spans for each block.

    Character counting rules (mirroring Google Docs API positions):
    - <sectionbreak>: 1 char
    - <p>, <h1>, ..., <li>: sum of text chars in children + 1 (trailing \\n)
    - <table>: 1 char per cell row-start/end + recursion through cells
    - TOC: treated as a single block

    Args:
        body_elem: The <body> XML element from a serde document.xml

    Returns:
        List of ElementSpan for each direct child of <body>
    """
    spans: list[ElementSpan] = []
    offset = 0

    for child in body_elem:
        start = offset
        size = _element_char_count(child)
        offset += size
        spans.append(ElementSpan(element=child, start=start, end=offset))

    return spans


def _element_char_count(elem: ET.Element) -> int:
    """Compute the character count for a single element."""
    tag = elem.tag

    if tag == "sectionbreak":
        return 1

    if tag in _BLOCK_TAGS:
        # Text chars + 1 for trailing newline
        return _inline_text_len(elem) + 1

    if tag == "table":
        return _table_char_count(elem)

    if tag == "toc":
        # Table of contents: treat as opaque block
        return _toc_char_count(elem)

    # Unknown block — count as 1
    return 1


def _table_char_count(table_elem: ET.Element) -> int:
    """Compute character count for a <table> element.

    Each table row opens and closes (2 chars structural), and each cell
    opens and closes (2 chars structural), plus cell content.
    """
    total = 0
    for row in table_elem.findall("row"):
        total += 1  # row start
        for cell in row.findall("cell"):
            total += 1  # cell start
            for block in cell:
                total += _element_char_count(block)
        total += 1  # row end
    return total


def _toc_char_count(toc_elem: ET.Element) -> int:
    """Compute character count for a <toc> element."""
    total = 0
    for child in toc_elem:
        total += _element_char_count(child)
    return max(total, 1)


def _inline_text_len(elem: ET.Element) -> int:
    """Count characters in the inline content of a block element."""
    total = 0

    # elem.text is text before the first child
    if elem.text:
        total += len(elem.text)

    for child in elem:
        child_tag = child.tag

        if child_tag in _SPECIAL_INLINE_TAGS:
            if child_tag == "equation":
                # equation element has a length attribute
                length_str = child.get("length", "1")
                try:
                    total += int(length_str)
                except ValueError:
                    total += 1
            else:
                total += 1
        else:
            # Inline formatting wrapper: <b>, <i>, <u>, <s>, <sup>, <sub>
            # or <t>, <a>, <comment-ref> — recurse
            total += _inline_text_len(child)

        # tail text after the child
        if child.tail:
            total += len(child.tail)

    return total


def find_overlapping_elements(
    spans: list[ElementSpan],
    anchor_start: int,
    anchor_end: int,
) -> list[ElementSpan]:
    """Find all ElementSpans that overlap with the [anchor_start, anchor_end) range.

    Returns the subset of spans that overlap, already expanded to full element
    boundaries (the snap-fit). Skips sectionbreak elements.

    Args:
        spans: Output from compute_element_spans()
        anchor_start: Start offset (inclusive) from comment anchor
        anchor_end: End offset (exclusive) from comment anchor

    Returns:
        List of overlapping ElementSpan objects
    """
    result: list[ElementSpan] = []
    for span in spans:
        if span.element.tag == "sectionbreak":
            continue
        # Overlap condition: span.start < anchor_end and span.end > anchor_start
        if span.start < anchor_end and span.end > anchor_start:
            result.append(span)
    return result


def parse_anchor_range(anchor: str) -> tuple[int, int] | None:
    """Parse a Drive API anchor string to extract (start_offset, end_offset).

    Anchor format: {"r":"head","a":[{"txt":{"o":<offset>,"l":<length>}}]}

    Args:
        anchor: Raw anchor string from the Drive API

    Returns:
        (start, end) tuple or None if not parseable / not a text anchor
    """
    if not anchor:
        return None
    try:
        data = json.loads(anchor)
        annotations = data.get("a", [])
        for ann in annotations:
            txt = ann.get("txt")
            if txt is not None:
                offset = int(txt.get("o", 0))
                length = int(txt.get("l", 0))
                return offset, offset + length
        return None
    except (json.JSONDecodeError, TypeError, KeyError, ValueError):
        return None
