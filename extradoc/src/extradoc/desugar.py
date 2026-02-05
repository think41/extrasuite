"""Desugar transform for ExtraDoc XML.

Transforms sugar elements to internal representation for diffing:
- <h1> -> <p style="HEADING_1">
- <li type="..." level="..."> -> <p bullet="..." level="...">
- <tr>/<td> -> flat <td row="r" col="c">
- <b>text</b> -> <t bold="1">text</t>
- <style class="..."> -> apply class to children

INDEX COUNTING MODEL
====================

Google Docs uses UTF-16 code unit based indexing. This module implements:

1. Paragraph length: utf16_len(content) + 1
   - The +1 is for the trailing newline (represented by </p>)
   - Empty paragraph <p></p> = 1 (just the newline)

2. Special elements inside paragraphs: +1 each
   - <hr/>, <pagebreak/>, <columnbreak/>, <image/>, <person/>, etc.

3. Container closes (</body>, </td>, etc.): 0 index cost

4. RULE: Every container must have at least one paragraph
   - Body, headers, footers, footnotes, and table cells always have >= 1 paragraph
   - The final paragraph CANNOT be deleted (Google Docs API constraint)

Examples:
    <p>Hello</p>          = 5 + 1 = 6
    <p><hr/></p>          = 1 + 1 = 2
    <p></p>               = 0 + 1 = 1
    <p>A<pagebreak/>B</p> = 1 + 1 + 1 + 1 = 4
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element

from .indexer import utf16_len

# Heading tags to named styles
HEADING_STYLES = {
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
INLINE_TAGS = {
    "b": "bold",
    "i": "italic",
    "u": "underline",
    "s": "strikethrough",
    "sup": "superscript",
    "sub": "subscript",
}


@dataclass
class TextRun:
    """A text run with style attributes."""

    text: str
    styles: dict[str, str] = field(default_factory=dict)

    def utf16_length(self) -> int:
        # Special elements (columnbreak, pagebreak, etc.) take 1 index in Google Docs
        if "_special" in self.styles:
            return 1
        return utf16_len(self.text)


@dataclass
class Paragraph:
    """A desugared paragraph."""

    runs: list[TextRun] = field(default_factory=list)
    named_style: str = "NORMAL_TEXT"
    bullet_type: str | None = None
    bullet_level: int = 0
    style_class: str | None = None

    def text_content(self) -> str:
        return "".join(run.text for run in self.runs)

    def utf16_length(self) -> int:
        """Length including trailing newline."""
        return sum(run.utf16_length() for run in self.runs) + 1


@dataclass
class SpecialElement:
    """A special element (hr, pagebreak, image, etc.)."""

    element_type: str
    attributes: dict[str, str] = field(default_factory=dict)

    def utf16_length(self) -> int:
        return 1


@dataclass
class TableCell:
    """A desugared table cell."""

    row: int
    col: int
    content: list[Paragraph | Table | SpecialElement] = field(default_factory=list)
    colspan: int = 1
    rowspan: int = 1
    style_class: str | None = None


@dataclass
class Table:
    """A desugared table."""

    rows: int
    cols: int
    cells: list[TableCell] = field(default_factory=list)


@dataclass
class Section:
    """A document section (body, header, footer, footnote)."""

    section_type: str  # "body", "header", "footer", "footnote"
    section_id: str = ""
    style_class: str = "_base"
    content: list[Paragraph | Table | SpecialElement] = field(default_factory=list)


@dataclass
class DesugaredDocument:
    """A fully desugared document ready for diffing."""

    document_id: str
    revision_id: str
    title: str
    sections: list[Section] = field(default_factory=list)


def desugar_document(
    xml_content: str, styles_content: str | None = None
) -> DesugaredDocument:
    """Desugar an ExtraDoc XML document.

    Args:
        xml_content: The document.xml content
        styles_content: Optional styles.xml content (for resolving class names)

    Returns:
        DesugaredDocument ready for diffing
    """
    # Parse styles if provided
    style_defs: dict[str, dict[str, str]] = {}
    if styles_content:
        style_defs = _parse_styles(styles_content)

    # Parse document
    root = ET.fromstring(xml_content)

    doc_id = root.get("id", "")
    revision_id = root.get("revision", "")

    # Get title from meta
    title = ""
    meta = root.find("meta")
    if meta is not None:
        title_elem = meta.find("title")
        if title_elem is not None and title_elem.text:
            title = title_elem.text

    doc = DesugaredDocument(
        document_id=doc_id,
        revision_id=revision_id,
        title=title,
    )

    # Process body
    body = root.find("body")
    if body is not None:
        section = _desugar_section(body, "body", style_defs)
        doc.sections.append(section)

    # Process tabs (multi-tab documents)
    for tab in root.findall("tab"):
        tab_body = tab.find("body")
        if tab_body is not None:
            tab_id = tab.get("id", "")
            section = _desugar_section(tab_body, "body", style_defs)
            section.section_id = tab_id
            doc.sections.append(section)

    # Process headers
    for header in root.findall("header"):
        section = _desugar_section(header, "header", style_defs)
        section.section_id = header.get("id", "")
        doc.sections.append(section)

    # Process footers
    for footer in root.findall("footer"):
        section = _desugar_section(footer, "footer", style_defs)
        section.section_id = footer.get("id", "")
        doc.sections.append(section)

    # Process footnotes
    for footnote in root.findall("footnote"):
        section = _desugar_section(footnote, "footnote", style_defs)
        section.section_id = footnote.get("id", "")
        doc.sections.append(section)

    return doc


def _parse_styles(styles_content: str) -> dict[str, dict[str, str]]:
    """Parse styles.xml into a dict of style_id -> properties."""
    style_defs: dict[str, dict[str, str]] = {}

    root = ET.fromstring(styles_content)
    for style in root.findall("style"):
        style_id = style.get("id", "")
        props = dict(style.attrib)
        del props["id"]
        style_defs[style_id] = props

    return style_defs


def _desugar_section(
    elem: Element,
    section_type: str,
    style_defs: dict[str, dict[str, str]],
) -> Section:
    """Desugar a section element."""
    section = Section(
        section_type=section_type,
        style_class=elem.get("class", "_base"),
    )

    # Process child elements
    for child in elem:
        _process_element(child, section.content, style_defs, None)

    return section


def _process_element(
    elem: Element,
    content: list[Paragraph | Table | SpecialElement],
    style_defs: dict[str, dict[str, str]],
    inherited_class: str | None,
) -> None:
    """Process a document element and add to content list."""
    tag = elem.tag

    # Style wrapper - apply class to children
    if tag == "style":
        wrapper_class = elem.get("class")
        for child in elem:
            _process_element(child, content, style_defs, wrapper_class)
        return

    # Headings (sugar for paragraphs with named styles)
    if tag in HEADING_STYLES:
        para = Paragraph(named_style=HEADING_STYLES[tag])
        para.style_class = elem.get("class") or inherited_class
        para.runs = _extract_text_runs(elem, style_defs)
        content.append(para)
        return

    # Regular paragraph
    if tag == "p":
        runs = _extract_text_runs(elem, style_defs)
        # If the paragraph consists solely of a column break, attach it to the preceding
        # paragraph so the section break lands inside a paragraph (Docs API requirement).
        if len(runs) == 1 and runs[0].styles.get("_special") == "columnbreak":
            if content and isinstance(content[-1], Paragraph):
                content[-1].runs.extend(runs)
            else:
                content.append(
                    SpecialElement(
                        element_type="columnbreak", attributes=dict(runs[0].styles)
                    )
                )
            return

        para = Paragraph(named_style="NORMAL_TEXT")
        para.style_class = elem.get("class") or inherited_class
        para.runs = runs
        content.append(para)
        return

    # List item (sugar for paragraph with bullet)
    if tag == "li":
        para = Paragraph(named_style="NORMAL_TEXT")
        para.bullet_type = elem.get("type", "bullet")
        para.bullet_level = int(elem.get("level", "0"))
        para.style_class = elem.get("class") or inherited_class
        para.runs = _extract_text_runs(elem, style_defs)
        content.append(para)
        return

    # Table
    if tag == "table":
        table = _desugar_table(elem, style_defs)
        content.append(table)
        return

    # TOC (table of contents)
    if tag == "toc":
        for child in elem:
            _process_element(child, content, style_defs, inherited_class)
        return

    # Special elements that might be standalone (not inside paragraphs)
    if tag in (
        "hr",
        "pagebreak",
        "image",
        "person",
        "footnoteref",
        "autotext",
        "date",
        "equation",
    ):
        # These should normally be inside paragraphs, but handle them if standalone
        special = SpecialElement(element_type=tag, attributes=dict(elem.attrib))
        content.append(special)
        return


def _desugar_table(elem: Element, style_defs: dict[str, dict[str, str]]) -> Table:
    """Desugar a table element."""
    rows = int(elem.get("rows", "0"))
    cols = int(elem.get("cols", "0"))

    table = Table(rows=rows, cols=cols)

    for row_idx, tr in enumerate(elem.findall("tr")):
        for col_idx, td in enumerate(tr.findall("td")):
            cell = TableCell(
                row=row_idx,
                col=col_idx,
                colspan=int(td.get("colspan", "1")),
                rowspan=int(td.get("rowspan", "1")),
                style_class=td.get("class"),
            )

            # Process cell content
            for child in td:
                _process_element(child, cell.content, style_defs, cell.style_class)

            # If cell has no structured content, check for text
            if not cell.content:
                text = _get_all_text(td)
                if text:
                    para = Paragraph()
                    para.runs = [TextRun(text=text)]
                    cell.content.append(para)

            table.cells.append(cell)
            # Each <td> is one physical cell - colspan is visual, not structural

    return table


def _extract_text_runs(
    elem: Element, style_defs: dict[str, dict[str, str]]
) -> list[TextRun]:
    """Extract text runs from an element, handling inline formatting."""
    runs: list[TextRun] = []
    _extract_runs_recursive(elem, runs, {}, style_defs)
    return runs


def _extract_runs_recursive(
    elem: Element,
    runs: list[TextRun],
    current_styles: dict[str, str],
    style_defs: dict[str, dict[str, str]],
) -> None:
    """Recursively extract text runs."""
    tag = elem.tag

    # Update styles based on tag
    elem_styles = current_styles.copy()

    if tag in INLINE_TAGS:
        elem_styles[INLINE_TAGS[tag]] = "1"
    elif tag == "a":
        href = elem.get("href", "")
        elem_styles["link"] = href
    elif tag == "span":
        # Span with class - merge in style properties
        class_name = elem.get("class")
        if class_name and class_name in style_defs:
            elem_styles.update(style_defs[class_name])

    # Add text content
    if elem.text:
        runs.append(TextRun(text=elem.text, styles=elem_styles.copy()))

    # Process children
    for child in elem:
        # Each child starts from the parent element's styles; do not share dicts
        child_base_styles = elem_styles.copy()
        child_tag = child.tag

        # Special inline elements
        if child_tag in (
            "hr",
            "pagebreak",
            "image",
            "person",
            "footnoteref",
            "autotext",
            "date",
            "equation",
            "columnbreak",
        ):
            # These are represented as special markers
            runs.append(
                TextRun(
                    text=f"\x00{child_tag}\x00",
                    styles={"_special": child_tag, **dict(child.attrib)},
                )
            )
        else:
            _extract_runs_recursive(child, runs, child_base_styles, style_defs)

        # Add tail text
        if child.tail:
            runs.append(TextRun(text=child.tail, styles=elem_styles.copy()))


def _get_all_text(elem: Element) -> str:
    """Get all text content from an element."""
    parts: list[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        parts.append(_get_all_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


# --- Convenience functions for diffing ---


def flatten_section(section: Section) -> list[tuple[str, Any, int, int]]:
    """Flatten a section into a list of (type, element, start_idx, end_idx) tuples.

    Args:
        section: The section to flatten

    Returns:
        List of tuples for each element with its index range
    """
    result: list[tuple[str, Any, int, int]] = []

    # Body starts at index 1, headers/footers/footnotes start at 0
    current_idx = 1 if section.section_type == "body" else 0

    for elem in section.content:
        start_idx = current_idx

        if isinstance(elem, Paragraph):
            end_idx = start_idx + elem.utf16_length()
            result.append(("paragraph", elem, start_idx, end_idx))
            current_idx = end_idx

        elif isinstance(elem, Table):
            # Table structure: table_start + rows + table_end
            table_start = current_idx
            current_idx += 1  # Table start marker

            for cell in elem.cells:
                current_idx += 1  # Row start (simplified)
                current_idx += 1  # Cell start

                for cell_elem in cell.content:
                    if isinstance(cell_elem, Paragraph):
                        current_idx += cell_elem.utf16_length()

            current_idx += 1  # Table end marker
            result.append(("table", elem, table_start, current_idx))

        elif isinstance(elem, SpecialElement):
            end_idx = start_idx + elem.utf16_length()
            result.append(("special", elem, start_idx, end_idx))
            current_idx = end_idx

    return result
