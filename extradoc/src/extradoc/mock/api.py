"""Main MockGoogleDocsAPI class that dispatches to handler modules."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from extradoc.api_types._generated import (
    BatchUpdateDocumentRequest,
    BatchUpdateDocumentResponse,
    Document,
)
from extradoc.mock import (
    bullet_ops,
    named_range_ops,
    segment_ops,
    stubs,
    style_ops,
    table_ops,
    text_ops,
)
from extradoc.mock.exceptions import ValidationError
from extradoc.mock.reindex import reindex_and_normalize_all_tabs
from extradoc.mock.validation import DocumentStructureTracker


class MockGoogleDocsAPI:
    """Mock implementation of Google Docs API.

    This class simulates the behavior of the real Google Docs API, including:
    - Document state management
    - batchUpdate request processing
    - All validation rules and constraints
    - Proper UTF-16 index handling

    After each request, a centralized reindex + normalize pass fixes all
    indices and consolidates text runs. Handlers only modify content.

    Public interface uses Pydantic types (Document, BatchUpdateDocumentRequest,
    BatchUpdateDocumentResponse). Internally the document is stored as a plain
    dict so that all 13 handler modules can continue to operate without change.
    Use _get_raw() / _batch_update_raw() when you need the raw dict boundary
    (e.g. MockTransport, CompositeTransport).
    """

    def __init__(self, doc: Document) -> None:
        initial = doc.model_dump(by_alias=True, exclude_none=True)
        self._document = copy.deepcopy(initial)
        self._revision_id = initial.get("revisionId", "mock_revision_1")
        self._revision_counter = 1

        self._named_ranges: dict[str, dict[str, Any]] = {}
        self._extract_named_ranges()

        self._structure_tracker = DocumentStructureTracker(self._document)

        self._header_types: set[str] = set()
        self._footer_types: set[str] = set()
        self._extract_header_footer_types()

    def _extract_named_ranges(self) -> None:
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
        pass

    def _get_raw(self) -> dict[str, Any]:
        """Return current document state as a raw dict (internal/transport use only)."""
        result = copy.deepcopy(self._document)
        result["revisionId"] = self._revision_id
        _strip_explicit_keys(result)
        return result

    def get(self) -> Document:
        """Return current document state as a typed Document."""
        return Document.model_validate(self._get_raw())

    def _batch_update_raw(
        self,
        requests: list[dict[str, Any]],
        write_control: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Apply a list of raw request dicts and return a raw response dict.

        Internal method used by MockTransport and CompositeTransport.
        Prefer batch_update() for typed callers.
        """
        if write_control:
            self._validate_write_control(write_control)

        replies: list[dict[str, Any]] = []

        backup_document = copy.deepcopy(self._document)
        backup_revision = self._revision_id
        backup_named_ranges = copy.deepcopy(self._named_ranges)

        try:
            for request in requests:
                reply = self._process_request(request)
                replies.append(reply)

                # Reindex and normalize after each request
                reindex_and_normalize_all_tabs(self._document)

                # Rebuild structure tracker so subsequent requests
                # validate against the updated document state
                self._structure_tracker = DocumentStructureTracker(self._document)

            self._revision_counter += 1
            self._revision_id = f"mock_revision_{self._revision_counter}"

            return {
                "replies": replies,
                "documentId": self._document.get("documentId", ""),
                "writeControl": {"requiredRevisionId": self._revision_id},
            }

        except Exception:
            self._document = backup_document
            self._revision_id = backup_revision
            self._named_ranges = backup_named_ranges
            raise

    def batch_update(
        self,
        batch: BatchUpdateDocumentRequest,
    ) -> BatchUpdateDocumentResponse:
        """Apply a batch of typed requests and return a typed response."""
        request_dicts = [
            req.model_dump(by_alias=True, exclude_none=True)
            for req in (batch.requests or [])
        ]
        write_control_dict = None
        if batch.write_control:
            write_control_dict = batch.write_control.model_dump(
                by_alias=True, exclude_none=True
            )
        response_dict = self._batch_update_raw(request_dicts, write_control_dict)
        return BatchUpdateDocumentResponse.model_validate(response_dict)

    def _validate_write_control(self, write_control: dict[str, Any]) -> None:
        required_revision = write_control.get("requiredRevisionId")
        if required_revision and required_revision != self._revision_id:
            raise ValidationError(
                f"Document was modified. Expected revision {required_revision}, "
                f"but current revision is {self._revision_id}",
                status_code=400,
            )

    def _process_request(self, request: dict[str, Any]) -> dict[str, Any]:
        request_types = [k for k in request if k != "writeControl"]
        if len(request_types) != 1:
            raise ValidationError(
                f"Request must have exactly one operation, got: {request_types}"
            )

        request_type = request_types[0]
        request_data = request[request_type]

        # Handlers that need extra state
        if request_type == "createHeader":
            return segment_ops.handle_create_header(
                self._document,
                request_data,
                self._structure_tracker,
                self._header_types,
            )
        if request_type == "createFooter":
            return segment_ops.handle_create_footer(
                self._document,
                request_data,
                self._structure_tracker,
                self._footer_types,
            )
        if request_type == "createNamedRange":
            return named_range_ops.handle_create_named_range(
                self._document,
                request_data,
                self._structure_tracker,
                self._named_ranges,
            )
        if request_type == "deleteNamedRange":
            return named_range_ops.handle_delete_named_range(
                self._document,
                request_data,
                self._structure_tracker,
                self._named_ranges,
            )

        # Standard handler dispatch
        _Handler = Callable[[dict[str, Any], dict[str, Any], Any], dict[str, Any]]
        handler_map: dict[str, _Handler] = {
            "insertText": text_ops.handle_insert_text,
            "deleteContentRange": text_ops.handle_delete_content_range,
            "updateTextStyle": style_ops.handle_update_text_style,
            "updateParagraphStyle": style_ops.handle_update_paragraph_style,
            "createParagraphBullets": bullet_ops.handle_create_paragraph_bullets,
            "deleteParagraphBullets": bullet_ops.handle_delete_paragraph_bullets,
            "insertTable": table_ops.handle_insert_table,
            "insertTableRow": table_ops.handle_insert_table_row,
            "insertTableColumn": table_ops.handle_insert_table_column,
            "deleteTableRow": table_ops.handle_delete_table_row,
            "deleteTableColumn": table_ops.handle_delete_table_column,
            "replaceAllText": stubs.handle_replace_all_text,
            "deletePositionedObject": stubs.handle_delete_positioned_object,
            "deleteHeader": segment_ops.handle_delete_header,
            "deleteFooter": segment_ops.handle_delete_footer,
            "createFootnote": segment_ops.handle_create_footnote,
            "addDocumentTab": segment_ops.handle_add_document_tab,
            "updateTableColumnProperties": stubs.handle_update_table_column_properties,
            "updateTableCellStyle": stubs.handle_update_table_cell_style,
            "updateTableRowStyle": stubs.handle_update_table_row_style,
            "updateDocumentStyle": stubs.handle_update_document_style,
            "updateSectionStyle": stubs.handle_update_section_style,
            "updateDocumentTabProperties": segment_ops.handle_update_document_tab_properties,
            "mergeTableCells": stubs.handle_merge_table_cells,
            "unmergeTableCells": stubs.handle_unmerge_table_cells,
            "pinTableHeaderRows": stubs.handle_pin_table_header_rows,
            "insertInlineImage": stubs.handle_insert_inline_image,
            "insertPageBreak": stubs.handle_insert_page_break,
            "insertSectionBreak": stubs.handle_insert_section_break,
            "insertPerson": stubs.handle_insert_person,
            "insertDate": stubs.handle_insert_date,
            "replaceImage": stubs.handle_replace_image,
            "replaceNamedRangeContent": stubs.handle_replace_named_range_content,
            "deleteTab": segment_ops.handle_delete_tab,
        }

        handler = handler_map.get(request_type)
        if not handler:
            raise ValidationError(f"Unsupported request type: {request_type}")

        return handler(self._document, request_data, self._structure_tracker)


def _strip_explicit_keys(obj: Any) -> None:
    """Recursively remove __explicit__ keys from document structure."""
    if isinstance(obj, dict):
        obj.pop("__explicit__", None)
        for v in obj.values():
            _strip_explicit_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            _strip_explicit_keys(item)
