"""Tests for MockGoogleDocsAPI."""

from __future__ import annotations

import pytest

from extradoc.mock_api import MockAPIError, MockGoogleDocsAPI, ValidationError


def create_minimal_document() -> dict[str, any]:
    """Create a minimal valid Document object for testing.

    Returns a document with:
    - One tab
    - One body with a single paragraph containing "Hello\n"
    """
    return {
        "documentId": "test_doc_123",
        "title": "Test Document",
        "revisionId": "initial_revision",
        "tabs": [
            {
                "tabProperties": {
                    "tabId": "tab1",
                    "title": "Tab 1",
                    "index": 0,
                },
                "documentTab": {
                    "body": {
                        "content": [
                            {
                                "startIndex": 1,
                                "endIndex": 7,
                                "paragraph": {
                                    "elements": [
                                        {
                                            "startIndex": 1,
                                            "endIndex": 7,
                                            "textRun": {
                                                "content": "Hello\n",
                                                "textStyle": {},
                                            },
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
        ],
    }


def test_mock_api_initialization() -> None:
    """Test that MockGoogleDocsAPI initializes correctly."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Should deep copy the document
    result = api.get()
    assert result["documentId"] == "test_doc_123"
    assert result["title"] == "Test Document"

    # Modifying original should not affect the mock
    doc["title"] = "Modified"
    assert api.get()["title"] == "Test Document"


def test_get_returns_copy() -> None:
    """Test that get() returns a copy, not the original."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    result1 = api.get()
    result1["title"] = "Modified"

    result2 = api.get()
    assert result2["title"] == "Test Document"


def test_batch_update_empty_requests() -> None:
    """Test batchUpdate with empty requests list."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    response = api.batch_update([])

    assert response["documentId"] == "test_doc_123"
    assert response["replies"] == []
    assert "writeControl" in response


def test_batch_update_increments_revision() -> None:
    """Test that successful batchUpdate increments revision ID."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    initial_doc = api.get()
    initial_revision = initial_doc["revisionId"]

    # Make a simple update
    requests = [{"insertText": {"location": {"index": 1}, "text": "Hi"}}]

    response = api.batch_update(requests)
    new_revision = response["writeControl"]["requiredRevisionId"]

    assert new_revision != initial_revision

    # Verify get() also returns new revision
    doc_after = api.get()
    assert doc_after["revisionId"] == new_revision


def test_write_control_required_revision_id() -> None:
    """Test WriteControl with requiredRevisionId."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    initial_doc = api.get()
    initial_revision = initial_doc["revisionId"]

    # First update should succeed with correct revision
    requests = [{"insertText": {"location": {"index": 1}, "text": "A"}}]
    write_control = {"requiredRevisionId": initial_revision}

    response = api.batch_update(requests, write_control)
    assert "replies" in response

    # Second update with old revision should fail
    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests, write_control)

    assert "modified" in str(exc_info.value).lower()


def test_atomicity_on_error() -> None:
    """Test that failed batchUpdate doesn't modify document."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    initial_doc = api.get()

    # Create a batch with one valid and one invalid request
    requests = [
        {"insertText": {"location": {"index": 1}, "text": "Valid"}},
        {"invalidRequest": {}},  # This should fail
    ]

    with pytest.raises(ValidationError):
        api.batch_update(requests)

    # Document should be unchanged
    doc_after = api.get()
    assert doc_after == initial_doc


# ========================================================================
# InsertText Tests
# ========================================================================


def test_insert_text_basic() -> None:
    """Test basic text insertion."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"insertText": {"location": {"index": 1}, "text": "Hi "}}]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_insert_text_strips_control_characters() -> None:
    """Test that control characters are stripped."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Should strip control characters but allow the text
    requests = [
        {"insertText": {"location": {"index": 1}, "text": "Hello\x00\x08World"}}
    ]

    # Should not raise an error (control chars are stripped)
    response = api.batch_update(requests)
    assert len(response["replies"]) == 1


def test_insert_text_at_end_of_segment() -> None:
    """Test inserting text at end of segment."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "insertText": {
                "endOfSegmentLocation": {"tabId": "tab1"},
                "text": "End",
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1


def test_insert_text_invalid_index() -> None:
    """Test that inserting at invalid index fails."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Index 0 is invalid (must be at least 1)
    requests = [{"insertText": {"location": {"index": 0}, "text": "Bad"}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "at least 1" in str(exc_info.value)


def test_insert_text_beyond_document() -> None:
    """Test that inserting beyond document fails."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Index 1000 is way beyond the document
    requests = [{"insertText": {"location": {"index": 1000}, "text": "Bad"}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "beyond" in str(exc_info.value).lower()


def test_insert_text_requires_location() -> None:
    """Test that insertText requires either location or endOfSegmentLocation."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Missing both location and endOfSegmentLocation
    requests = [{"insertText": {"text": "Bad"}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "location" in str(exc_info.value).lower()


def test_insert_text_cannot_have_both_locations() -> None:
    """Test that insertText cannot have both location types."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "insertText": {
                "location": {"index": 1},
                "endOfSegmentLocation": {},
                "text": "Bad",
            }
        }
    ]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "both" in str(exc_info.value).lower()


# ========================================================================
# DeleteContentRange Tests
# ========================================================================


def test_delete_content_range_basic() -> None:
    """Test basic content deletion."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Delete part of "Hello" (indices 1-3 = "He")
    requests = [{"deleteContentRange": {"range": {"startIndex": 1, "endIndex": 3}}}]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1


def test_delete_content_range_invalid_range() -> None:
    """Test that invalid range fails."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # endIndex <= startIndex is invalid
    requests = [{"deleteContentRange": {"range": {"startIndex": 5, "endIndex": 5}}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "greater than" in str(exc_info.value).lower()


def test_delete_content_range_final_newline() -> None:
    """Test that deleting final newline fails."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Try to delete the final newline (index 6-7 in "Hello\n")
    requests = [{"deleteContentRange": {"range": {"startIndex": 6, "endIndex": 7}}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "final newline" in str(exc_info.value).lower()


def test_delete_content_range_requires_range() -> None:
    """Test that deleteContentRange requires range."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"deleteContentRange": {}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "range is required" in str(exc_info.value)


# ========================================================================
# UpdateTextStyle Tests
# ========================================================================


def test_update_text_style_basic() -> None:
    """Test basic text style update."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "updateTextStyle": {
                "range": {"startIndex": 1, "endIndex": 5},
                "textStyle": {"bold": True},
                "fields": "bold",
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1


def test_update_text_style_requires_fields() -> None:
    """Test that updateTextStyle requires fields parameter."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "updateTextStyle": {
                "range": {"startIndex": 1, "endIndex": 5},
                "textStyle": {"bold": True},
            }
        }
    ]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "fields is required" in str(exc_info.value)


# ========================================================================
# UpdateParagraphStyle Tests
# ========================================================================


def test_update_paragraph_style_basic() -> None:
    """Test basic paragraph style update."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "updateParagraphStyle": {
                "range": {"startIndex": 1, "endIndex": 5},
                "paragraphStyle": {"namedStyleType": "HEADING_1"},
                "fields": "namedStyleType",
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1


# ========================================================================
# Bullet Tests
# ========================================================================


def test_create_paragraph_bullets_basic() -> None:
    """Test creating bullets."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "createParagraphBullets": {
                "range": {"startIndex": 1, "endIndex": 5},
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1


def test_delete_paragraph_bullets_basic() -> None:
    """Test deleting bullets."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"deleteParagraphBullets": {"range": {"startIndex": 1, "endIndex": 5}}}]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1


# ========================================================================
# Table Tests
# ========================================================================


def test_insert_table_basic() -> None:
    """Test inserting a table."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "insertTable": {
                "location": {"index": 1},
                "rows": 3,
                "columns": 3,
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1


def test_insert_table_invalid_dimensions() -> None:
    """Test that table must have positive dimensions."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Zero rows should fail
    requests = [{"insertTable": {"location": {"index": 1}, "rows": 0, "columns": 3}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "at least 1" in str(exc_info.value)


def test_insert_table_row_requires_location() -> None:
    """Test that insertTableRow requires tableCellLocation."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"insertTableRow": {"insertBelow": True}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "tableCellLocation is required" in str(exc_info.value)


# ========================================================================
# Named Range Tests
# ========================================================================


def test_create_named_range_basic() -> None:
    """Test creating a named range."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "createNamedRange": {
                "name": "test_range",
                "range": {"startIndex": 1, "endIndex": 5},
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1

    reply = response["replies"][0]
    assert "createNamedRange" in reply
    assert "namedRangeId" in reply["createNamedRange"]


def test_create_named_range_validates_name_length() -> None:
    """Test that named range name must be 1-256 UTF-16 code units."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Empty name should fail
    requests = [
        {
            "createNamedRange": {
                "name": "",
                "range": {"startIndex": 1, "endIndex": 5},
            }
        }
    ]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "1-256" in str(exc_info.value)


def test_create_named_range_validates_range() -> None:
    """Test that named range validates the range."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Invalid range (beyond document)
    requests = [
        {
            "createNamedRange": {
                "name": "test",
                "range": {"startIndex": 1, "endIndex": 1000},
            }
        }
    ]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "exceeds" in str(exc_info.value).lower()


def test_delete_named_range_by_id() -> None:
    """Test deleting a named range by ID."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # First create a named range
    create_requests = [
        {
            "createNamedRange": {
                "name": "test_range",
                "range": {"startIndex": 1, "endIndex": 5},
            }
        }
    ]

    create_response = api.batch_update(create_requests)
    range_id = create_response["replies"][0]["createNamedRange"]["namedRangeId"]

    # Now delete it by ID
    delete_requests = [{"deleteNamedRange": {"namedRangeId": range_id}}]

    response = api.batch_update(delete_requests)
    assert len(response["replies"]) == 1


def test_delete_named_range_by_name() -> None:
    """Test deleting named ranges by name."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Create two ranges with the same name
    create_requests = [
        {
            "createNamedRange": {
                "name": "duplicate",
                "range": {"startIndex": 1, "endIndex": 3},
            }
        },
        {
            "createNamedRange": {
                "name": "duplicate",
                "range": {"startIndex": 3, "endIndex": 5},
            }
        },
    ]

    api.batch_update(create_requests)

    # Delete all with this name
    delete_requests = [{"deleteNamedRange": {"name": "duplicate"}}]

    response = api.batch_update(delete_requests)
    assert len(response["replies"]) == 1


def test_delete_named_range_requires_id_or_name() -> None:
    """Test that deleteNamedRange requires either ID or name."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Neither ID nor name provided
    requests = [{"deleteNamedRange": {}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "must specify" in str(exc_info.value).lower()


def test_delete_named_range_cannot_have_both() -> None:
    """Test that deleteNamedRange cannot have both ID and name."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"deleteNamedRange": {"namedRangeId": "id123", "name": "test"}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "both" in str(exc_info.value).lower()


# ========================================================================
# ReplaceAllText Tests
# ========================================================================


def test_replace_all_text_basic() -> None:
    """Test basic replace all text."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "replaceAllText": {
                "containsText": {"text": "Hello", "matchCase": True},
                "replaceText": "Goodbye",
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1

    reply = response["replies"][0]
    assert "replaceAllText" in reply
    assert "occurrencesChanged" in reply["replaceAllText"]


def test_replace_all_text_requires_contains_text() -> None:
    """Test that replaceAllText requires containsText."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"replaceAllText": {"replaceText": "Test"}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "containsText is required" in str(exc_info.value)


# ========================================================================
# Multiple Request Tests
# ========================================================================


def test_multiple_requests_in_order() -> None:
    """Test that multiple requests are processed in order."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {"insertText": {"location": {"index": 1}, "text": "A"}},
        {"insertText": {"location": {"index": 1}, "text": "B"}},
        {
            "createNamedRange": {
                "name": "test",
                "range": {"startIndex": 1, "endIndex": 5},
            }
        },
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 3

    # First two should be empty
    assert response["replies"][0] == {}
    assert response["replies"][1] == {}

    # Third should have named range ID
    assert "createNamedRange" in response["replies"][2]


def test_invalid_request_type() -> None:
    """Test that invalid request type is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"unknownRequest": {}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "unsupported" in str(exc_info.value).lower()


def test_request_must_have_one_operation() -> None:
    """Test that request must have exactly one operation."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Multiple operations in one request
    requests = [
        {
            "insertText": {"location": {"index": 1}, "text": "A"},
            "deleteContentRange": {"range": {"startIndex": 1, "endIndex": 2}},
        }
    ]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "exactly one" in str(exc_info.value).lower()


# ========================================================================
# Tab Handling Tests
# ========================================================================


def test_invalid_tab_id() -> None:
    """Test that invalid tab ID is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {"insertText": {"location": {"index": 1, "tabId": "nonexistent"}, "text": "X"}}
    ]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "tab not found" in str(exc_info.value).lower()


def test_explicit_tab_id() -> None:
    """Test that explicit tab ID works."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {"insertText": {"location": {"index": 1, "tabId": "tab1"}, "text": "X"}}
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1


# ========================================================================
# Error Type Tests
# ========================================================================


def test_validation_error_is_mock_api_error() -> None:
    """Test that ValidationError is a subclass of MockAPIError."""
    assert issubclass(ValidationError, MockAPIError)


def test_mock_api_error_has_status_code() -> None:
    """Test that MockAPIError has status code."""
    error = MockAPIError("Test error", status_code=500)
    assert error.status_code == 500
    assert "Test error" in str(error)


def test_validation_error_defaults_to_400() -> None:
    """Test that ValidationError defaults to status 400."""
    error = ValidationError("Bad request")
    assert error.status_code == 400


# ========================================================================
# Deletion Request Tests
# ========================================================================


def test_delete_positioned_object_basic() -> None:
    """Test basic positioned object deletion."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"deletePositionedObject": {"objectId": "obj123"}}]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_delete_positioned_object_missing_object_id() -> None:
    """Test that missing objectId is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"deletePositionedObject": {}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "objectid is required" in str(exc_info.value).lower()


def test_delete_header_basic() -> None:
    """Test basic header deletion."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # First create a header
    create_requests = [{"createHeader": {"type": "DEFAULT"}}]
    create_response = api.batch_update(create_requests)
    header_id = create_response["replies"][0]["createHeader"]["headerId"]

    # Then delete it
    delete_requests = [{"deleteHeader": {"headerId": header_id}}]
    response = api.batch_update(delete_requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_delete_header_missing_header_id() -> None:
    """Test that missing headerId is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"deleteHeader": {}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "headerid is required" in str(exc_info.value).lower()


def test_delete_header_nonexistent() -> None:
    """Test that deleting nonexistent header fails."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"deleteHeader": {"headerId": "nonexistent"}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "header not found" in str(exc_info.value).lower()


def test_delete_footer_basic() -> None:
    """Test basic footer deletion."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # First create a footer
    create_requests = [{"createFooter": {"type": "DEFAULT"}}]
    create_response = api.batch_update(create_requests)
    footer_id = create_response["replies"][0]["createFooter"]["footerId"]

    # Then delete it
    delete_requests = [{"deleteFooter": {"footerId": footer_id}}]
    response = api.batch_update(delete_requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_delete_footer_missing_footer_id() -> None:
    """Test that missing footerId is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"deleteFooter": {}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "footerid is required" in str(exc_info.value).lower()


def test_delete_footer_nonexistent() -> None:
    """Test that deleting nonexistent footer fails."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"deleteFooter": {"footerId": "nonexistent"}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "footer not found" in str(exc_info.value).lower()


# ========================================================================
# Creation Request Tests
# ========================================================================


def test_create_header_basic() -> None:
    """Test basic header creation."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"createHeader": {"type": "DEFAULT"}}]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert "createHeader" in response["replies"][0]
    assert "headerId" in response["replies"][0]["createHeader"]


def test_create_header_missing_type() -> None:
    """Test that missing type is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"createHeader": {}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "type is required" in str(exc_info.value).lower()


def test_create_footer_basic() -> None:
    """Test basic footer creation."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"createFooter": {"type": "DEFAULT"}}]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert "createFooter" in response["replies"][0]
    assert "footerId" in response["replies"][0]["createFooter"]


def test_create_footer_missing_type() -> None:
    """Test that missing type is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"createFooter": {}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "type is required" in str(exc_info.value).lower()


def test_create_footnote_basic() -> None:
    """Test basic footnote creation."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"createFootnote": {"location": {"index": 1}}}]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert "createFootnote" in response["replies"][0]
    assert "footnoteId" in response["replies"][0]["createFootnote"]


def test_create_footnote_in_header_fails() -> None:
    """Test that creating footnote in header fails."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # First create a header
    create_requests = [{"createHeader": {"type": "DEFAULT"}}]
    create_response = api.batch_update(create_requests)
    header_id = create_response["replies"][0]["createHeader"]["headerId"]

    # Try to create footnote in header
    requests = [{"createFootnote": {"location": {"index": 1, "segmentId": header_id}}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "cannot create footnote" in str(exc_info.value).lower()


def test_create_footnote_missing_location() -> None:
    """Test that missing location is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"createFootnote": {}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "must specify either location" in str(exc_info.value).lower()


def test_add_document_tab_basic() -> None:
    """Test basic document tab addition."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"addDocumentTab": {}}]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert "addDocumentTab" in response["replies"][0]
    assert "tabId" in response["replies"][0]["addDocumentTab"]


def test_add_document_tab_with_properties() -> None:
    """Test adding document tab with properties."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"addDocumentTab": {"tabProperties": {"title": "New Tab", "index": 1}}}]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert "tabId" in response["replies"][0]["addDocumentTab"]


# ========================================================================
# Update Request Tests
# ========================================================================


def test_update_table_column_properties_basic() -> None:
    """Test basic table column properties update."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "updateTableColumnProperties": {
                "tableStartLocation": {"index": 1},
                "tableColumnProperties": {
                    "widthType": "FIXED_WIDTH",
                    "width": {"magnitude": 100, "unit": "PT"},
                },
                "fields": "widthType,width",
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_update_table_column_properties_too_narrow() -> None:
    """Test that too narrow column width is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "updateTableColumnProperties": {
                "tableStartLocation": {"index": 1},
                "tableColumnProperties": {
                    "widthType": "FIXED_WIDTH",
                    "width": {"magnitude": 3, "unit": "PT"},
                },
                "fields": "width",
            }
        }
    ]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "at least 5 points" in str(exc_info.value).lower()


def test_update_table_column_properties_missing_fields() -> None:
    """Test that missing fields is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "updateTableColumnProperties": {
                "tableStartLocation": {"index": 1},
                "tableColumnProperties": {"widthType": "FIXED_WIDTH"},
            }
        }
    ]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "fields is required" in str(exc_info.value).lower()


def test_update_table_cell_style_basic() -> None:
    """Test basic table cell style update."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "updateTableCellStyle": {
                "tableStartLocation": {"index": 1},
                "tableCellStyle": {
                    "backgroundColor": {"color": {"rgbColor": {"red": 1.0}}}
                },
                "fields": "backgroundColor",
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_update_table_cell_style_missing_fields() -> None:
    """Test that missing fields is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "updateTableCellStyle": {
                "tableStartLocation": {"index": 1},
                "tableCellStyle": {"backgroundColor": {}},
            }
        }
    ]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "fields is required" in str(exc_info.value).lower()


def test_update_table_row_style_basic() -> None:
    """Test basic table row style update."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "updateTableRowStyle": {
                "tableStartLocation": {"index": 1},
                "tableRowStyle": {"minRowHeight": {"magnitude": 30, "unit": "PT"}},
                "fields": "minRowHeight",
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_update_table_row_style_missing_fields() -> None:
    """Test that missing fields is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "updateTableRowStyle": {
                "tableStartLocation": {"index": 1},
                "tableRowStyle": {"minRowHeight": {"magnitude": 30}},
            }
        }
    ]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "fields is required" in str(exc_info.value).lower()


def test_update_document_style_basic() -> None:
    """Test basic document style update."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "updateDocumentStyle": {
                "documentStyle": {
                    "background": {
                        "color": {"color": {"rgbColor": {"red": 1.0, "green": 1.0}}}
                    }
                },
                "fields": "background",
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_update_document_style_missing_fields() -> None:
    """Test that missing fields is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"updateDocumentStyle": {"documentStyle": {"background": {}}}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "fields is required" in str(exc_info.value).lower()


def test_update_section_style_basic() -> None:
    """Test basic section style update."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "updateSectionStyle": {
                "range": {"startIndex": 1, "endIndex": 5},
                "sectionStyle": {"columnSeparatorStyle": "BETWEEN_EACH_COLUMN"},
                "fields": "columnSeparatorStyle",
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_update_section_style_in_header_fails() -> None:
    """Test that updating section style in header fails."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # First create a header
    create_requests = [{"createHeader": {"type": "DEFAULT"}}]
    create_response = api.batch_update(create_requests)
    header_id = create_response["replies"][0]["createHeader"]["headerId"]

    # Try to update section style in header
    requests = [
        {
            "updateSectionStyle": {
                "range": {"startIndex": 1, "endIndex": 2, "segmentId": header_id},
                "sectionStyle": {"columnSeparatorStyle": "BETWEEN_EACH_COLUMN"},
                "fields": "columnSeparatorStyle",
            }
        }
    ]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "can only be applied to body" in str(exc_info.value).lower()


def test_update_document_tab_properties_basic() -> None:
    """Test basic document tab properties update."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "updateDocumentTabProperties": {
                "tabProperties": {"tabId": "tab1", "title": "Updated Title"},
                "fields": "title",
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_update_document_tab_properties_missing_tab_id() -> None:
    """Test that missing tabId is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "updateDocumentTabProperties": {
                "tabProperties": {"title": "Updated Title"},
                "fields": "title",
            }
        }
    ]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "tabid is required" in str(exc_info.value).lower()


# ========================================================================
# Table Operation Tests
# ========================================================================


def test_merge_table_cells_basic() -> None:
    """Test basic table cell merging."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "mergeTableCells": {
                "tableRange": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 1},
                        "rowIndex": 0,
                        "columnIndex": 0,
                    },
                    "rowSpan": 2,
                    "columnSpan": 2,
                }
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_merge_table_cells_missing_table_range() -> None:
    """Test that missing tableRange is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"mergeTableCells": {}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "tablerange is required" in str(exc_info.value).lower()


def test_unmerge_table_cells_basic() -> None:
    """Test basic table cell unmerging."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "unmergeTableCells": {
                "tableRange": {
                    "tableCellLocation": {
                        "tableStartLocation": {"index": 1},
                        "rowIndex": 0,
                        "columnIndex": 0,
                    },
                    "rowSpan": 2,
                    "columnSpan": 2,
                }
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_unmerge_table_cells_missing_table_range() -> None:
    """Test that missing tableRange is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"unmergeTableCells": {}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "tablerange is required" in str(exc_info.value).lower()


def test_pin_table_header_rows_basic() -> None:
    """Test basic table header row pinning."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "pinTableHeaderRows": {
                "tableStartLocation": {"index": 1},
                "pinnedHeaderRowsCount": 2,
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_pin_table_header_rows_missing_count() -> None:
    """Test that missing pinnedHeaderRowsCount is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"pinTableHeaderRows": {"tableStartLocation": {"index": 1}}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "pinnedheaderrowscount is required" in str(exc_info.value).lower()


# ========================================================================
# Insertion Request Tests
# ========================================================================


def test_insert_inline_image_basic() -> None:
    """Test basic inline image insertion."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "insertInlineImage": {
                "uri": "https://example.com/image.png",
                "location": {"index": 1},
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert "insertInlineImage" in response["replies"][0]
    assert "objectId" in response["replies"][0]["insertInlineImage"]


def test_insert_inline_image_missing_uri() -> None:
    """Test that missing uri is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"insertInlineImage": {"location": {"index": 1}}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "uri is required" in str(exc_info.value).lower()


def test_insert_inline_image_uri_too_long() -> None:
    """Test that too long URI is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    long_uri = "https://example.com/" + "x" * 2050

    requests = [{"insertInlineImage": {"uri": long_uri, "location": {"index": 1}}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "less than 2 kb" in str(exc_info.value).lower()


def test_insert_page_break_basic() -> None:
    """Test basic page break insertion."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"insertPageBreak": {"location": {"index": 1}}}]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_insert_page_break_in_header_fails() -> None:
    """Test that inserting page break in header fails."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # First create a header
    create_requests = [{"createHeader": {"type": "DEFAULT"}}]
    create_response = api.batch_update(create_requests)
    header_id = create_response["replies"][0]["createHeader"]["headerId"]

    # Try to insert page break in header
    requests = [{"insertPageBreak": {"location": {"index": 1, "segmentId": header_id}}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "cannot insert page break" in str(exc_info.value).lower()


def test_insert_section_break_basic() -> None:
    """Test basic section break insertion."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {"insertSectionBreak": {"location": {"index": 1}, "sectionType": "CONTINUOUS"}}
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_insert_section_break_missing_section_type() -> None:
    """Test that missing sectionType is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"insertSectionBreak": {"location": {"index": 1}}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "sectiontype is required" in str(exc_info.value).lower()


def test_insert_section_break_in_footer_fails() -> None:
    """Test that inserting section break in footer fails."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # First create a footer
    create_requests = [{"createFooter": {"type": "DEFAULT"}}]
    create_response = api.batch_update(create_requests)
    footer_id = create_response["replies"][0]["createFooter"]["footerId"]

    # Try to insert section break in footer
    requests = [
        {
            "insertSectionBreak": {
                "location": {"index": 1, "segmentId": footer_id},
                "sectionType": "CONTINUOUS",
            }
        }
    ]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "cannot insert section break" in str(exc_info.value).lower()


def test_insert_person_basic() -> None:
    """Test basic person insertion."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "insertPerson": {
                "location": {"index": 1},
                "personProperties": {"email": "user@example.com"},
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_insert_person_missing_properties() -> None:
    """Test that missing personProperties is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"insertPerson": {"location": {"index": 1}}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "personproperties is required" in str(exc_info.value).lower()


def test_insert_date_basic() -> None:
    """Test basic date insertion."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "insertDate": {
                "location": {"index": 1},
                "dateElementProperties": {"format": "YYYY-MM-DD"},
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_insert_date_missing_properties() -> None:
    """Test that missing dateElementProperties is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"insertDate": {"location": {"index": 1}}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "dateelementproperties is required" in str(exc_info.value).lower()


# ========================================================================
# Replacement Request Tests
# ========================================================================


def test_replace_image_basic() -> None:
    """Test basic image replacement."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "replaceImage": {
                "imageObjectId": "image123",
                "uri": "https://example.com/newimage.png",
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_replace_image_missing_object_id() -> None:
    """Test that missing imageObjectId is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"replaceImage": {"uri": "https://example.com/image.png"}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "imageobjectid is required" in str(exc_info.value).lower()


def test_replace_image_uri_too_long() -> None:
    """Test that too long URI is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    long_uri = "https://example.com/" + "x" * 2050

    requests = [{"replaceImage": {"imageObjectId": "image123", "uri": long_uri}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "less than 2 kb" in str(exc_info.value).lower()


def test_replace_named_range_content_basic() -> None:
    """Test basic named range content replacement."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "replaceNamedRangeContent": {
                "namedRangeName": "myrange",
                "text": "New content",
            }
        }
    ]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_replace_named_range_content_missing_text() -> None:
    """Test that missing text is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"replaceNamedRangeContent": {"namedRangeName": "myrange"}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "text is required" in str(exc_info.value).lower()


def test_replace_named_range_content_missing_identifier() -> None:
    """Test that missing identifier is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"replaceNamedRangeContent": {"text": "New content"}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "must specify either" in str(exc_info.value).lower()


def test_delete_tab_basic() -> None:
    """Test basic tab deletion."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"deleteTab": {"tabId": "tab1"}}]

    response = api.batch_update(requests)
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}


def test_delete_tab_missing_tab_id() -> None:
    """Test that missing tabId is rejected."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [{"deleteTab": {}}]

    with pytest.raises(ValidationError) as exc_info:
        api.batch_update(requests)

    assert "tabid is required" in str(exc_info.value).lower()
