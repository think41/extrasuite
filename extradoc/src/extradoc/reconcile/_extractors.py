"""Extract text and fingerprints from Document structures."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from extradoc.api_types._generated import (
        DocumentTab,
        Paragraph,
        StructuralElement,
        Tab,
        Table,
    )


def extract_plain_text_from_paragraph(para: Paragraph) -> str:
    """Extract concatenated text from all textRun elements in a paragraph."""
    parts: list[str] = []
    for elem in para.elements or []:
        if elem.text_run and elem.text_run.content:
            parts.append(elem.text_run.content)
        elif elem.footnote_reference:
            # Footnote references are represented as a single character
            parts.append("\u0001")
        elif elem.inline_object_element:
            parts.append("\u0002")
        elif elem.horizontal_rule or elem.page_break:
            parts.append("\n")
    return "".join(parts)


def extract_plain_text_from_table(table: Table) -> str:
    """Extract all text from a table, recursing into cells."""
    parts: list[str] = []
    for row in table.table_rows or []:
        for cell in row.table_cells or []:
            for se in cell.content or []:
                parts.append(extract_plain_text(se))
    return "".join(parts)


def extract_plain_text(se: StructuralElement) -> str:
    """Extract plain text from a StructuralElement."""
    if se.paragraph:
        return extract_plain_text_from_paragraph(se.paragraph)
    if se.table:
        return extract_plain_text_from_table(se.table)
    if se.section_break:
        return ""
    if se.table_of_contents:
        return "[TOC]"
    return ""


def content_fingerprint(se: StructuralElement) -> str:
    """Create a fingerprint for a StructuralElement for LCS matching.

    Format: "<type>:<text_content>"
    The type prefix ensures paragraphs and tables don't accidentally match.
    """
    if se.paragraph:
        text = extract_plain_text_from_paragraph(se.paragraph)
        return f"P:{text}"
    if se.table:
        rows = se.table.rows or 0
        cols = se.table.columns or 0
        text = extract_plain_text_from_table(se.table)
        return f"T:{rows}x{cols}:{text}"
    if se.section_break:
        return "SB:"
    if se.table_of_contents:
        return "TOC:"
    return "UNKNOWN:"


SegmentInfo = dict[str, Any]
# Keys: "segment_id" (str|None), "content" (list[StructuralElement])


def extract_segments(tab: Tab) -> dict[str, SegmentInfo]:
    """Extract all segments from a tab.

    Returns a dict keyed by segment identifier:
    - "body" for the body
    - header_id for each header
    - footer_id for each footer
    - footnote_id for each footnote
    """
    segments: dict[str, SegmentInfo] = {}
    doc_tab: DocumentTab | None = tab.document_tab
    if not doc_tab:
        return segments

    if doc_tab.body and doc_tab.body.content:
        segments["body"] = {
            "segment_id": None,  # body has no segment_id in API
            "content": doc_tab.body.content,
        }

    for hid, header in (doc_tab.headers or {}).items():
        segments[hid] = {
            "segment_id": hid,
            "content": header.content or [],
        }

    for fid, footer in (doc_tab.footers or {}).items():
        segments[fid] = {
            "segment_id": fid,
            "content": footer.content or [],
        }

    for fnid, footnote in (doc_tab.footnotes or {}).items():
        segments[fnid] = {
            "segment_id": fnid,
            "content": footnote.content or [],
        }

    return segments
