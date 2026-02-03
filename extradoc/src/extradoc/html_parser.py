"""Parse HTML back to document operations.

This module parses the HTML format and provides:
1. A structured representation of the HTML content
2. Index calculation for each element
3. Diff generation for batchUpdate requests
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Literal

from .indexer import utf16_len


@dataclass
class TextSpan:
    """A span of text with optional formatting."""

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    link_url: str | None = None
    superscript: bool = False
    subscript: bool = False

    def utf16_length(self) -> int:
        """Get length in UTF-16 code units."""
        return utf16_len(self.text)


@dataclass
class ParagraphContent:
    """Content of a paragraph."""

    spans: list[TextSpan] = field(default_factory=list)
    horizontal_rule: bool = False
    page_break: bool = False

    def text_content(self) -> str:
        """Get plain text content."""
        return "".join(span.text for span in self.spans)

    def utf16_length(self) -> int:
        """Get length in UTF-16 code units including newline."""
        length = sum(span.utf16_length() for span in self.spans)
        if self.horizontal_rule:
            length += 1
        if self.page_break:
            length += 1
        # Every paragraph ends with a newline
        length += 1
        return length


@dataclass
class HTMLParagraph:
    """A paragraph parsed from HTML."""

    tag: str  # p, h1-h6
    heading_id: str | None = None
    content: ParagraphContent = field(default_factory=ParagraphContent)
    is_list_item: bool = False
    list_nesting: int = 0

    def utf16_length(self) -> int:
        """Get length in UTF-16 code units."""
        return self.content.utf16_length()


@dataclass
class HTMLTableCell:
    """A table cell parsed from HTML."""

    paragraphs: list[HTMLParagraph] = field(default_factory=list)
    colspan: int = 1
    rowspan: int = 1

    def utf16_length(self) -> int:
        """Get length in UTF-16 code units."""
        # Cell marker = 1
        length = 1
        for para in self.paragraphs:
            length += para.utf16_length()
        return length


@dataclass
class HTMLTableRow:
    """A table row parsed from HTML."""

    cells: list[HTMLTableCell] = field(default_factory=list)

    def utf16_length(self) -> int:
        """Get length in UTF-16 code units."""
        # Row marker = 1
        length = 1
        for cell in self.cells:
            length += cell.utf16_length()
        return length


@dataclass
class HTMLTable:
    """A table parsed from HTML."""

    rows: list[HTMLTableRow] = field(default_factory=list)

    def utf16_length(self) -> int:
        """Get length in UTF-16 code units."""
        # Table start marker = 1, table end marker = 1
        length = 2
        for row in self.rows:
            length += row.utf16_length()
        return length


@dataclass
class HTMLDocument:
    """A document parsed from HTML."""

    title: str = ""
    elements: list[HTMLParagraph | HTMLTable] = field(default_factory=list)

    def calculate_indexes(self) -> list[tuple[Any, int, int]]:
        """Calculate start/end indexes for each element.

        Returns:
            List of (element, start_index, end_index) tuples
        """
        results: list[tuple[Any, int, int]] = []

        # Document always starts with section break at index 0-1
        current_index = 1

        for element in self.elements:
            start = current_index

            if isinstance(element, HTMLParagraph | HTMLTable):
                end = start + element.utf16_length()
                results.append((element, start, end))
                current_index = end

        return results


class DocumentHTMLParser(HTMLParser):
    """Parse document HTML into structured elements."""

    def __init__(self) -> None:
        super().__init__()
        self.document = HTMLDocument()
        self._current_paragraph: HTMLParagraph | None = None
        self._current_span: TextSpan | None = None
        self._tag_stack: list[str] = []
        self._formatting_stack: list[dict[str, Any]] = []

        # Table parsing state
        self._in_table = False
        self._current_table: HTMLTable | None = None
        self._current_row: HTMLTableRow | None = None
        self._current_cell: HTMLTableCell | None = None

        # List parsing state
        self._list_stack: list[str] = []  # Stack of 'ul' or 'ol'

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        self._tag_stack.append(tag)

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p"):
            self._start_paragraph(tag, attrs_dict)

        elif tag == "li":
            self._start_list_item()

        elif tag in ("ul", "ol"):
            self._list_stack.append(tag)

        elif tag == "table":
            self._in_table = True
            self._current_table = HTMLTable()

        elif tag == "tr":
            if self._current_table:
                self._current_row = HTMLTableRow()

        elif tag == "td" or tag == "th":
            if self._current_row:
                self._current_cell = HTMLTableCell()
                colspan = attrs_dict.get("colspan")
                rowspan = attrs_dict.get("rowspan")
                if colspan is not None:
                    self._current_cell.colspan = int(colspan)
                if rowspan is not None:
                    self._current_cell.rowspan = int(rowspan)

        elif tag == "strong" or tag == "b":
            self._push_formatting(bold=True)

        elif tag == "em" or tag == "i":
            self._push_formatting(italic=True)

        elif tag == "u":
            self._push_formatting(underline=True)

        elif tag == "s" or tag == "del":
            self._push_formatting(strikethrough=True)

        elif tag == "sup":
            self._push_formatting(superscript=True)

        elif tag == "sub":
            self._push_formatting(subscript=True)

        elif tag == "a":
            href = attrs_dict.get("href", "")
            self._push_formatting(link_url=href)

        elif tag == "hr":
            if self._current_paragraph:
                self._current_paragraph.content.horizontal_rule = True

        elif tag == "img":
            # Images are inline objects - count as 1 index
            pass

    def handle_endtag(self, tag: str) -> None:
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p"):
            self._end_paragraph()

        elif tag == "li":
            self._end_list_item()

        elif tag in ("ul", "ol"):
            if self._list_stack:
                self._list_stack.pop()

        elif tag == "table":
            if self._current_table:
                self.document.elements.append(self._current_table)
                self._current_table = None
            self._in_table = False

        elif tag == "tr":
            if self._current_row and self._current_table:
                self._current_table.rows.append(self._current_row)
                self._current_row = None

        elif tag == "td" or tag == "th":
            if self._current_cell and self._current_row:
                self._current_row.cells.append(self._current_cell)
                self._current_cell = None

        elif tag in ("strong", "b", "em", "i", "u", "s", "del", "sup", "sub", "a"):
            self._pop_formatting()

    def handle_data(self, data: str) -> None:
        # Skip whitespace-only data between elements
        if not data.strip() and not self._current_paragraph:
            return

        if self._current_paragraph:
            # Get current formatting
            formatting = self._get_current_formatting()
            span = TextSpan(text=data, **formatting)
            self._current_paragraph.content.spans.append(span)

    def handle_comment(self, data: str) -> None:
        if self._current_paragraph and "pagebreak" in data:
            self._current_paragraph.content.page_break = True

    def _start_paragraph(self, tag: str, attrs: dict[str, str | None]) -> None:
        heading_id = attrs.get("id")
        self._current_paragraph = HTMLParagraph(tag=tag, heading_id=heading_id)

    def _end_paragraph(self) -> None:
        if self._current_paragraph:
            if self._in_table and self._current_cell:
                self._current_cell.paragraphs.append(self._current_paragraph)
            else:
                self.document.elements.append(self._current_paragraph)
            self._current_paragraph = None

    def _start_list_item(self) -> None:
        nesting = len(self._list_stack) - 1
        self._current_paragraph = HTMLParagraph(
            tag="li", is_list_item=True, list_nesting=nesting
        )

    def _end_list_item(self) -> None:
        if self._current_paragraph and self._current_paragraph.is_list_item:
            self.document.elements.append(self._current_paragraph)
            self._current_paragraph = None

    def _push_formatting(self, **kwargs: Any) -> None:
        self._formatting_stack.append(kwargs)

    def _pop_formatting(self) -> None:
        if self._formatting_stack:
            self._formatting_stack.pop()

    def _get_current_formatting(self) -> dict[str, Any]:
        result = {
            "bold": False,
            "italic": False,
            "underline": False,
            "strikethrough": False,
            "superscript": False,
            "subscript": False,
            "link_url": None,
        }
        for fmt in self._formatting_stack:
            result.update(fmt)
        return result


def parse_html(html_content: str) -> HTMLDocument:
    """Parse HTML content into a structured document.

    Args:
        html_content: HTML string

    Returns:
        Parsed HTMLDocument
    """
    parser = DocumentHTMLParser()
    parser.feed(html_content)
    return parser.document


# --- Diff Generation ---


@dataclass
class TextChange:
    """Represents a text change between two documents."""

    change_type: Literal["insert", "delete", "replace"]
    start_index: int
    end_index: int  # For delete/replace
    old_text: str = ""
    new_text: str = ""


@dataclass
class StyleChange:
    """Represents a style change."""

    start_index: int
    end_index: int
    style_field: str  # 'bold', 'italic', etc.
    new_value: bool | str


def diff_documents(
    pristine_doc: HTMLDocument,
    edited_doc: HTMLDocument,
    _pristine_json: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate batchUpdate requests by diffing two HTML documents.

    Args:
        pristine_doc: Original document
        edited_doc: Edited document
        _pristine_json: Optional original JSON for ID resolution (not yet used)

    Returns:
        List of batchUpdate request objects
    """
    requests: list[dict[str, Any]] = []

    # Calculate indexes for both documents
    _pristine_indexes = pristine_doc.calculate_indexes()
    _edited_indexes = edited_doc.calculate_indexes()

    # TODO: Implement diff algorithm
    # Simple diff: compare paragraph by paragraph
    # For a production implementation, this would use proper diff algorithms

    # Build requests in reverse order (highest index first)
    # This ensures index stability during batch operations

    return requests


def generate_insert_text_request(
    index: int, text: str, segment_id: str | None = None, tab_id: str | None = None
) -> dict[str, Any]:
    """Generate an InsertTextRequest.

    Args:
        index: Where to insert
        text: Text to insert
        segment_id: Optional segment ID (for headers/footers)
        tab_id: Optional tab ID

    Returns:
        InsertTextRequest dict
    """
    location: dict[str, Any] = {"index": index}
    if segment_id:
        location["segmentId"] = segment_id
    if tab_id:
        location["tabId"] = tab_id

    return {"insertText": {"location": location, "text": text}}


def generate_delete_content_request(
    start_index: int,
    end_index: int,
    segment_id: str | None = None,
    tab_id: str | None = None,
) -> dict[str, Any]:
    """Generate a DeleteContentRangeRequest.

    Args:
        start_index: Start of range (inclusive)
        end_index: End of range (exclusive)
        segment_id: Optional segment ID
        tab_id: Optional tab ID

    Returns:
        DeleteContentRangeRequest dict
    """
    range_obj: dict[str, Any] = {"startIndex": start_index, "endIndex": end_index}
    if segment_id:
        range_obj["segmentId"] = segment_id
    if tab_id:
        range_obj["tabId"] = tab_id

    return {"deleteContentRange": {"range": range_obj}}


def generate_update_text_style_request(
    start_index: int,
    end_index: int,
    text_style: dict[str, Any],
    fields: str,
    segment_id: str | None = None,
    tab_id: str | None = None,
) -> dict[str, Any]:
    """Generate an UpdateTextStyleRequest.

    Args:
        start_index: Start of range
        end_index: End of range
        text_style: Style to apply
        fields: Field mask (e.g., "bold", "italic")
        segment_id: Optional segment ID
        tab_id: Optional tab ID

    Returns:
        UpdateTextStyleRequest dict
    """
    range_obj: dict[str, Any] = {"startIndex": start_index, "endIndex": end_index}
    if segment_id:
        range_obj["segmentId"] = segment_id
    if tab_id:
        range_obj["tabId"] = tab_id

    return {
        "updateTextStyle": {
            "range": range_obj,
            "textStyle": text_style,
            "fields": fields,
        }
    }
