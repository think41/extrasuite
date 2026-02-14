"""Validation logic for the mock Google Docs API."""

from __future__ import annotations

from typing import Any

from extradoc.mock.exceptions import ValidationError
from extradoc.mock.navigation import get_segment


class DocumentStructureTracker:
    """Track structural elements in a document for validation.

    This class scans the document and maintains indexes of all structural
    elements (tables, TableOfContents, equations, section breaks) to enable
    validation of operations that might violate structural constraints.
    """

    def __init__(self, document: dict[str, Any]) -> None:
        self.tables: list[tuple[int, int]] = []
        # For each table, store the cell content ranges (start, end) for validation
        self.table_cell_ranges: list[list[tuple[int, int]]] = []
        self.table_of_contents: list[tuple[int, int]] = []
        self.equations: list[tuple[int, int]] = []
        self.section_breaks: list[int] = []
        self._scan_document(document)

    def _scan_document(self, document: dict[str, Any]) -> None:
        for tab in document.get("tabs", []):
            document_tab = tab.get("documentTab", {})
            body = document_tab.get("body", {})
            self._scan_content(body.get("content", []))

    def _scan_content(self, content: list[dict[str, Any]]) -> None:
        for element in content:
            start = element.get("startIndex", 0)
            end = element.get("endIndex", 0)

            if "table" in element:
                self.tables.append((start, end))
                cell_ranges: list[tuple[int, int]] = []
                for row in element["table"].get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        cell_content = cell.get("content", [])
                        if cell_content:
                            c_start = cell_content[0].get("startIndex", 0)
                            c_end = cell_content[-1].get("endIndex", 0)
                            cell_ranges.append((c_start, c_end))
                self.table_cell_ranges.append(cell_ranges)
            elif "tableOfContents" in element:
                self.table_of_contents.append((start, end))
                toc = element["tableOfContents"]
                self._scan_content(toc.get("content", []))
            elif "sectionBreak" in element:
                self.section_breaks.append(start)
            elif "paragraph" in element:
                para = element["paragraph"]
                for para_elem in para.get("elements", []):
                    if "equation" in para_elem:
                        eq_start = para_elem.get("startIndex", 0)
                        eq_end = para_elem.get("endIndex", 0)
                        self.equations.append((eq_start, eq_end))

    def validate_delete_range(self, start_index: int, end_index: int) -> None:
        """Validate that deletion doesn't violate structural rules."""
        # Validate tables
        for i, (table_start, table_end) in enumerate(self.tables):
            if start_index > table_start and end_index < table_end:
                # Range is inside the table — only valid if it falls entirely
                # within a single cell's content range (not structural overhead)
                cell_ranges = (
                    self.table_cell_ranges[i] if i < len(self.table_cell_ranges) else []
                )
                in_cell = any(
                    c_start <= start_index and end_index <= c_end
                    for c_start, c_end in cell_ranges
                )
                if in_cell:
                    continue
                raise ValidationError(
                    f"Invalid deletion range. Cannot delete the requested range. "
                    f"Range {start_index}-{end_index} targets table structural "
                    f"elements, not cell content."
                )
            if self._is_partial_overlap(start_index, end_index, table_start, table_end):
                raise ValidationError(
                    f"Cannot partially delete table at indices {table_start}-{table_end}. "
                    f"Deletion range {start_index}-{end_index} only partially overlaps. "
                    "Delete the entire table or content within cells only."
                )
            if table_start > 1 and start_index < table_start == end_index:
                raise ValidationError(
                    f"Cannot delete newline before table without deleting the table. "
                    f"Table at index {table_start}, deletion range {start_index}-{end_index} "
                    "deletes the preceding newline but not the table."
                )

        # Validate TableOfContents
        for toc_start, toc_end in self.table_of_contents:
            if self._is_partial_overlap(start_index, end_index, toc_start, toc_end):
                raise ValidationError(
                    f"Cannot partially delete table of contents at indices {toc_start}-{toc_end}. "
                    f"Deletion range {start_index}-{end_index} only partially overlaps. "
                    "Delete the entire table of contents or nothing."
                )
            if toc_start > 1 and start_index < toc_start == end_index:
                raise ValidationError(
                    f"Cannot delete newline before table of contents without deleting it. "
                    f"TOC at index {toc_start}, deletion range {start_index}-{end_index} "
                    "deletes the preceding newline but not the TOC."
                )

        # Validate Equations
        for eq_start, eq_end in self.equations:
            if self._is_partial_overlap(start_index, end_index, eq_start, eq_end):
                raise ValidationError(
                    f"Cannot partially delete equation at indices {eq_start}-{eq_end}. "
                    f"Deletion range {start_index}-{end_index} only partially overlaps. "
                    "Delete the entire equation or nothing."
                )

        # Validate SectionBreaks
        for sb_index in self.section_breaks:
            if sb_index > 1 and start_index < sb_index == end_index:
                raise ValidationError(
                    f"Cannot delete newline before section break without deleting the break. "
                    f"Section break at index {sb_index}, deletion range {start_index}-{end_index} "
                    "deletes the preceding newline but not the break."
                )

    def _is_partial_overlap(
        self, del_start: int, del_end: int, elem_start: int, elem_end: int
    ) -> bool:
        has_overlap = del_start < elem_end and del_end > elem_start
        is_complete = del_start <= elem_start and del_end >= elem_end
        return has_overlap and not is_complete


def validate_no_surrogate_pair_split(
    segment: dict[str, Any], start_index: int, end_index: int
) -> None:
    """Validate that deletion doesn't split a surrogate pair."""
    for element in segment.get("content", []):
        _check_surrogate_pairs_in_element(element, start_index, end_index)


def _check_surrogate_pairs_in_element(
    element: dict[str, Any], start_index: int, end_index: int
) -> None:
    if "paragraph" in element:
        for para_elem in element["paragraph"].get("elements", []):
            if "textRun" in para_elem:
                text = para_elem["textRun"].get("content", "")
                elem_start = para_elem.get("startIndex", 0)
                _validate_text_surrogate_pairs(text, elem_start, start_index, end_index)
    elif "table" in element:
        table = element["table"]
        for row in table.get("tableRows", []):
            for cell in row.get("tableCells", []):
                for cell_elem in cell.get("content", []):
                    _check_surrogate_pairs_in_element(cell_elem, start_index, end_index)
    elif "tableOfContents" in element:
        toc = element["tableOfContents"]
        for toc_elem in toc.get("content", []):
            _check_surrogate_pairs_in_element(toc_elem, start_index, end_index)


def _validate_text_surrogate_pairs(
    text: str, elem_start: int, del_start: int, del_end: int
) -> None:
    current_index = elem_start
    for char in text:
        char_code = ord(char)
        if char_code >= 0x10000:
            pair_start = current_index
            pair_end = current_index + 2
            if pair_start < del_start < pair_end or pair_start < del_end < pair_end:
                raise ValidationError(
                    f"Cannot delete one code unit of a surrogate pair. "
                    f"Character '{char}' (U+{char_code:04X}) at index {pair_start} "
                    f"spans indices {pair_start}-{pair_end}. Deletion range "
                    f"{del_start}-{del_end} would split it."
                )
            current_index += 2
        else:
            current_index += 1


def validate_no_table_cell_final_newline_deletion(
    tab: dict[str, Any],
    segment_id: str | None,
    start_index: int,
    end_index: int,
) -> None:
    """Validate that deletion doesn't include final newline from table cells."""
    if segment_id is not None:
        return

    segment, _ = get_segment(tab, segment_id)

    for element in segment.get("content", []):
        if "table" in element:
            table_start = element.get("startIndex", 0)
            table_end = element.get("endIndex", 0)

            if start_index <= table_start and end_index >= table_end:
                continue

            table = element["table"]
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    cell_content = cell.get("content", [])
                    if cell_content:
                        cell_end = cell_content[-1].get("endIndex", 0)
                        cell_start = cell_content[0].get("startIndex", 0)

                        if (
                            start_index < cell_end
                            and end_index > cell_start
                            and end_index >= cell_end
                        ):
                            raise ValidationError(
                                f"Cannot delete the final newline of a table cell. "
                                f"Cell at indices {cell_start}-{cell_end}, "
                                f"deletion range {start_index}-{end_index} includes "
                                f"final newline at index {cell_end - 1}"
                            )
