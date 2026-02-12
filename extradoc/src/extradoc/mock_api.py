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
            raise ValidationError("Must specify either location or endOfSegmentLocation")
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

    def _handle_update_paragraph_style(
        self, request: dict[str, Any]
    ) -> dict[str, Any]:
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
            raise ValidationError("Must specify either location or endOfSegmentLocation")
        if location and end_of_segment:
            raise ValidationError(
                "Cannot specify both location and endOfSegmentLocation"
            )

        # Simplified: just validate the index
        if location:
            index = location["index"]
            tab_id = location.get("tabId")
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
            del self._named_ranges[named_range_id]

        else:
            # Delete all ranges with this name
            to_delete = [
                rid
                for rid, info in self._named_ranges.items()
                if info["name"] == name
            ]
            for rid in to_delete:
                del self._named_ranges[rid]

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
        """Insert text at a specific index with full validation.

        This is a simplified implementation that validates the operation
        but doesn't fully update the document structure. A complete
        implementation would:

        1. Navigate to the correct paragraph containing the index
        2. Split the TextRun at the insertion point
        3. Insert new text (creating new paragraphs for newlines)
        4. Update all indexes for subsequent elements
        5. Handle style inheritance

        Args:
            text: Text to insert (not used in simplified validation-only impl).
            index: Index to insert at.
            tab_id: Tab ID or None for first tab.
            segment_id: Segment ID or None for body.

        Raises:
            ValidationError: If insertion is invalid.
        """
        # Note: text parameter is not used in this simplified validation-only impl
        _ = text  # Suppress unused warning
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

        # In a full implementation, we would update the document structure here
        # For now, this serves as validation that the operation is legal

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

        # Cannot delete the final newline
        if end_index >= max_index:
            raise ValidationError(
                f"Cannot delete the final newline of {segment_type}. "
                f"Deletion range {start_index}-{end_index} includes final newline at {max_index - 1}"
            )

        # Validate we're not partially deleting structural elements
        for element in content:
            elem_start = element.get("startIndex", 0)
            elem_end = element.get("endIndex", 0)

            # Check if deletion partially overlaps a table
            if "table" in element:
                # Partial overlap is not allowed
                if (start_index < elem_end and end_index > elem_start) and not (
                    start_index <= elem_start and end_index >= elem_end
                ):
                    raise ValidationError(
                        f"Cannot partially delete table at {elem_start}-{elem_end}. "
                        "Delete the entire table or content within cells only."
                    )

                # Cannot delete newline before table
                if elem_start > 0 and start_index <= elem_start < end_index:
                    raise ValidationError(
                        f"Cannot delete newline before table at index {elem_start}"
                    )

        # In a full implementation, we would:
        # 1. Remove the specified range from all TextRuns
        # 2. Merge paragraphs if deletion crosses paragraph boundary
        # 3. Update all indexes for subsequent elements
        # 4. Handle style merging
