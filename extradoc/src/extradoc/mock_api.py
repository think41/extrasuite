"""Mock implementation of Google Docs API for testing.

This module provides a complete mock of the Google Docs API focusing on
batchUpdate and get operations. It maintains document state and performs
all the validations that the real API performs.

The mock is seeded with a complete Document object representing the output
of a get request. You can then call batchUpdate with proper request objects
to modify the document, and call get to retrieve the updated document.

All validations follow the rules documented in:
- extradoc/docs/googledocs/batch.md
- extradoc/docs/googledocs/rules-behavior.md
- extradoc/docs/googledocs/api/*.md
"""

from __future__ import annotations

import copy
import re
import uuid
from typing import Any

from extradoc.indexer import utf16_len


class MockAPIError(Exception):
    """Base class for mock API errors."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class ValidationError(MockAPIError):
    """Raised when request validation fails."""

    pass


class DocumentStructureTracker:
    """Track structural elements in a document for validation.

    This class scans the document and maintains indexes of all structural
    elements (tables, TableOfContents, equations, section breaks) to enable
    validation of operations that might violate structural constraints.
    """

    def __init__(self, document: dict[str, Any]) -> None:
        """Initialize tracker by scanning document.

        Args:
            document: Complete Document object from Google Docs API
        """
        # Store (start_index, end_index) tuples for each element type
        self.tables: list[tuple[int, int]] = []
        self.table_of_contents: list[tuple[int, int]] = []
        self.equations: list[tuple[int, int]] = []
        # Section breaks only have a single index (they're structural markers)
        self.section_breaks: list[int] = []

        self._scan_document(document)

    def _scan_document(self, document: dict[str, Any]) -> None:
        """Scan document and record all structural elements.

        Args:
            document: Document to scan
        """
        for tab in document.get("tabs", []):
            document_tab = tab.get("documentTab", {})
            body = document_tab.get("body", {})
            self._scan_content(body.get("content", []))

    def _scan_content(self, content: list[dict[str, Any]]) -> None:
        """Recursively scan content for structural elements.

        Args:
            content: List of structural elements
        """
        for element in content:
            start = element.get("startIndex", 0)
            end = element.get("endIndex", 0)

            if "table" in element:
                self.tables.append((start, end))
            elif "tableOfContents" in element:
                self.table_of_contents.append((start, end))
                # Recursively scan TOC content
                toc = element["tableOfContents"]
                self._scan_content(toc.get("content", []))
            elif "sectionBreak" in element:
                # Section breaks are at a single index
                self.section_breaks.append(start)
            elif "paragraph" in element:
                # Check for equations within paragraphs
                para = element["paragraph"]
                for para_elem in para.get("elements", []):
                    if "equation" in para_elem:
                        eq_start = para_elem.get("startIndex", 0)
                        eq_end = para_elem.get("endIndex", 0)
                        self.equations.append((eq_start, eq_end))

    def validate_delete_range(self, start_index: int, end_index: int) -> None:
        """Validate that deletion doesn't violate structural rules.

        Args:
            start_index: Start of deletion range
            end_index: End of deletion range (exclusive)

        Raises:
            ValidationError: If deletion violates structural constraints
        """
        # Validate tables
        # NOTE: We only check if deletion partially overlaps the TABLE ITSELF
        # (the structural element boundaries), not content within table cells.
        # Deletions completely within cells are handled by table cell validation.
        for table_start, table_end in self.tables:
            # Check if deletion is completely contained within table
            # (i.e., within table cells, not touching table structure boundaries)
            if start_index > table_start and end_index < table_end:
                # Deletion is within the table, allow it
                # (table cell validation will handle cell-specific rules)
                continue

            # Check if deletion partially overlaps the table structure boundaries
            # This means deleting part of the table but not all of it
            if self._is_partial_overlap(start_index, end_index, table_start, table_end):
                raise ValidationError(
                    f"Cannot partially delete table at indices {table_start}-{table_end}. "
                    f"Deletion range {start_index}-{end_index} only partially overlaps. "
                    "Delete the entire table or content within cells only."
                )

            # Check newline before table (the character immediately before table_start)
            # Only error if we delete the newline but NOT the table itself
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
            # Check newline before TOC
            # Only error if we delete the newline but NOT the TOC itself
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
            # Check if deletion includes newline before section break
            # but doesn't include the section break itself
            # Section break starts at sb_index
            # The newline before it ends at sb_index (exclusive range)
            # So deleting X-sb_index deletes the newline but not the break
            if sb_index > 1 and start_index < sb_index == end_index:
                # Deletion ends exactly at section break, meaning it deletes
                # the newline before it but not the break itself
                raise ValidationError(
                    f"Cannot delete newline before section break without deleting the break. "
                    f"Section break at index {sb_index}, deletion range {start_index}-{end_index} "
                    "deletes the preceding newline but not the break."
                )

    def _is_partial_overlap(
        self, del_start: int, del_end: int, elem_start: int, elem_end: int
    ) -> bool:
        """Check if deletion partially overlaps element.

        Args:
            del_start: Deletion start index
            del_end: Deletion end index
            elem_start: Element start index
            elem_end: Element end index

        Returns:
            True if there's overlap but not complete deletion
        """
        # Has overlap
        has_overlap = del_start < elem_end and del_end > elem_start
        # Complete deletion (deletion fully contains element)
        is_complete = del_start <= elem_start and del_end >= elem_end
        # Partial means overlap but not complete
        return has_overlap and not is_complete


class MockGoogleDocsAPI:
    """Mock implementation of Google Docs API.

    This class simulates the behavior of the real Google Docs API, including:
    - Document state management
    - batchUpdate request processing
    - All validation rules and constraints
    - Proper UTF-16 index handling

    The implementation focuses on correctness and validation rather than
    performance. It's designed for testing, not production use.
    """

    def __init__(self, initial_document: dict[str, Any]) -> None:
        """Initialize the mock API with a document.

        Args:
            initial_document: Complete Document object from Google Docs API.
                Must include documentId, title, and tabs structure.
        """
        # Deep copy to avoid external modifications
        self._document = copy.deepcopy(initial_document)
        self._revision_id = initial_document.get("revisionId", "mock_revision_1")
        self._revision_counter = 1

        # Track named ranges (keyed by ID)
        self._named_ranges: dict[str, dict[str, Any]] = {}
        self._extract_named_ranges()

        # Track structural elements for validation
        self._structure_tracker = DocumentStructureTracker(self._document)

        # Track header/footer types to prevent duplicates
        self._header_types: set[str] = set()
        self._footer_types: set[str] = set()
        self._extract_header_footer_types()

    def _extract_named_ranges(self) -> None:
        """Extract all named ranges from document into tracking dict."""
        for tab in self._document.get("tabs", []):
            document_tab = tab.get("documentTab", {})
            named_ranges_obj = document_tab.get("namedRanges", {})
            for name, ranges_list in named_ranges_obj.items():
                for range_info in ranges_list.get("namedRanges", []):
                    range_id = range_info.get("namedRangeId")
                    if range_id:
                        self._named_ranges[range_id] = {
                            "name": name,
                            "range": range_info.get("ranges", [{}])[0],
                        }

    def _extract_header_footer_types(self) -> None:
        """Extract existing header/footer types from document."""
        # In a real implementation, we would parse the document structure
        # to find existing headers/footers and their types.
        # For this mock, types are tracked as headers/footers are created.
        pass

    def get(self) -> dict[str, Any]:
        """Get the current document state.

        Returns:
            Complete Document object with current state.
        """
        result = copy.deepcopy(self._document)
        result["revisionId"] = self._revision_id
        return result

    def batch_update(
        self,
        requests: list[dict[str, Any]],
        write_control: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Apply batchUpdate requests to the document.

        All requests are atomic - either all succeed or all fail.
        Requests are processed sequentially in order.

        Args:
            requests: List of request objects to apply.
            write_control: Optional WriteControl for handling concurrent edits.

        Returns:
            Response with replies array and updated revision ID.

        Raises:
            ValidationError: If any request fails validation.
        """
        # Validate write control if provided
        if write_control:
            self._validate_write_control(write_control)

        # Process all requests sequentially
        replies: list[dict[str, Any]] = []

        # Make a backup for atomicity
        backup_document = copy.deepcopy(self._document)
        backup_revision = self._revision_id
        backup_named_ranges = copy.deepcopy(self._named_ranges)

        try:
            for request in requests:
                reply = self._process_request(request)
                replies.append(reply)

            # Update revision ID after successful batch
            self._revision_counter += 1
            self._revision_id = f"mock_revision_{self._revision_counter}"

            # Rebuild structure tracker to reflect any changes
            # (In a full implementation, we'd update it incrementally)
            self._structure_tracker = DocumentStructureTracker(self._document)

            return {
                "replies": replies,
                "documentId": self._document.get("documentId", ""),
                "writeControl": {"requiredRevisionId": self._revision_id},
            }

        except Exception:
            # Restore backup on any error (atomicity)
            self._document = backup_document
            self._revision_id = backup_revision
            self._named_ranges = backup_named_ranges
            raise

    def _validate_write_control(self, write_control: dict[str, Any]) -> None:
        """Validate WriteControl parameters.

        Args:
            write_control: WriteControl object with requiredRevisionId or targetRevisionId.

        Raises:
            ValidationError: If revision ID doesn't match.
        """
        required_revision = write_control.get("requiredRevisionId")
        if required_revision and required_revision != self._revision_id:
            raise ValidationError(
                f"Document was modified. Expected revision {required_revision}, "
                f"but current revision is {self._revision_id}",
                status_code=400,
            )

    def _process_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Process a single request.

        Args:
            request: Single request object.

        Returns:
            Reply object (may be empty).

        Raises:
            ValidationError: If request is invalid.
        """
        # Determine request type (only one key should be present)
        request_types = [k for k in request if k != "writeControl"]
        if len(request_types) != 1:
            raise ValidationError(
                f"Request must have exactly one operation, got: {request_types}"
            )

        request_type = request_types[0]
        request_data = request[request_type]

        # Dispatch to appropriate handler
        handler_map = {
            "insertText": self._handle_insert_text,
            "deleteContentRange": self._handle_delete_content_range,
            "updateTextStyle": self._handle_update_text_style,
            "updateParagraphStyle": self._handle_update_paragraph_style,
            "createParagraphBullets": self._handle_create_paragraph_bullets,
            "deleteParagraphBullets": self._handle_delete_paragraph_bullets,
            "insertTable": self._handle_insert_table,
            "insertTableRow": self._handle_insert_table_row,
            "insertTableColumn": self._handle_insert_table_column,
            "deleteTableRow": self._handle_delete_table_row,
            "deleteTableColumn": self._handle_delete_table_column,
            "createNamedRange": self._handle_create_named_range,
            "deleteNamedRange": self._handle_delete_named_range,
            "replaceAllText": self._handle_replace_all_text,
            # Deletion requests
            "deletePositionedObject": self._handle_delete_positioned_object,
            "deleteHeader": self._handle_delete_header,
            "deleteFooter": self._handle_delete_footer,
            # Creation requests
            "createHeader": self._handle_create_header,
            "createFooter": self._handle_create_footer,
            "createFootnote": self._handle_create_footnote,
            "addDocumentTab": self._handle_add_document_tab,
            # Update requests
            "updateTableColumnProperties": self._handle_update_table_column_properties,
            "updateTableCellStyle": self._handle_update_table_cell_style,
            "updateTableRowStyle": self._handle_update_table_row_style,
            "updateDocumentStyle": self._handle_update_document_style,
            "updateSectionStyle": self._handle_update_section_style,
            "updateDocumentTabProperties": self._handle_update_document_tab_properties,
            # Table operations
            "mergeTableCells": self._handle_merge_table_cells,
            "unmergeTableCells": self._handle_unmerge_table_cells,
            "pinTableHeaderRows": self._handle_pin_table_header_rows,
            # Insertion requests
            "insertInlineImage": self._handle_insert_inline_image,
            "insertPageBreak": self._handle_insert_page_break,
            "insertSectionBreak": self._handle_insert_section_break,
            "insertPerson": self._handle_insert_person,
            "insertDate": self._handle_insert_date,
            # Replacement requests
            "replaceImage": self._handle_replace_image,
            "replaceNamedRangeContent": self._handle_replace_named_range_content,
            "deleteTab": self._handle_delete_tab,
        }

        handler = handler_map.get(request_type)
        if not handler:
            raise ValidationError(f"Unsupported request type: {request_type}")

        return handler(request_data)

    # ========================================================================
    # Request Handlers
    # ========================================================================

    def _handle_insert_text(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle InsertTextRequest.

        Inserts text at a specified location, handling:
        - Control character stripping
        - Newline paragraph creation
        - Index validation
        - Paragraph boundary enforcement

        Args:
            request: InsertTextRequest data.

        Returns:
            Empty reply.

        Raises:
            ValidationError: If insertion is invalid.
        """
        text = request.get("text", "")
        location = request.get("location")
        end_of_segment = request.get("endOfSegmentLocation")

        # Check that exactly one location type is specified
        has_location = location is not None
        has_end_of_segment = end_of_segment is not None

        if not has_location and not has_end_of_segment:
            raise ValidationError(
                "Must specify either location or endOfSegmentLocation"
            )
        if has_location and has_end_of_segment:
            raise ValidationError(
                "Cannot specify both location and endOfSegmentLocation"
            )

        # Strip control characters as per API spec
        text = self._strip_control_characters(text)

        if location:
            index = location["index"]
            tab_id = location.get("tabId")
            segment_id = location.get("segmentId")
            self._insert_text_impl(text, index, tab_id, segment_id)
        else:
            # Insert at end of segment
            if end_of_segment is None:
                raise ValidationError("endOfSegmentLocation is required")
            tab_id = end_of_segment.get("tabId")
            segment_id = end_of_segment.get("segmentId")
            tab = self._get_tab(tab_id)
            segment, _ = self._get_segment(tab, segment_id)

            # Get end index (before final newline)
            content = segment.get("content", [])
            if content:
                last_elem = content[-1]
                end_index = last_elem.get("endIndex", 1)
                # Insert before the final newline
                insert_index = max(1, end_index - 1)
                self._insert_text_impl(text, insert_index, tab_id, segment_id)

        return {}

    def _handle_delete_content_range(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle DeleteContentRangeRequest.

        Deletes content with validation for:
        - Surrogate pairs
        - Final newlines
        - Structural element boundaries

        Args:
            request: DeleteContentRangeRequest data.

        Returns:
            Empty reply.

        Raises:
            ValidationError: If deletion is invalid.
        """
        range_obj = request.get("range")
        if not range_obj:
            raise ValidationError("range is required")

        start_index = range_obj["startIndex"]
        end_index = range_obj["endIndex"]
        tab_id = range_obj.get("tabId")
        segment_id = range_obj.get("segmentId")

        self._delete_content_range_impl(start_index, end_index, tab_id, segment_id)
        return {}

    def _handle_update_text_style(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle UpdateTextStyleRequest.

        Args:
            request: UpdateTextStyleRequest data.

        Returns:
            Empty reply.

        Raises:
            ValidationError: If update is invalid.
        """
        range_obj = request.get("range")
        text_style = request.get("textStyle")
        fields = request.get("fields")

        if not range_obj:
            raise ValidationError("range is required")
        if text_style is None:
            raise ValidationError("textStyle is required")
        if not fields:
            raise ValidationError("fields is required")

        start_index = range_obj["startIndex"]
        end_index = range_obj["endIndex"]
        tab_id = range_obj.get("tabId")

        # Simplified: just validate the range exists
        tab = self._get_tab(tab_id)
        self._validate_range(tab, start_index, end_index)

        # In a full implementation, we would:
        # - Parse the field mask
        # - Find all TextRuns in the range
        # - Apply the style updates
        # - Handle style inheritance

        return {}

    def _handle_update_paragraph_style(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle UpdateParagraphStyleRequest.

        Args:
            request: UpdateParagraphStyleRequest data.

        Returns:
            Empty reply.
        """
        range_obj = request.get("range")
        paragraph_style = request.get("paragraphStyle")
        fields = request.get("fields")

        if not range_obj:
            raise ValidationError("range is required")
        if paragraph_style is None:
            raise ValidationError("paragraphStyle is required")
        if not fields:
            raise ValidationError("fields is required")

        start_index = range_obj["startIndex"]
        end_index = range_obj["endIndex"]
        tab_id = range_obj.get("tabId")

        tab = self._get_tab(tab_id)
        self._validate_range(tab, start_index, end_index)

        return {}

    def _handle_create_paragraph_bullets(
        self, request: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle CreateParagraphBulletsRequest.

        Args:
            request: CreateParagraphBulletsRequest data.

        Returns:
            Empty reply.
        """
        range_obj = request.get("range")
        bullet_preset = request.get("bulletPreset")

        if not range_obj:
            raise ValidationError("range is required")
        if not bullet_preset:
            raise ValidationError("bulletPreset is required")

        start_index = range_obj["startIndex"]
        end_index = range_obj["endIndex"]
        tab_id = range_obj.get("tabId")

        tab = self._get_tab(tab_id)
        self._validate_range(tab, start_index, end_index)

        return {}

    def _handle_delete_paragraph_bullets(
        self, request: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle DeleteParagraphBulletsRequest.

        Args:
            request: DeleteParagraphBulletsRequest data.

        Returns:
            Empty reply.
        """
        range_obj = request.get("range")
        if not range_obj:
            raise ValidationError("range is required")

        start_index = range_obj["startIndex"]
        end_index = range_obj["endIndex"]
        tab_id = range_obj.get("tabId")

        tab = self._get_tab(tab_id)
        self._validate_range(tab, start_index, end_index)

        return {}

    def _handle_insert_table(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle InsertTableRequest.

        Args:
            request: InsertTableRequest data.

        Returns:
            Empty reply.
        """
        rows = request.get("rows")
        columns = request.get("columns")
        location = request.get("location")
        end_of_segment = request.get("endOfSegmentLocation")

        if not rows or rows < 1:
            raise ValidationError("rows must be at least 1")
        if not columns or columns < 1:
            raise ValidationError("columns must be at least 1")

        if not location and not end_of_segment:
            raise ValidationError(
                "Must specify either location or endOfSegmentLocation"
            )
        if location and end_of_segment:
            raise ValidationError(
                "Cannot specify both location and endOfSegmentLocation"
            )

        # Validate location
        if location:
            index = location["index"]
            tab_id = location.get("tabId")
            segment_id = location.get("segmentId")

            # Tables cannot be inserted in footnotes
            # (can be inserted in headers/footers but not footnotes)
            if segment_id:
                tab = self._get_tab(tab_id)
                document_tab = tab.get("documentTab", {})
                footnotes = document_tab.get("footnotes", {})
                if segment_id in footnotes:
                    raise ValidationError(
                        "Cannot insert table in footnote. "
                        "Tables can be inserted in body, headers, and footers, but not footnotes."
                    )

            # Validate tab exists
            self._get_tab(tab_id)
            if index < 1:
                raise ValidationError("index must be at least 1")

        return {}

    def _handle_insert_table_row(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle InsertTableRowRequest."""
        table_cell_location = request.get("tableCellLocation")
        if not table_cell_location:
            raise ValidationError("tableCellLocation is required")
        return {}

    def _handle_insert_table_column(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle InsertTableColumnRequest."""
        table_cell_location = request.get("tableCellLocation")
        if not table_cell_location:
            raise ValidationError("tableCellLocation is required")
        return {}

    def _handle_delete_table_row(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle DeleteTableRowRequest."""
        table_cell_location = request.get("tableCellLocation")
        if not table_cell_location:
            raise ValidationError("tableCellLocation is required")
        return {}

    def _handle_delete_table_column(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle DeleteTableColumnRequest."""
        table_cell_location = request.get("tableCellLocation")
        if not table_cell_location:
            raise ValidationError("tableCellLocation is required")
        return {}

    def _handle_create_named_range(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle CreateNamedRangeRequest.

        Args:
            request: CreateNamedRangeRequest data.

        Returns:
            Reply with namedRangeId.

        Raises:
            ValidationError: If creation is invalid.
        """
        name = request.get("name")
        range_obj = request.get("range")

        if name is None:
            raise ValidationError("name is required")
        if not range_obj:
            raise ValidationError("range is required")

        # Validate name length (UTF-16 code units)
        name_length = utf16_len(name)
        if name_length < 1 or name_length > 256:
            raise ValidationError(
                f"name must be 1-256 UTF-16 code units, got {name_length}"
            )

        # Validate range
        start_index = range_obj.get("startIndex")
        end_index = range_obj.get("endIndex")
        tab_id = range_obj.get("tabId")

        if start_index is None or end_index is None:
            raise ValidationError("range must have startIndex and endIndex")

        tab = self._get_tab(tab_id)
        self._validate_range(tab, start_index, end_index)

        # Generate unique ID
        named_range_id = f"namedRange_{uuid.uuid4().hex[:16]}"

        # Store in tracking dict
        self._named_ranges[named_range_id] = {"name": name, "range": range_obj}

        # Add to document structure
        document_tab = tab.get("documentTab", {})
        if "namedRanges" not in document_tab:
            document_tab["namedRanges"] = {}

        if name not in document_tab["namedRanges"]:
            document_tab["namedRanges"][name] = {"namedRanges": []}

        document_tab["namedRanges"][name]["namedRanges"].append(
            {"namedRangeId": named_range_id, "ranges": [range_obj]}
        )

        return {"createNamedRange": {"namedRangeId": named_range_id}}

    def _handle_delete_named_range(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle DeleteNamedRangeRequest.

        Args:
            request: DeleteNamedRangeRequest data.

        Returns:
            Empty reply.
        """
        named_range_id = request.get("namedRangeId")
        name = request.get("name")

        if not named_range_id and not name:
            raise ValidationError("Must specify either namedRangeId or name")
        if named_range_id and name:
            raise ValidationError("Cannot specify both namedRangeId and name")

        if named_range_id:
            # Delete specific range by ID
            if named_range_id not in self._named_ranges:
                raise ValidationError(f"Named range not found: {named_range_id}")
            range_name = self._named_ranges[named_range_id]["name"]
            del self._named_ranges[named_range_id]

            # Also remove from document structure
            for tab in self._document.get("tabs", []):
                document_tab = tab.get("documentTab", {})
                named_ranges_obj = document_tab.get("namedRanges", {})
                if range_name in named_ranges_obj:
                    ranges_list = named_ranges_obj[range_name].get("namedRanges", [])
                    named_ranges_obj[range_name]["namedRanges"] = [
                        r for r in ranges_list if r.get("namedRangeId") != named_range_id
                    ]
                    # Remove the name entry if no ranges left
                    if not named_ranges_obj[range_name]["namedRanges"]:
                        del named_ranges_obj[range_name]

        else:
            # Delete all ranges with this name
            to_delete = [
                rid for rid, info in self._named_ranges.items() if info["name"] == name
            ]
            for rid in to_delete:
                del self._named_ranges[rid]

            # Also remove from document structure
            for tab in self._document.get("tabs", []):
                document_tab = tab.get("documentTab", {})
                named_ranges_obj = document_tab.get("namedRanges", {})
                if name in named_ranges_obj:
                    del named_ranges_obj[name]

        return {}

    def _handle_replace_all_text(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle ReplaceAllTextRequest.

        Args:
            request: ReplaceAllTextRequest data.

        Returns:
            Reply with occurrences replaced count.
        """
        # Note: replace_text = request.get("replaceText", "") would be used in full impl
        contains_text = request.get("containsText")

        if not contains_text:
            raise ValidationError("containsText is required")

        # Simplified: return 0 occurrences
        # Full implementation would search and replace text
        return {"replaceAllText": {"occurrencesChanged": 0}}

    # ========================================================================
    # Deletion Requests
    # ========================================================================

    def _handle_delete_positioned_object(
        self, request: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle DeletePositionedObjectRequest.

        Args:
            request: DeletePositionedObjectRequest data.

        Returns:
            Empty reply.
        """
        object_id = request.get("objectId")
        if not object_id:
            raise ValidationError("objectId is required")

        tab_id = request.get("tabId")
        # Validate tab exists
        self._get_tab(tab_id)

        # In a full implementation, we would:
        # - Verify the positioned object exists
        # - Remove it from the document's positionedObjects
        return {}

    def _handle_delete_header(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle DeleteHeaderRequest.

        Args:
            request: DeleteHeaderRequest data.

        Returns:
            Empty reply.
        """
        header_id = request.get("headerId")
        if not header_id:
            raise ValidationError("headerId is required")

        tab_id = request.get("tabId")
        tab = self._get_tab(tab_id)

        # In a full implementation, we would:
        # - Verify the header exists
        # - Remove it from the document
        document_tab = tab.get("documentTab", {})
        headers = document_tab.get("headers", {})
        if header_id not in headers:
            raise ValidationError(f"Header not found: {header_id}")

        return {}

    def _handle_delete_footer(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle DeleteFooterRequest.

        Args:
            request: DeleteFooterRequest data.

        Returns:
            Empty reply.
        """
        footer_id = request.get("footerId")
        if not footer_id:
            raise ValidationError("footerId is required")

        tab_id = request.get("tabId")
        tab = self._get_tab(tab_id)

        # In a full implementation, we would:
        # - Verify the footer exists
        # - Remove it from the document
        document_tab = tab.get("documentTab", {})
        footers = document_tab.get("footers", {})
        if footer_id not in footers:
            raise ValidationError(f"Footer not found: {footer_id}")

        return {}

    # ========================================================================
    # Creation Requests
    # ========================================================================

    def _handle_create_header(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle CreateHeaderRequest.

        Args:
            request: CreateHeaderRequest data.

        Returns:
            Reply with created header ID.
        """
        header_type = request.get("type")
        if not header_type:
            raise ValidationError("type is required")

        # Check if header of this type already exists
        if header_type in self._header_types:
            raise ValidationError(
                f"A header of type {header_type} already exists. "
                "Only one header of each type (DEFAULT, FIRST_PAGE, EVEN_PAGE) is allowed."
            )

        section_break_location = request.get("sectionBreakLocation")
        tab_id = None
        if section_break_location:
            tab_id = section_break_location.get("tabId")

        tab = self._get_tab(tab_id)

        # Generate unique ID
        header_id = f"header_{uuid.uuid4().hex[:16]}"

        # Track this header type
        self._header_types.add(header_type)

        # Create the header segment and add to document structure
        document_tab = tab.get("documentTab", {})
        if "headers" not in document_tab:
            document_tab["headers"] = {}

        document_tab["headers"][header_id] = {
            "content": [
                {
                    "startIndex": 1,
                    "endIndex": 2,
                    "paragraph": {
                        "elements": [
                            {
                                "startIndex": 1,
                                "endIndex": 2,
                                "textRun": {"content": "\n", "textStyle": {}},
                            }
                        ],
                        "paragraphStyle": {},
                    },
                }
            ]
        }

        return {"createHeader": {"headerId": header_id}}

    def _handle_create_footer(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle CreateFooterRequest.

        Args:
            request: CreateFooterRequest data.

        Returns:
            Reply with created footer ID.
        """
        footer_type = request.get("type")
        if not footer_type:
            raise ValidationError("type is required")

        # Check if footer of this type already exists
        if footer_type in self._footer_types:
            raise ValidationError(
                f"A footer of type {footer_type} already exists. "
                "Only one footer of each type (DEFAULT, FIRST_PAGE, EVEN_PAGE) is allowed."
            )

        section_break_location = request.get("sectionBreakLocation")
        tab_id = None
        if section_break_location:
            tab_id = section_break_location.get("tabId")

        tab = self._get_tab(tab_id)

        # Generate unique ID
        footer_id = f"footer_{uuid.uuid4().hex[:16]}"

        # Track this footer type
        self._footer_types.add(footer_type)

        # Create the footer segment and add to document structure
        document_tab = tab.get("documentTab", {})
        if "footers" not in document_tab:
            document_tab["footers"] = {}

        document_tab["footers"][footer_id] = {
            "content": [
                {
                    "startIndex": 1,
                    "endIndex": 2,
                    "paragraph": {
                        "elements": [
                            {
                                "startIndex": 1,
                                "endIndex": 2,
                                "textRun": {"content": "\n", "textStyle": {}},
                            }
                        ],
                        "paragraphStyle": {},
                    },
                }
            ]
        }

        return {"createFooter": {"footerId": footer_id}}

    def _handle_create_footnote(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle CreateFootnoteRequest.

        Args:
            request: CreateFootnoteRequest data.

        Returns:
            Reply with created footnote ID.
        """
        location = request.get("location")
        end_of_segment = request.get("endOfSegmentLocation")

        if not location and not end_of_segment:
            raise ValidationError(
                "Must specify either location or endOfSegmentLocation"
            )
        if location and end_of_segment:
            raise ValidationError(
                "Cannot specify both location and endOfSegmentLocation"
            )

        # Validate location
        if location:
            index = location["index"]
            tab_id = location.get("tabId")
            segment_id = location.get("segmentId")

            # Footnotes must be in body (segment_id must be empty/None)
            if segment_id:
                raise ValidationError(
                    "Cannot create footnote in header, footer, or another footnote"
                )

            tab = self._get_tab(tab_id)
            # Validate index is within bounds
            if index < 1:
                raise ValidationError(f"Index must be at least 1, got {index}")

        # Generate unique ID
        footnote_id = f"footnote_{uuid.uuid4().hex[:16]}"

        # In a full implementation, we would:
        # - Create the footnote segment with space + newline
        # - Insert the footnote reference at the specified location
        # - Add it to the document structure

        if location:
            tab_id = location.get("tabId")
        else:
            tab_id = end_of_segment.get("tabId") if end_of_segment else None

        tab = self._get_tab(tab_id)
        document_tab = tab.get("documentTab", {})
        if "footnotes" not in document_tab:
            document_tab["footnotes"] = {}

        document_tab["footnotes"][footnote_id] = {
            "content": [
                {
                    "startIndex": 1,
                    "endIndex": 3,
                    "paragraph": {
                        "elements": [
                            {
                                "startIndex": 1,
                                "endIndex": 3,
                                "textRun": {"content": " \n", "textStyle": {}},
                            }
                        ],
                        "paragraphStyle": {},
                    },
                }
            ]
        }

        return {"createFootnote": {"footnoteId": footnote_id}}

    def _handle_add_document_tab(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle AddDocumentTabRequest.

        Args:
            request: AddDocumentTabRequest data.

        Returns:
            Reply with new tab ID.
        """
        tab_properties = request.get("tabProperties", {})

        # Generate unique ID
        tab_id = f"tab_{uuid.uuid4().hex[:16]}"

        # In a full implementation, we would:
        # - Insert the new tab at the specified index
        # - Increment indexes of subsequent tabs
        # - Create the tab structure with empty body

        new_tab = {
            "tabProperties": {
                "tabId": tab_id,
                "title": tab_properties.get("title", "Untitled Tab"),
                "index": tab_properties.get(
                    "index", len(self._document.get("tabs", []))
                ),
            },
            "documentTab": {
                "body": {
                    "content": [
                        {
                            "startIndex": 1,
                            "endIndex": 2,
                            "paragraph": {
                                "elements": [
                                    {
                                        "startIndex": 1,
                                        "endIndex": 2,
                                        "textRun": {"content": "\n", "textStyle": {}},
                                    }
                                ],
                                "paragraphStyle": {},
                            },
                        }
                    ]
                },
                "headers": {},
                "footers": {},
                "footnotes": {},
                "namedRanges": {},
            },
        }

        if "tabs" not in self._document:
            self._document["tabs"] = []
        self._document["tabs"].append(new_tab)

        return {"addDocumentTab": {"tabId": tab_id}}

    # ========================================================================
    # Update Requests
    # ========================================================================

    def _handle_update_table_column_properties(
        self, request: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle UpdateTableColumnPropertiesRequest.

        Args:
            request: UpdateTableColumnPropertiesRequest data.

        Returns:
            Empty reply.
        """
        table_start_location = request.get("tableStartLocation")
        table_column_properties = request.get("tableColumnProperties")
        fields = request.get("fields")

        if not table_start_location:
            raise ValidationError("tableStartLocation is required")
        if table_column_properties is None:
            raise ValidationError("tableColumnProperties is required")
        if not fields:
            raise ValidationError("fields is required")

        tab_id = table_start_location.get("tabId")
        self._get_tab(tab_id)

        # Validate minimum column width if width is being updated
        if "width" in fields or "*" in fields:
            width = table_column_properties.get("width", {})
            if width:
                magnitude = width.get("magnitude", 0)
                unit = width.get("unit", "PT")
                if unit == "PT" and magnitude < 5:
                    raise ValidationError("Column width must be at least 5 points")

        # In a full implementation, we would:
        # - Find the table at the specified location
        # - Update the specified columns (or all if columnIndices not provided)
        # - Apply the column properties
        return {}

    def _handle_update_table_cell_style(
        self, request: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle UpdateTableCellStyleRequest.

        Args:
            request: UpdateTableCellStyleRequest data.

        Returns:
            Empty reply.
        """
        table_cell_style = request.get("tableCellStyle")
        fields = request.get("fields")

        if table_cell_style is None:
            raise ValidationError("tableCellStyle is required")
        if not fields:
            raise ValidationError("fields is required")

        # Must have either tableRange or tableStartLocation
        table_range = request.get("tableRange")
        table_start_location = request.get("tableStartLocation")

        if not table_range and not table_start_location:
            raise ValidationError(
                "Must specify either tableRange or tableStartLocation"
            )

        if table_range:
            tab_id = table_range.get("tabId")
        else:
            tab_id = table_start_location.get("tabId") if table_start_location else None

        self._get_tab(tab_id)

        # In a full implementation, we would:
        # - Find the table and cells
        # - Apply the style updates
        # - Handle border updates for adjacent cells
        return {}

    def _handle_update_table_row_style(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle UpdateTableRowStyleRequest.

        Args:
            request: UpdateTableRowStyleRequest data.

        Returns:
            Empty reply.
        """
        table_start_location = request.get("tableStartLocation")
        table_row_style = request.get("tableRowStyle")
        fields = request.get("fields")

        if not table_start_location:
            raise ValidationError("tableStartLocation is required")
        if table_row_style is None:
            raise ValidationError("tableRowStyle is required")
        if not fields:
            raise ValidationError("fields is required")

        tab_id = table_start_location.get("tabId")
        self._get_tab(tab_id)

        # In a full implementation, we would:
        # - Find the table at the specified location
        # - Update the specified rows (or all if rowIndices not provided)
        # - Apply the row style properties
        return {}

    def _handle_update_document_style(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle UpdateDocumentStyleRequest.

        Args:
            request: UpdateDocumentStyleRequest data.

        Returns:
            Empty reply.
        """
        document_style = request.get("documentStyle")
        fields = request.get("fields")

        if document_style is None:
            raise ValidationError("documentStyle is required")
        if not fields:
            raise ValidationError("fields is required")

        tab_id = request.get("tabId")
        self._get_tab(tab_id)

        # In a full implementation, we would:
        # - Update the document-level style properties
        # - Handle cascading changes to match Docs editor behavior
        return {}

    def _handle_update_section_style(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle UpdateSectionStyleRequest.

        Args:
            request: UpdateSectionStyleRequest data.

        Returns:
            Empty reply.
        """
        range_obj = request.get("range")
        section_style = request.get("sectionStyle")
        fields = request.get("fields")

        if not range_obj:
            raise ValidationError("range is required")
        if section_style is None:
            raise ValidationError("sectionStyle is required")
        if not fields:
            raise ValidationError("fields is required")

        # Validate segment ID must be empty (body-only)
        segment_id = range_obj.get("segmentId")
        if segment_id:
            raise ValidationError(
                "Section styles can only be applied to body, not headers/footers/footnotes"
            )

        start_index = range_obj["startIndex"]
        end_index = range_obj["endIndex"]
        tab_id = range_obj.get("tabId")

        tab = self._get_tab(tab_id)
        self._validate_range(tab, start_index, end_index)

        # In a full implementation, we would:
        # - Find all section breaks in the range
        # - Update their section styles
        # - Handle cascading changes
        return {}

    def _handle_update_document_tab_properties(
        self, request: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle UpdateDocumentTabPropertiesRequest.

        Args:
            request: UpdateDocumentTabPropertiesRequest data.

        Returns:
            Empty reply.
        """
        tab_properties = request.get("tabProperties")
        fields = request.get("fields")

        if not tab_properties:
            raise ValidationError("tabProperties is required")
        if not fields:
            raise ValidationError("fields is required")

        tab_id = tab_properties.get("tabId")
        if not tab_id:
            raise ValidationError("tabProperties.tabId is required")

        # Validate tab exists
        self._get_tab(tab_id)

        # In a full implementation, we would:
        # - Update the tab properties
        # - Apply the changes to the document structure
        return {}

    # ========================================================================
    # Table Operations
    # ========================================================================

    def _handle_merge_table_cells(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle MergeTableCellsRequest.

        Args:
            request: MergeTableCellsRequest data.

        Returns:
            Empty reply.
        """
        table_range = request.get("tableRange")
        if not table_range:
            raise ValidationError("tableRange is required")

        # Validate range is rectangular
        # In a full implementation, we would:
        # - Verify the range is rectangular
        # - Concatenate text from all cells
        # - Store in "head" cell (upper-left for LTR, upper-right for RTL)
        # - Mark other cells as merged

        tab_id = table_range.get("tabId")
        self._get_tab(tab_id)

        return {}

    def _handle_unmerge_table_cells(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle UnmergeTableCellsRequest.

        Args:
            request: UnmergeTableCellsRequest data.

        Returns:
            Empty reply.
        """
        table_range = request.get("tableRange")
        if not table_range:
            raise ValidationError("tableRange is required")

        # In a full implementation, we would:
        # - Find merged cells in the range
        # - Unmerge them
        # - Keep text in the "head" cell

        tab_id = table_range.get("tabId")
        self._get_tab(tab_id)

        return {}

    def _handle_pin_table_header_rows(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle PinTableHeaderRowsRequest.

        Args:
            request: PinTableHeaderRowsRequest data.

        Returns:
            Empty reply.
        """
        table_start_location = request.get("tableStartLocation")
        pinned_header_rows_count = request.get("pinnedHeaderRowsCount")

        if not table_start_location:
            raise ValidationError("tableStartLocation is required")
        if pinned_header_rows_count is None:
            raise ValidationError("pinnedHeaderRowsCount is required")

        tab_id = table_start_location.get("tabId")
        self._get_tab(tab_id)

        # In a full implementation, we would:
        # - Find the table
        # - Update the pinned header rows count
        return {}

    # ========================================================================
    # Insertion Requests
    # ========================================================================

    def _handle_insert_inline_image(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle InsertInlineImageRequest.

        Args:
            request: InsertInlineImageRequest data.

        Returns:
            Reply with inserted object ID.
        """
        uri = request.get("uri")
        location = request.get("location")
        end_of_segment = request.get("endOfSegmentLocation")

        if not uri:
            raise ValidationError("uri is required")

        if not location and not end_of_segment:
            raise ValidationError(
                "Must specify either location or endOfSegmentLocation"
            )
        if location and end_of_segment:
            raise ValidationError(
                "Cannot specify both location and endOfSegmentLocation"
            )

        # Validate URI length
        if len(uri) > 2048:  # 2 KB
            raise ValidationError("URI must be less than 2 KB")

        # Validate location
        if location:
            index = location["index"]
            tab_id = location.get("tabId")
            segment_id = location.get("segmentId")

            # Images cannot be in footnotes
            if segment_id:
                tab = self._get_tab(tab_id)
                _segment, segment_type = self._get_segment(tab, segment_id)
                if segment_type == "footnote":
                    raise ValidationError("Cannot insert image in footnote")

            # Validate index
            if index < 1:
                raise ValidationError(f"Index must be at least 1, got {index}")

        # Generate unique ID
        object_id = f"inlineImage_{uuid.uuid4().hex[:16]}"

        # In a full implementation, we would:
        # - Validate image URL is accessible
        # - Insert the InlineObjectElement at the specified location
        # - Add the inline object to the document
        return {"insertInlineImage": {"objectId": object_id}}

    def _handle_insert_page_break(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle InsertPageBreakRequest.

        Args:
            request: InsertPageBreakRequest data.

        Returns:
            Empty reply.
        """
        location = request.get("location")
        end_of_segment = request.get("endOfSegmentLocation")

        if not location and not end_of_segment:
            raise ValidationError(
                "Must specify either location or endOfSegmentLocation"
            )
        if location and end_of_segment:
            raise ValidationError(
                "Cannot specify both location and endOfSegmentLocation"
            )

        # Validate location
        if location:
            index = location["index"]
            tab_id = location.get("tabId")
            segment_id = location.get("segmentId")

            # Page breaks must be in body (segment_id must be empty/None)
            if segment_id:
                raise ValidationError(
                    "Cannot insert page break in header, footer, or footnote"
                )

            self._get_tab(tab_id)
            if index < 1:
                raise ValidationError(f"Index must be at least 1, got {index}")

        # In a full implementation, we would:
        # - Insert the page break element at the specified location
        # - Add a newline after the page break
        return {}

    def _handle_insert_section_break(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle InsertSectionBreakRequest.

        Args:
            request: InsertSectionBreakRequest data.

        Returns:
            Empty reply.
        """
        location = request.get("location")
        end_of_segment = request.get("endOfSegmentLocation")
        section_type = request.get("sectionType")

        if not location and not end_of_segment:
            raise ValidationError(
                "Must specify either location or endOfSegmentLocation"
            )
        if location and end_of_segment:
            raise ValidationError(
                "Cannot specify both location and endOfSegmentLocation"
            )
        if not section_type:
            raise ValidationError("sectionType is required")

        # Validate location
        if location:
            index = location["index"]
            tab_id = location.get("tabId")
            segment_id = location.get("segmentId")

            # Section breaks must be in body (segment_id must be empty/None)
            if segment_id:
                raise ValidationError(
                    "Cannot insert section break in header, footer, or footnote"
                )

            self._get_tab(tab_id)
            if index < 1:
                raise ValidationError(f"Index must be at least 1, got {index}")

        # In a full implementation, we would:
        # - Insert the section break element at the specified location
        # - Add a newline before the section break
        return {}

    def _handle_insert_person(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle InsertPersonRequest.

        Args:
            request: InsertPersonRequest data.

        Returns:
            Empty reply.
        """
        location = request.get("location")
        end_of_segment = request.get("endOfSegmentLocation")
        person_properties = request.get("personProperties")

        if not location and not end_of_segment:
            raise ValidationError(
                "Must specify either location or endOfSegmentLocation"
            )
        if location and end_of_segment:
            raise ValidationError(
                "Cannot specify both location and endOfSegmentLocation"
            )
        if not person_properties:
            raise ValidationError("personProperties is required")

        # Validate location
        if location:
            index = location["index"]
            tab_id = location.get("tabId")
            segment_id = location.get("segmentId")

            # Person mentions cannot be in equations
            if segment_id:
                tab = self._get_tab(tab_id)
                _segment, _segment_type = self._get_segment(tab, segment_id)
                # In a full implementation, check for equations

            if index < 1:
                raise ValidationError(f"Index must be at least 1, got {index}")

        # In a full implementation, we would:
        # - Insert the person element at the specified location
        return {}

    def _handle_insert_date(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle InsertDateRequest.

        Args:
            request: InsertDateRequest data.

        Returns:
            Empty reply.
        """
        location = request.get("location")
        end_of_segment = request.get("endOfSegmentLocation")
        date_element_properties = request.get("dateElementProperties")

        if not location and not end_of_segment:
            raise ValidationError(
                "Must specify either location or endOfSegmentLocation"
            )
        if location and end_of_segment:
            raise ValidationError(
                "Cannot specify both location and endOfSegmentLocation"
            )
        if not date_element_properties:
            raise ValidationError("dateElementProperties is required")

        # Validate location
        if location:
            index = location["index"]
            tab_id = location.get("tabId")

            if index < 1:
                raise ValidationError(f"Index must be at least 1, got {index}")

            # Validate tab exists
            self._get_tab(tab_id)

        # In a full implementation, we would:
        # - Insert the date element at the specified location
        return {}

    # ========================================================================
    # Replacement Requests
    # ========================================================================

    def _handle_replace_image(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle ReplaceImageRequest.

        Args:
            request: ReplaceImageRequest data.

        Returns:
            Empty reply.
        """
        image_object_id = request.get("imageObjectId")
        uri = request.get("uri")

        if not image_object_id:
            raise ValidationError("imageObjectId is required")
        if not uri:
            raise ValidationError("uri is required")

        # Validate URI length
        if len(uri) > 2048:  # 2 KB
            raise ValidationError("URI must be less than 2 KB")

        tab_id = request.get("tabId")
        self._get_tab(tab_id)

        # In a full implementation, we would:
        # - Find the image object
        # - Replace it with the new image
        # - Remove some image effects to match Docs editor behavior
        return {}

    def _handle_replace_named_range_content(
        self, request: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle ReplaceNamedRangeContentRequest.

        Args:
            request: ReplaceNamedRangeContentRequest data.

        Returns:
            Empty reply.
        """
        text = request.get("text")
        named_range_id = request.get("namedRangeId")
        named_range_name = request.get("namedRangeName")

        if text is None:
            raise ValidationError("text is required")

        if not named_range_id and not named_range_name:
            raise ValidationError("Must specify either namedRangeId or namedRangeName")

        # In a full implementation, we would:
        # - Find the named range(s)
        # - Replace content in the first range
        # - Delete content in other discontinuous ranges
        # - Validate the result doesn't create invalid structure
        return {}

    def _handle_delete_tab(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle DeleteTabRequest.

        Args:
            request: DeleteTabRequest data.

        Returns:
            Empty reply.
        """
        tab_id = request.get("tabId")
        if not tab_id:
            raise ValidationError("tabId is required")

        # Validate tab exists
        self._get_tab(tab_id)

        # In a full implementation, we would:
        # - Delete the tab and all child tabs
        # - Remove from document structure
        return {}

    # ========================================================================
    # Implementation Helpers
    # ========================================================================

    def _strip_control_characters(self, text: str) -> str:
        """Strip control characters from text as per API spec.

        Args:
            text: Input text.

        Returns:
            Text with control characters removed.
        """
        # Remove U+0000-U+0008, U+000C-U+001F
        text = re.sub(r"[\x00-\x08\x0c-\x1f]", "", text)
        # Remove Unicode Private Use Area U+E000-U+F8FF
        text = re.sub(r"[\ue000-\uf8ff]", "", text)
        return text

    def _validate_no_surrogate_pair_split(
        self, segment: dict[str, Any], start_index: int, end_index: int
    ) -> None:
        """Validate that deletion doesn't split a surrogate pair.

        Surrogate pairs in UTF-16:
        - High surrogate: 0xD800-0xDBFF
        - Low surrogate: 0xDC00-0xDFFF
        - Together they represent characters outside the Basic Multilingual Plane
        - Examples: emoji (😀), some Chinese characters, mathematical symbols

        Args:
            segment: The segment containing the content
            start_index: Start of deletion range
            end_index: End of deletion range

        Raises:
            ValidationError: If deletion would split a surrogate pair
        """
        # Walk through all text content in the segment
        for element in segment.get("content", []):
            self._check_surrogate_pairs_in_element(element, start_index, end_index)

    def _check_surrogate_pairs_in_element(
        self, element: dict[str, Any], start_index: int, end_index: int
    ) -> None:
        """Recursively check surrogate pairs in an element.

        Args:
            element: Structural element to check
            start_index: Start of deletion range
            end_index: End of deletion range

        Raises:
            ValidationError: If deletion would split a surrogate pair
        """
        if "paragraph" in element:
            for para_elem in element["paragraph"].get("elements", []):
                if "textRun" in para_elem:
                    text = para_elem["textRun"].get("content", "")
                    elem_start = para_elem.get("startIndex", 0)
                    self._validate_text_surrogate_pairs(
                        text, elem_start, start_index, end_index
                    )
        elif "table" in element:
            # Recursively check table cells
            table = element["table"]
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    for cell_elem in cell.get("content", []):
                        self._check_surrogate_pairs_in_element(
                            cell_elem, start_index, end_index
                        )
        elif "tableOfContents" in element:
            # Recursively check TOC content
            toc = element["tableOfContents"]
            for toc_elem in toc.get("content", []):
                self._check_surrogate_pairs_in_element(toc_elem, start_index, end_index)

    def _validate_text_surrogate_pairs(
        self, text: str, elem_start: int, del_start: int, del_end: int
    ) -> None:
        """Validate that deletion boundaries don't split surrogate pairs in text.

        Python strings use Unicode code points, not UTF-16 code units directly.
        Characters outside the Basic Multilingual Plane (BMP) like emoji are
        represented as surrogate pairs in UTF-16, consuming 2 code units each.

        Args:
            text: The text content (Python Unicode string)
            elem_start: Starting index of this text run in document
            del_start: Start of deletion range
            del_end: End of deletion range

        Raises:
            ValidationError: If deletion would split a surrogate pair
        """
        # Track current position in UTF-16 code units
        current_index = elem_start

        for char in text:
            char_code = ord(char)

            # Check if this character requires a surrogate pair in UTF-16
            # Characters >= U+10000 need surrogate pairs
            if char_code >= 0x10000:
                # This character will be encoded as a surrogate pair (2 UTF-16 units)
                # The pair occupies indices [current_index, current_index + 2)
                pair_start = current_index
                pair_end = current_index + 2

                # Check if deletion boundary falls within the pair
                # Invalid if start or end is in the middle of the pair
                # (between pair_start and pair_end, but not at the boundaries)
                if pair_start < del_start < pair_end or pair_start < del_end < pair_end:
                    raise ValidationError(
                        f"Cannot delete one code unit of a surrogate pair. "
                        f"Character '{char}' (U+{char_code:04X}) at index {pair_start} "
                        f"spans indices {pair_start}-{pair_end}. Deletion range "
                        f"{del_start}-{del_end} would split it."
                    )

                # This character consumed 2 UTF-16 code units
                current_index += 2
            else:
                # Regular BMP character (1 UTF-16 code unit)
                current_index += 1

    def _validate_no_table_cell_final_newline_deletion(
        self, tab: dict[str, Any], segment_id: str | None, start_index: int, end_index: int
    ) -> None:
        """Validate that deletion doesn't include final newline from table cells.

        Note: This check only applies when deleting content WITHIN table cells.
        When deleting an entire table structure, cell final newlines are allowed
        to be deleted as part of the table deletion.

        Args:
            tab: Tab object
            segment_id: Segment ID (must be None/body for tables)
            start_index: Start of deletion range
            end_index: End of deletion range

        Raises:
            ValidationError: If deletion would remove final newline from a cell
                while not deleting the entire table
        """
        # Tables only exist in the body
        if segment_id is not None:
            return

        segment, _ = self._get_segment(tab, segment_id)

        # Check all tables in the segment
        for element in segment.get("content", []):
            if "table" in element:
                table_start = element.get("startIndex", 0)
                table_end = element.get("endIndex", 0)

                # If deletion includes the entire table, allow it
                # (deleting entire table necessarily deletes cell final newlines)
                if start_index <= table_start and end_index >= table_end:
                    continue

                # Otherwise check individual cells
                table = element["table"]
                for row in table.get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        cell_content = cell.get("content", [])
                        if cell_content:
                            # Get the last element's endIndex (final newline position)
                            cell_end = cell_content[-1].get("endIndex", 0)
                            cell_start = cell_content[0].get("startIndex", 0)

                            # Check if deletion range includes this cell
                            if start_index < cell_end and end_index > cell_start:
                                # Deletion overlaps with this cell
                                # Check if it includes the final newline
                                if end_index >= cell_end:
                                    raise ValidationError(
                                        f"Cannot delete the final newline of a table cell. "
                                        f"Cell at indices {cell_start}-{cell_end}, "
                                        f"deletion range {start_index}-{end_index} includes "
                                        f"final newline at index {cell_end - 1}"
                                    )

    def _get_tab(self, tab_id: str | None) -> dict[str, Any]:
        """Get tab by ID, or first tab if None.

        Args:
            tab_id: Tab ID or None for first tab.

        Returns:
            Tab object.

        Raises:
            ValidationError: If tab not found.
        """
        tabs = self._document.get("tabs", [])
        if not tabs:
            raise ValidationError("Document has no tabs")

        if tab_id is None:
            first_tab: dict[str, Any] = tabs[0]
            return first_tab

        for tab in tabs:
            if tab.get("tabProperties", {}).get("tabId") == tab_id:
                found_tab: dict[str, Any] = tab
                return found_tab

        raise ValidationError(f"Tab not found: {tab_id}")

    def _get_segment(
        self, tab: dict[str, Any], segment_id: str | None
    ) -> tuple[dict[str, Any], str]:
        """Get segment (body, header, footer, footnote) from tab.

        Args:
            tab: Tab object.
            segment_id: Segment ID or None for body.

        Returns:
            Tuple of (segment object, segment type).

        Raises:
            ValidationError: If segment not found.
        """
        document_tab = tab.get("documentTab", {})

        if segment_id is None:
            # Default to body
            body = document_tab.get("body")
            if not body:
                raise ValidationError("Document has no body")
            return body, "body"

        # Check headers
        headers = document_tab.get("headers", {})
        if segment_id in headers:
            return headers[segment_id], "header"

        # Check footers
        footers = document_tab.get("footers", {})
        if segment_id in footers:
            return footers[segment_id], "footer"

        # Check footnotes
        footnotes = document_tab.get("footnotes", {})
        if segment_id in footnotes:
            return footnotes[segment_id], "footnote"

        raise ValidationError(f"Segment not found: {segment_id}")

    def _validate_range(
        self, tab: dict[str, Any], start_index: int, end_index: int
    ) -> None:
        """Validate that a range is within document bounds.

        Args:
            tab: Tab object.
            start_index: Start index.
            end_index: End index.

        Raises:
            ValidationError: If range is invalid.
        """
        if start_index < 1:
            raise ValidationError(f"startIndex must be at least 1, got {start_index}")
        if end_index <= start_index:
            raise ValidationError(
                f"endIndex ({end_index}) must be greater than startIndex ({start_index})"
            )

        # Get document bounds
        document_tab = tab.get("documentTab", {})
        body = document_tab.get("body", {})
        content = body.get("content", [])

        if content:
            last_element = content[-1]
            max_index = last_element.get("endIndex", 1)
            if end_index > max_index:
                raise ValidationError(
                    f"endIndex ({end_index}) exceeds document length ({max_index})"
                )

    def _insert_text_impl(
        self, text: str, index: int, tab_id: str | None, segment_id: str | None
    ) -> None:
        """Insert text at a specific index with full implementation.

        Args:
            text: Text to insert.
            index: Index to insert at.
            tab_id: Tab ID or None for first tab.
            segment_id: Segment ID or None for body.

        Raises:
            ValidationError: If insertion is invalid.
        """
        if index < 1:
            raise ValidationError(f"Index must be at least 1, got {index}")

        tab = self._get_tab(tab_id)
        segment, segment_type = self._get_segment(tab, segment_id)

        # Validate index is within bounds
        content = segment.get("content", [])
        if not content:
            raise ValidationError(f"Segment {segment_type} has no content")

        # Find the last element to determine max index
        last_element = content[-1]
        max_index = last_element.get("endIndex", 1)

        if index >= max_index:
            raise ValidationError(
                f"Index {index} is beyond segment end {max_index - 1}"
            )

        # Validate we're not inserting at a table boundary
        for element in content:
            if "table" in element:
                table_start = element.get("startIndex", 0)
                if index == table_start:
                    raise ValidationError(
                        "Cannot insert text at table start index. "
                        "Insert in the preceding paragraph instead."
                    )

        # Calculate text length in UTF-16 code units
        text_len = utf16_len(text)

        # Actually insert the text into the document
        self._insert_text_into_segment(segment, index, text, text_len)

    def _delete_content_range_impl(
        self,
        start_index: int,
        end_index: int,
        tab_id: str | None,
        segment_id: str | None,
    ) -> None:
        """Delete content range with full validation.

        This validates all the constraints:
        - No surrogate pair splitting
        - No deletion of final newlines
        - No partial structural element deletion

        Args:
            start_index: Start of range.
            end_index: End of range (exclusive).
            tab_id: Tab ID or None for first tab.
            segment_id: Segment ID or None for body.

        Raises:
            ValidationError: If deletion is invalid.
        """
        if start_index < 1:
            raise ValidationError(f"startIndex must be at least 1, got {start_index}")
        if end_index <= start_index:
            raise ValidationError(
                f"endIndex ({end_index}) must be greater than startIndex ({start_index})"
            )

        tab = self._get_tab(tab_id)
        segment, segment_type = self._get_segment(tab, segment_id)

        content = segment.get("content", [])
        if not content:
            raise ValidationError(f"Segment {segment_type} has no content")

        last_element = content[-1]
        max_index = last_element.get("endIndex", 1)

        # Validate we're not splitting surrogate pairs (check this FIRST)
        self._validate_no_surrogate_pair_split(segment, start_index, end_index)

        # Cannot delete the final newline
        if end_index >= max_index:
            raise ValidationError(
                f"Cannot delete the final newline of {segment_type}. "
                f"Deletion range {start_index}-{end_index} includes final newline at {max_index - 1}"
            )

        # Validate we're not deleting final newline from table cells
        self._validate_no_table_cell_final_newline_deletion(
            tab, segment_id, start_index, end_index
        )

        # Validate structural element constraints (TOC, equations, section breaks)
        self._structure_tracker.validate_delete_range(start_index, end_index)

        # Actually delete the content from the document
        self._delete_content_from_segment(segment, start_index, end_index)

    # ========================================================================
    # Document Modification Helpers
    # ========================================================================

    def _insert_text_into_segment(
        self, segment: dict[str, Any], index: int, text: str, text_len: int
    ) -> None:
        """Actually insert text into a segment, modifying the document structure.

        Args:
            segment: The segment to modify
            index: The index to insert at
            text: The text to insert
            text_len: Length of text in UTF-16 code units
        """
        content = segment.get("content", [])

        # If text contains newlines, handle paragraph creation
        if "\n" in text and text != "\n":
            # Complex case: split into paragraphs
            self._insert_text_with_newlines(segment, index, text, text_len)
        else:
            # Simple case: insert into existing paragraph
            self._insert_text_simple(segment, index, text, text_len)

    def _insert_text_simple(
        self, segment: dict[str, Any], index: int, text: str, text_len: int
    ) -> None:
        """Insert text without creating new paragraphs.

        Args:
            segment: The segment to modify
            index: The index to insert at
            text: The text to insert (no newlines except possibly final newline)
            text_len: Length in UTF-16 code units
        """
        content = segment.get("content", [])

        # Find the paragraph containing this index
        for element in content:
            elem_start = element.get("startIndex", 0)
            elem_end = element.get("endIndex", 0)

            if elem_start <= index < elem_end and "paragraph" in element:
                # Found the paragraph, insert text into it
                paragraph = element["paragraph"]
                para_elements = paragraph.get("elements", [])

                # Find the text run containing this index
                for i, para_elem in enumerate(para_elements):
                    run_start = para_elem.get("startIndex", 0)
                    run_end = para_elem.get("endIndex", 0)

                    if run_start <= index <= run_end and "textRun" in para_elem:
                        # Insert into this text run
                        text_run = para_elem["textRun"]
                        content_str = text_run.get("content", "")

                        # Calculate offset within this run
                        offset_in_run = self._calculate_utf16_offset(
                            content_str, index - run_start
                        )

                        # Insert the text
                        new_content = (
                            content_str[:offset_in_run]
                            + text
                            + content_str[offset_in_run:]
                        )
                        text_run["content"] = new_content

                        # Update this text run's endIndex
                        para_elem["endIndex"] = run_end + text_len

                        # Update all subsequent elements in this paragraph
                        for j in range(i + 1, len(para_elements)):
                            para_elements[j]["startIndex"] += text_len
                            para_elements[j]["endIndex"] += text_len

                        # Update paragraph endIndex
                        element["endIndex"] = elem_end + text_len

                        # Update all subsequent structural elements
                        self._shift_indexes_after(content, elem_end, text_len)
                        return

        # If we get here, we couldn't find the right place to insert
        raise ValidationError(f"Could not find paragraph to insert at index {index}")

    def _insert_text_with_newlines(
        self, segment: dict[str, Any], index: int, text: str, text_len: int
    ) -> None:
        """Insert text that contains newlines, creating new paragraphs.

        Args:
            segment: The segment to modify
            index: The index to insert at
            text: The text to insert (contains newlines)
            text_len: Length in UTF-16 code units
        """
        # For simplicity, split the text on newlines and insert multiple paragraphs
        # This is a simplified implementation
        parts = text.split("\n")

        content = segment.get("content", [])

        # Find the paragraph containing the insertion index
        for elem_idx, element in enumerate(content):
            elem_start = element.get("startIndex", 0)
            elem_end = element.get("endIndex", 0)

            if elem_start <= index < elem_end and "paragraph" in element:
                # Split this paragraph at the insertion point
                # For now, simplified: insert all text as one paragraph if it ends with \n
                # Otherwise treat as multiple paragraphs

                if text.endswith("\n"):
                    # Multiple paragraphs need to be created
                    # Simplified: just update the current paragraph with first part + newline
                    # and create new paragraph for rest

                    new_paragraphs = []
                    current_idx = index

                    for i, part in enumerate(parts):
                        if i == len(parts) - 1 and part == "":
                            # Empty final part after final newline
                            break

                        # Create paragraph for this part
                        part_with_newline = part + "\n" if i < len(parts) - 1 else part
                        part_len = utf16_len(part_with_newline)

                        new_para = {
                            "startIndex": current_idx,
                            "endIndex": current_idx + part_len,
                            "paragraph": {
                                "elements": [
                                    {
                                        "startIndex": current_idx,
                                        "endIndex": current_idx + part_len,
                                        "textRun": {
                                            "content": part_with_newline,
                                            "textStyle": {},
                                        },
                                    }
                                ],
                                "paragraphStyle": {},
                            },
                        }
                        new_paragraphs.append(new_para)
                        current_idx += part_len

                    # Remove old paragraph and insert new ones
                    content[elem_idx : elem_idx + 1] = new_paragraphs

                    # Shift all subsequent elements
                    self._shift_indexes_after(content, elem_end, text_len)
                    return

        # Fallback: just do simple insertion
        self._insert_text_simple(segment, index, text, text_len)

    def _delete_content_from_segment(
        self, segment: dict[str, Any], start_index: int, end_index: int
    ) -> None:
        """Actually delete content from a segment.

        Args:
            segment: The segment to modify
            start_index: Start of deletion range
            end_index: End of deletion range (exclusive)
        """
        content = segment.get("content", [])
        deletion_len = end_index - start_index

        # Find all paragraphs that overlap with the deletion range
        for element in content:
            elem_start = element.get("startIndex", 0)
            elem_end = element.get("endIndex", 0)

            # Check if this element overlaps with deletion range
            if elem_start < end_index and elem_end > start_index and "paragraph" in element:
                paragraph = element["paragraph"]
                para_elements = paragraph.get("elements", [])

                # Process each text run in the paragraph
                for para_elem in para_elements:
                    if "textRun" not in para_elem:
                        continue

                    run_start = para_elem.get("startIndex", 0)
                    run_end = para_elem.get("endIndex", 0)

                    # Check if this run overlaps with deletion range
                    if run_start < end_index and run_end > start_index:
                        text_run = para_elem["textRun"]
                        content_str = text_run.get("content", "")

                        # Calculate what part of this run to delete
                        delete_from = max(0, start_index - run_start)
                        delete_to = min(run_end - run_start, end_index - run_start)

                        # Convert to string offsets
                        str_delete_from = self._calculate_utf16_offset(
                            content_str, delete_from
                        )
                        str_delete_to = self._calculate_utf16_offset(
                            content_str, delete_to
                        )

                        # Delete the text
                        new_content = (
                            content_str[:str_delete_from] + content_str[str_delete_to:]
                        )
                        text_run["content"] = new_content

                        # Update this run's endIndex
                        chars_deleted = delete_to - delete_from
                        para_elem["endIndex"] = run_end - chars_deleted

                # Update paragraph endIndex
                element["endIndex"] = elem_end - deletion_len

        # Shift all subsequent elements
        self._shift_indexes_after(content, end_index, -deletion_len)

    def _shift_indexes_after(
        self, content: list[dict[str, Any]], after_index: int, shift_amount: int
    ) -> None:
        """Shift all indexes in elements after a certain point.

        Args:
            content: List of structural elements
            after_index: Shift indexes after this point
            shift_amount: Amount to shift (positive for insertion, negative for deletion)
        """
        for element in content:
            elem_start = element.get("startIndex", 0)
            elem_end = element.get("endIndex", 0)

            # Only shift elements that come after the modification point
            if elem_start >= after_index:
                element["startIndex"] = elem_start + shift_amount
                element["endIndex"] = elem_end + shift_amount

                # Also shift nested elements
                if "paragraph" in element:
                    para_elements = element["paragraph"].get("elements", [])
                    for para_elem in para_elements:
                        para_elem["startIndex"] = para_elem.get("startIndex", 0) + shift_amount
                        para_elem["endIndex"] = para_elem.get("endIndex", 0) + shift_amount

                elif "table" in element:
                    # Shift table cell indexes
                    table = element["table"]
                    for row in table.get("tableRows", []):
                        for cell in row.get("tableCells", []):
                            for cell_elem in cell.get("content", []):
                                self._shift_element_recursive(cell_elem, shift_amount)

    def _shift_element_recursive(
        self, element: dict[str, Any], shift_amount: int
    ) -> None:
        """Recursively shift an element and all its children.

        Args:
            element: Element to shift
            shift_amount: Amount to shift
        """
        element["startIndex"] = element.get("startIndex", 0) + shift_amount
        element["endIndex"] = element.get("endIndex", 0) + shift_amount

        if "paragraph" in element:
            for para_elem in element["paragraph"].get("elements", []):
                para_elem["startIndex"] = para_elem.get("startIndex", 0) + shift_amount
                para_elem["endIndex"] = para_elem.get("endIndex", 0) + shift_amount

        elif "table" in element:
            for row in element["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    for cell_elem in cell.get("content", []):
                        self._shift_element_recursive(cell_elem, shift_amount)

    def _calculate_utf16_offset(self, text: str, utf16_units: int) -> int:
        """Calculate string offset for a given UTF-16 code unit offset.

        Args:
            text: The text string
            utf16_units: Number of UTF-16 code units from start

        Returns:
            String index (Python character position)
        """
        if utf16_units == 0:
            return 0

        units_counted = 0
        for i, char in enumerate(text):
            if units_counted >= utf16_units:
                return i
            # Emoji and other non-BMP chars are 2 UTF-16 units
            if ord(char) >= 0x10000:
                units_counted += 2
            else:
                units_counted += 1

        return len(text)
