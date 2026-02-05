"""Index tracking for Google Docs.

Google Docs uses UTF-16 code unit based indexing. This module provides
utilities to calculate and verify indexes for document elements.

Key indexing rules:
1. Indexes are zero-based UTF-16 code unit offsets
2. The document body starts at index 0
3. The first element (usually sectionBreak) has endIndex=1 with implicit startIndex=0
4. Text content is counted by UTF-16 code units (most chars = 1, surrogate pairs = 2)
5. Special elements (horizontalRule, pageBreak, etc.) each consume 1 index
6. Container elements (table, tableRow, tableCell) each add 1 index before content
7. Paragraphs end with newline which is included in the paragraph's index range
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, cast


def utf16_len(text: str) -> int:
    """Calculate the length of a string in UTF-16 code units.

    Python strings are UTF-32 internally, but Google Docs uses UTF-16.
    Characters outside the BMP (code points > 0xFFFF) use surrogate pairs
    in UTF-16, consuming 2 code units.

    Args:
        text: The string to measure

    Returns:
        Length in UTF-16 code units
    """
    length = 0
    for char in text:
        code_point = ord(char)
        if code_point > 0xFFFF:
            # Surrogate pair needed
            length += 2
        else:
            length += 1
    return length


@dataclass
class IndexMismatch:
    """Represents an index mismatch between expected and actual values."""

    path: str  # JSON path to the element
    element_type: str  # Type of element (e.g., "paragraph", "textRun")
    field: str  # "startIndex" or "endIndex"
    expected: int
    actual: int
    context: str = ""  # Additional context (e.g., text content)

    def __str__(self) -> str:
        msg = f"{self.path}: {self.element_type}.{self.field} expected={self.expected}, actual={self.actual}"
        if self.context:
            msg += f" ({self.context})"
        return msg


@dataclass
class IndexValidationResult:
    """Result of validating indexes in a document."""

    document_id: str
    is_valid: bool
    mismatches: list[IndexMismatch] = field(default_factory=list)
    total_elements_checked: int = 0

    def __str__(self) -> str:
        if self.is_valid:
            return f"Document {self.document_id}: All {self.total_elements_checked} elements have correct indexes"
        return f"Document {self.document_id}: {len(self.mismatches)} mismatches found in {self.total_elements_checked} elements"


class IndexCalculator:
    """Calculates expected indexes for Google Docs elements.

    This class traverses a document structure and calculates what the
    indexes should be based on the content, then compares with actual
    indexes from the API.
    """

    def __init__(self, document: dict[str, Any]) -> None:
        """Initialize with a document from the Google Docs API.

        Args:
            document: The raw document JSON from documents.get()
        """
        self._document = document
        self._mismatches: list[IndexMismatch] = []
        self._elements_checked = 0

    def validate(self) -> IndexValidationResult:
        """Validate all indexes in the document.

        Returns:
            IndexValidationResult with any mismatches found
        """
        self._mismatches = []
        self._elements_checked = 0

        document_id = self._document.get("documentId", "unknown")

        # Process body content
        body = self._document.get("body", {})
        content = body.get("content", [])

        # Calculate expected indexes starting from 0
        expected_index = 0
        for i, element in enumerate(content):
            path = f"body.content[{i}]"
            expected_index = self._validate_structural_element(
                element, expected_index, path
            )

        # Process headers (each has its own index space starting at 0)
        headers = self._document.get("headers", {})
        for header_id, header in headers.items():
            self._validate_section_content(
                header.get("content", []), f"headers[{header_id}]"
            )

        # Process footers (each has its own index space starting at 0)
        footers = self._document.get("footers", {})
        for footer_id, footer in footers.items():
            self._validate_section_content(
                footer.get("content", []), f"footers[{footer_id}]"
            )

        # Process footnotes (each has its own index space starting at 0)
        footnotes = self._document.get("footnotes", {})
        for footnote_id, footnote in footnotes.items():
            self._validate_section_content(
                footnote.get("content", []), f"footnotes[{footnote_id}]"
            )

        return IndexValidationResult(
            document_id=document_id,
            is_valid=len(self._mismatches) == 0,
            mismatches=self._mismatches,
            total_elements_checked=self._elements_checked,
        )

    def _validate_section_content(
        self, content: list[dict[str, Any]], path_prefix: str
    ) -> None:
        """Validate indexes for a section (header, footer, footnote).

        Each section has its own index space starting at 0.

        Args:
            content: List of structural elements
            path_prefix: Path prefix for error reporting
        """
        expected_index = 0
        for i, element in enumerate(content):
            path = f"{path_prefix}.content[{i}]"
            expected_index = self._validate_structural_element(
                element, expected_index, path
            )

    def _validate_structural_element(
        self, element: dict[str, Any], expected_start: int, path: str
    ) -> int:
        """Validate a structural element and return the expected end index.

        Args:
            element: The structural element dict
            expected_start: The expected start index
            path: JSON path for error reporting

        Returns:
            The expected end index (which is the next element's start)
        """
        self._elements_checked += 1

        # Check start index (first element may not have startIndex)
        actual_start = element.get("startIndex")
        if actual_start is not None and actual_start != expected_start:
            self._mismatches.append(
                IndexMismatch(
                    path=path,
                    element_type="structuralElement",
                    field="startIndex",
                    expected=expected_start,
                    actual=actual_start,
                )
            )

        actual_end = element.get("endIndex")

        # Calculate expected end based on content type
        if "sectionBreak" in element:
            # Section break consumes 1 index
            expected_end = expected_start + 1
            self._validate_index(
                path, "sectionBreak", "endIndex", expected_end, actual_end
            )
            return expected_end

        elif "paragraph" in element:
            expected_end = self._calculate_paragraph_end(
                element["paragraph"], expected_start, path
            )
            self._validate_index(
                path, "paragraph", "endIndex", expected_end, actual_end
            )
            return expected_end

        elif "table" in element:
            expected_end = self._calculate_table_end(
                element["table"], expected_start, path
            )
            self._validate_index(path, "table", "endIndex", expected_end, actual_end)
            return expected_end

        elif "tableOfContents" in element:
            expected_end = self._calculate_toc_end(
                element["tableOfContents"], expected_start, path
            )
            self._validate_index(
                path, "tableOfContents", "endIndex", expected_end, actual_end
            )
            return expected_end

        # Unknown element type - use actual end
        return actual_end if actual_end else expected_start

    def _calculate_paragraph_end(
        self, paragraph: dict[str, Any], start: int, path: str
    ) -> int:
        """Calculate the end index of a paragraph.

        Args:
            paragraph: The paragraph dict
            start: The paragraph's start index
            path: JSON path for error reporting

        Returns:
            The expected end index
        """
        elements = paragraph.get("elements", [])
        current_index = start

        for i, elem in enumerate(elements):
            elem_path = f"{path}.paragraph.elements[{i}]"
            current_index = self._validate_paragraph_element(
                elem, current_index, elem_path
            )

        return current_index

    def _validate_paragraph_element(
        self, element: dict[str, Any], expected_start: int, path: str
    ) -> int:
        """Validate a paragraph element and return expected end index.

        Args:
            element: The paragraph element dict
            expected_start: The expected start index
            path: JSON path for error reporting

        Returns:
            The expected end index
        """
        self._elements_checked += 1

        actual_start = element.get("startIndex")
        actual_end = element.get("endIndex")

        # Validate start index
        if actual_start is not None and actual_start != expected_start:
            elem_type = self._get_paragraph_element_type(element)
            self._mismatches.append(
                IndexMismatch(
                    path=path,
                    element_type=elem_type,
                    field="startIndex",
                    expected=expected_start,
                    actual=actual_start,
                )
            )

        # Calculate expected end based on element type
        if "textRun" in element:
            content = element["textRun"].get("content", "")
            expected_end = expected_start + utf16_len(content)
            context = repr(content[:50]) if len(content) > 50 else repr(content)
            self._validate_index(
                path, "textRun", "endIndex", expected_end, actual_end, context
            )
            return expected_end

        elif "horizontalRule" in element:
            # Horizontal rule consumes 1 index
            expected_end = expected_start + 1
            self._validate_index(
                path, "horizontalRule", "endIndex", expected_end, actual_end
            )
            return expected_end

        elif "pageBreak" in element:
            # Page break consumes 1 index
            expected_end = expected_start + 1
            self._validate_index(
                path, "pageBreak", "endIndex", expected_end, actual_end
            )
            return expected_end

        elif "columnBreak" in element:
            # Column break consumes 1 index
            expected_end = expected_start + 1
            self._validate_index(
                path, "columnBreak", "endIndex", expected_end, actual_end
            )
            return expected_end

        elif "footnoteReference" in element:
            # Footnote reference consumes 1 index
            expected_end = expected_start + 1
            self._validate_index(
                path, "footnoteReference", "endIndex", expected_end, actual_end
            )
            return expected_end

        elif "inlineObjectElement" in element:
            # Inline object consumes 1 index
            expected_end = expected_start + 1
            self._validate_index(
                path, "inlineObjectElement", "endIndex", expected_end, actual_end
            )
            return expected_end

        elif "autoText" in element:
            # Auto text - need to check actual content length
            # For now use actual end since content varies
            return actual_end if actual_end else expected_start + 1

        elif "person" in element:
            # Person chip - typically consumes 1 index
            expected_end = expected_start + 1
            self._validate_index(path, "person", "endIndex", expected_end, actual_end)
            return expected_end

        elif "richLink" in element:
            # Rich link - typically consumes 1 index
            expected_end = expected_start + 1
            self._validate_index(path, "richLink", "endIndex", expected_end, actual_end)
            return expected_end

        elif "dateElement" in element:
            # Date element - typically consumes 1 index
            expected_end = expected_start + 1
            self._validate_index(
                path, "dateElement", "endIndex", expected_end, actual_end
            )
            return expected_end

        elif "equation" in element:
            # Equation - need to determine actual size
            # Use actual end for now
            return actual_end if actual_end else expected_start + 1

        # Unknown element type
        return actual_end if actual_end else expected_start

    def _calculate_table_end(self, table: dict[str, Any], start: int, path: str) -> int:
        """Calculate the end index of a table.

        Table structure adds index overhead:
        - Table start: +1 index (start marker)
        - Each row start: +1 index
        - Each cell start: +1 index
        - Table end: +1 index (end marker)

        Args:
            table: The table dict
            start: The table's start index
            path: JSON path for error reporting

        Returns:
            The expected end index
        """
        # Table element itself starts at 'start', content starts at start+1
        current_index = start + 1  # Table start marker

        table_rows = table.get("tableRows", [])
        for row_idx, row in enumerate(table_rows):
            row_path = f"{path}.table.tableRows[{row_idx}]"
            current_index = self._validate_table_row(row, current_index, row_path)

        # Table has an end marker that consumes 1 additional index
        return current_index + 1

    def _validate_table_row(
        self, row: dict[str, Any], expected_start: int, path: str
    ) -> int:
        """Validate a table row and return expected end index.

        Args:
            row: The table row dict
            expected_start: The expected start index
            path: JSON path for error reporting

        Returns:
            The expected end index
        """
        self._elements_checked += 1

        actual_start = row.get("startIndex")
        actual_end = row.get("endIndex")

        if actual_start is not None and actual_start != expected_start:
            self._mismatches.append(
                IndexMismatch(
                    path=path,
                    element_type="tableRow",
                    field="startIndex",
                    expected=expected_start,
                    actual=actual_start,
                )
            )

        # Row content starts after the row marker (+1)
        current_index = expected_start + 1

        table_cells = row.get("tableCells", [])
        for cell_idx, cell in enumerate(table_cells):
            cell_path = f"{path}.tableCells[{cell_idx}]"
            current_index = self._validate_table_cell(cell, current_index, cell_path)

        expected_end = current_index
        self._validate_index(path, "tableRow", "endIndex", expected_end, actual_end)

        return expected_end

    def _validate_table_cell(
        self, cell: dict[str, Any], expected_start: int, path: str
    ) -> int:
        """Validate a table cell and return expected end index.

        Args:
            cell: The table cell dict
            expected_start: The expected start index
            path: JSON path for error reporting

        Returns:
            The expected end index
        """
        self._elements_checked += 1

        actual_start = cell.get("startIndex")
        actual_end = cell.get("endIndex")

        if actual_start is not None and actual_start != expected_start:
            self._mismatches.append(
                IndexMismatch(
                    path=path,
                    element_type="tableCell",
                    field="startIndex",
                    expected=expected_start,
                    actual=actual_start,
                )
            )

        # Cell content starts after the cell marker (+1)
        current_index = expected_start + 1

        # Process cell content (array of StructuralElements)
        content = cell.get("content", [])
        for i, element in enumerate(content):
            elem_path = f"{path}.content[{i}]"
            current_index = self._validate_structural_element(
                element, current_index, elem_path
            )

        expected_end = current_index
        self._validate_index(path, "tableCell", "endIndex", expected_end, actual_end)

        return expected_end

    def _calculate_toc_end(self, toc: dict[str, Any], start: int, path: str) -> int:
        """Calculate the end index of a table of contents.

        Args:
            toc: The table of contents dict
            start: The TOC's start index
            path: JSON path for error reporting

        Returns:
            The expected end index
        """
        # TOC has content array similar to body
        current_index = start
        content = toc.get("content", [])

        for i, element in enumerate(content):
            elem_path = f"{path}.tableOfContents.content[{i}]"
            current_index = self._validate_structural_element(
                element, current_index, elem_path
            )

        return current_index

    def _validate_index(
        self,
        path: str,
        element_type: str,
        field: str,
        expected: int,
        actual: int | None,
        context: str = "",
    ) -> None:
        """Record a mismatch if expected != actual.

        Args:
            path: JSON path to the element
            element_type: Type of element
            field: Field name ("startIndex" or "endIndex")
            expected: Expected value
            actual: Actual value from API (may be None)
            context: Additional context for error message
        """
        if actual is not None and actual != expected:
            self._mismatches.append(
                IndexMismatch(
                    path=path,
                    element_type=element_type,
                    field=field,
                    expected=expected,
                    actual=actual,
                    context=context,
                )
            )

    def _get_paragraph_element_type(self, element: dict[str, Any]) -> str:
        """Get the type name of a paragraph element."""
        for key in [
            "textRun",
            "horizontalRule",
            "pageBreak",
            "columnBreak",
            "footnoteReference",
            "inlineObjectElement",
            "autoText",
            "person",
            "richLink",
            "dateElement",
            "equation",
        ]:
            if key in element:
                return key
        return "unknown"


def validate_document(document: dict[str, Any]) -> IndexValidationResult:
    """Validate all indexes in a Google Docs document.

    Args:
        document: The raw document JSON from documents.get()

    Returns:
        IndexValidationResult with any mismatches found
    """
    calculator = IndexCalculator(document)
    return calculator.validate()


def calculate_table_indexes(
    sections: list[Any],
) -> dict[str, int]:
    """Calculate start indexes for all tables in the document.

    Walks through the desugared document sections and calculates where
    each table starts based on cumulative content lengths.

    Args:
        sections: List of Section objects from desugar_document()

    Returns:
        Dict mapping table position (section_type:index) to startIndex
        e.g., {"body:0": 2, "body:1": 50} for 1st and 2nd tables in body
    """
    # Import here to avoid circular dependency
    from extradoc.desugar import (
        Paragraph,
        SpecialElement,
        Table,
    )

    table_indexes: dict[str, int] = {}

    for section in sections:
        section_type = section.section_type
        # Each section has its own index space starting at 0
        # Body starts at 1 (after initial sectionBreak)
        current_index = 1 if section_type == "body" else 0

        table_count = 0
        for elem in section.content:
            if isinstance(elem, Paragraph | SpecialElement):
                current_index += elem.utf16_length()
            elif isinstance(elem, Table):
                # Record this table's start index
                key = f"{section_type}:{table_count}"
                table_indexes[key] = current_index

                # Calculate table length and advance
                current_index += _calculate_table_length(elem)
                table_count += 1

    return table_indexes


def _calculate_table_length(table: Any) -> int:
    """Calculate the UTF-16 length of a table including structure markers.

    Table structure:
    - 1 index for table start marker
    - For each row: 1 index for row marker
    - For each cell: 1 index for cell marker + cell content length
    - 1 index for table end marker
    """
    from extradoc.desugar import (
        Paragraph,
        SpecialElement,
        Table,
    )

    length = 1  # Table start marker

    # Build cell lookup
    cell_map = {(cell.row, cell.col): cell for cell in table.cells}

    for row in range(table.rows):
        length += 1  # Row marker
        for col in range(table.cols):
            length += 1  # Cell marker
            cell = cell_map.get((row, col))
            if cell and cell.content:
                for item in cell.content:
                    if isinstance(item, Paragraph | SpecialElement):
                        length += item.utf16_length()
                    elif isinstance(item, Table):
                        length += _calculate_table_length(item)
            else:
                # Empty cell has default paragraph with newline
                length += 1

    length += 1  # Table end marker
    return length


def strip_indexes(document: dict[str, Any]) -> dict[str, Any]:
    """Create a copy of the document with all indexes removed.

    This is useful for creating a canonical representation of document
    content that can be compared without index values.

    Args:
        document: The raw document JSON

    Returns:
        A deep copy with startIndex and endIndex fields removed
    """

    def remove_indexes(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {
                k: remove_indexes(v)
                for k, v in obj.items()
                if k not in ("startIndex", "endIndex")
            }
        elif isinstance(obj, list):
            return [remove_indexes(item) for item in obj]
        else:
            return obj

    return cast("dict[str, Any]", remove_indexes(copy.deepcopy(document)))
