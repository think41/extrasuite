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
    requests = [
        {"insertText": {"location": {"index": 1}, "text": "Hi"}}
    ]

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

    requests = [
        {"deleteParagraphBullets": {"range": {"startIndex": 1, "endIndex": 5}}}
    ]

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
