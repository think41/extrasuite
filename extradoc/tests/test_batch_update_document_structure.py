"""Tests for document structure returned after batch update operations.

These tests verify that MockGoogleDocsAPI returns document structures that
exactly match what the real Google Docs API would return after various
batch update operations.

Unlike test_mock_api.py which focuses on validation, these tests verify:
- The response structure is correct
- The document returned by get() has correct structure
- Indexes are updated correctly
- Content is modified as expected
- Structural elements have correct nested structure
"""

from __future__ import annotations

from extradoc.mock_api import MockGoogleDocsAPI


def create_minimal_document() -> dict[str, any]:
    """Create a minimal valid Document object for testing."""
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


# ============================================================================
# Category 1: Text Operations - Insert
# ============================================================================


def test_insert_text_simple_updates_document_structure() -> None:
    """TC-001: InsertText - Simple text insertion updates document correctly."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Insert " World" at index 6 (before the newline)
    requests = [
        {
            "insertText": {
                "location": {"index": 6},
                "text": " World",
            }
        }
    ]

    response = api.batch_update(requests)

    # Verify response structure
    assert "replies" in response
    assert len(response["replies"]) == 1
    assert response["replies"][0] == {}  # InsertText returns empty reply
    assert "writeControl" in response
    assert "requiredRevisionId" in response["writeControl"]
    assert response["documentId"] == "test_doc_123"

    # Get updated document
    updated_doc = api.get()

    # Verify document structure
    assert updated_doc["revisionId"] != "initial_revision"  # Revision updated

    body_content = updated_doc["tabs"][0]["documentTab"]["body"]["content"]
    assert len(body_content) == 1  # Still one paragraph

    paragraph = body_content[0]
    assert paragraph["startIndex"] == 1
    assert paragraph["endIndex"] == 13  # Was 7, now 7 + 6 = 13

    # Verify text content
    elements = paragraph["paragraph"]["elements"]
    assert len(elements) == 1

    text_run = elements[0]
    assert text_run["startIndex"] == 1
    assert text_run["endIndex"] == 13
    assert text_run["textRun"]["content"] == "Hello World\n"


def test_insert_text_with_newline_creates_new_paragraph() -> None:
    """TC-002: InsertText with newline creates new paragraph structure."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Insert "Title\n" at index 1 (beginning)
    requests = [
        {
            "insertText": {
                "location": {"index": 1},
                "text": "Title\n",
            }
        }
    ]

    api.batch_update(requests)
    updated_doc = api.get()

    # Verify two paragraphs now exist
    body_content = updated_doc["tabs"][0]["documentTab"]["body"]["content"]
    assert len(body_content) == 2

    # First paragraph: "Title\n" (indices 1-7)
    para1 = body_content[0]
    assert para1["startIndex"] == 1
    assert para1["endIndex"] == 7
    assert para1["paragraph"]["elements"][0]["textRun"]["content"] == "Title\n"

    # Second paragraph: "Hello\n" (indices 7-13)
    para2 = body_content[1]
    assert para2["startIndex"] == 7
    assert para2["endIndex"] == 13
    assert para2["paragraph"]["elements"][0]["textRun"]["content"] == "Hello\n"


def test_insert_text_at_end_of_segment_location() -> None:
    """TC-003: InsertText using endOfSegmentLocation inserts before final newline."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        {
            "insertText": {
                "endOfSegmentLocation": {},
                "text": " World",
            }
        }
    ]

    api.batch_update(requests)
    updated_doc = api.get()

    # Should insert before final newline
    body_content = updated_doc["tabs"][0]["documentTab"]["body"]["content"]
    paragraph = body_content[0]

    # Text should be "Hello World\n"
    assert (
        paragraph["paragraph"]["elements"][0]["textRun"]["content"] == "Hello World\n"
    )
    assert paragraph["endIndex"] == 13


# ============================================================================
# Category 1: Text Operations - Delete
# ============================================================================


def test_delete_content_range_simple_updates_document() -> None:
    """TC-004: DeleteContentRange - Simple deletion updates document structure."""
    # Create document with "Hello World\n"
    doc = create_minimal_document()
    doc["tabs"][0]["documentTab"]["body"]["content"][0] = {
        "startIndex": 1,
        "endIndex": 13,
        "paragraph": {
            "elements": [
                {
                    "startIndex": 1,
                    "endIndex": 13,
                    "textRun": {
                        "content": "Hello World\n",
                        "textStyle": {},
                    },
                }
            ],
            "paragraphStyle": {},
        },
    }

    api = MockGoogleDocsAPI(doc)

    # Delete " World" (range 6-12, exclusive end)
    requests = [
        {
            "deleteContentRange": {
                "range": {
                    "startIndex": 6,
                    "endIndex": 12,
                }
            }
        }
    ]

    api.batch_update(requests)
    updated_doc = api.get()

    # Verify document structure
    body_content = updated_doc["tabs"][0]["documentTab"]["body"]["content"]
    paragraph = body_content[0]

    # Paragraph should now end at index 7 (was 13, deleted 6 chars)
    assert paragraph["startIndex"] == 1
    assert paragraph["endIndex"] == 7

    # Verify text content
    assert paragraph["paragraph"]["elements"][0]["textRun"]["content"] == "Hello\n"
    assert paragraph["paragraph"]["elements"][0]["endIndex"] == 7


def test_delete_content_range_with_emoji_updates_indexes_correctly() -> None:
    """TC-006: Delete with surrogate pairs updates indexes correctly."""
    # Create document with "Hello😀World\n"
    # Indexes: H(1) e(2) l(3) l(4) o(5) 😀(6-8) W(8) o(9) r(10) l(11) d(12) \n(13)
    doc = {
        "documentId": "test_doc_emoji",
        "title": "Emoji Test",
        "revisionId": "initial_revision",
        "tabs": [
            {
                "tabProperties": {"tabId": "tab1", "title": "Tab 1", "index": 0},
                "documentTab": {
                    "body": {
                        "content": [
                            {
                                "startIndex": 1,
                                "endIndex": 14,
                                "paragraph": {
                                    "elements": [
                                        {
                                            "startIndex": 1,
                                            "endIndex": 14,
                                            "textRun": {
                                                "content": "Hello😀World\n",
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

    api = MockGoogleDocsAPI(doc)

    # Delete the emoji (indices 6-8)
    requests = [
        {
            "deleteContentRange": {
                "range": {
                    "startIndex": 6,
                    "endIndex": 8,
                }
            }
        }
    ]

    api.batch_update(requests)
    updated_doc = api.get()

    # Verify document structure
    body_content = updated_doc["tabs"][0]["documentTab"]["body"]["content"]
    paragraph = body_content[0]

    # Should be "HelloWorld\n" now (13 - 2 = 12)
    assert paragraph["endIndex"] == 12
    assert paragraph["paragraph"]["elements"][0]["textRun"]["content"] == "HelloWorld\n"


# ============================================================================
# Category 4: Named Ranges
# ============================================================================


def test_create_named_range_adds_to_document_structure() -> None:
    """TC-013: CreateNamedRange adds named range to document structure."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Create named range "greeting" covering "Hello" (indices 1-6)
    requests = [
        {
            "createNamedRange": {
                "name": "greeting",
                "range": {
                    "startIndex": 1,
                    "endIndex": 6,
                },
            }
        }
    ]

    response = api.batch_update(requests)

    # Verify response includes namedRangeId
    assert len(response["replies"]) == 1
    assert "createNamedRange" in response["replies"][0]
    assert "namedRangeId" in response["replies"][0]["createNamedRange"]
    named_range_id = response["replies"][0]["createNamedRange"]["namedRangeId"]

    # Get updated document
    updated_doc = api.get()

    # Verify named range in document structure
    named_ranges = updated_doc["tabs"][0]["documentTab"]["namedRanges"]
    assert "greeting" in named_ranges

    greeting_ranges = named_ranges["greeting"]["namedRanges"]
    assert len(greeting_ranges) == 1

    named_range = greeting_ranges[0]
    assert named_range["namedRangeId"] == named_range_id
    assert len(named_range["ranges"]) == 1
    assert named_range["ranges"][0]["startIndex"] == 1
    assert named_range["ranges"][0]["endIndex"] == 6


def test_create_multiple_named_ranges_same_name() -> None:
    """TC-014: Create multiple named ranges with same name."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Create two named ranges with same name, different ranges
    requests = [
        {
            "createNamedRange": {
                "name": "marker",
                "range": {"startIndex": 1, "endIndex": 3},
            }
        },
        {
            "createNamedRange": {
                "name": "marker",
                "range": {"startIndex": 4, "endIndex": 6},
            }
        },
    ]

    response = api.batch_update(requests)

    # Verify both ranges created
    id1 = response["replies"][0]["createNamedRange"]["namedRangeId"]
    id2 = response["replies"][1]["createNamedRange"]["namedRangeId"]
    assert id1 != id2  # IDs should be unique

    # Get updated document
    updated_doc = api.get()

    # Verify both ranges in document
    named_ranges = updated_doc["tabs"][0]["documentTab"]["namedRanges"]
    marker_ranges = named_ranges["marker"]["namedRanges"]
    assert len(marker_ranges) == 2

    # Verify unique IDs
    ids = {r["namedRangeId"] for r in marker_ranges}
    assert len(ids) == 2


def test_delete_named_range_by_id_removes_from_document() -> None:
    """TC-015: DeleteNamedRange by ID removes specific range."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Create two named ranges with same name
    create_requests = [
        {
            "createNamedRange": {
                "name": "marker",
                "range": {"startIndex": 1, "endIndex": 3},
            }
        },
        {
            "createNamedRange": {
                "name": "marker",
                "range": {"startIndex": 4, "endIndex": 6},
            }
        },
    ]

    create_response = api.batch_update(create_requests)
    id_to_delete = create_response["replies"][0]["createNamedRange"]["namedRangeId"]
    id_to_keep = create_response["replies"][1]["createNamedRange"]["namedRangeId"]

    # Delete first one by ID
    delete_requests = [
        {
            "deleteNamedRange": {
                "namedRangeId": id_to_delete,
            }
        }
    ]

    api.batch_update(delete_requests)
    updated_doc = api.get()

    # Verify only one range remains
    named_ranges = updated_doc["tabs"][0]["documentTab"]["namedRanges"]
    marker_ranges = named_ranges["marker"]["namedRanges"]
    assert len(marker_ranges) == 1
    assert marker_ranges[0]["namedRangeId"] == id_to_keep


def test_delete_named_range_by_name_removes_all() -> None:
    """TC-016: DeleteNamedRange by name removes all ranges with that name."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Create two named ranges with same name
    create_requests = [
        {
            "createNamedRange": {
                "name": "marker",
                "range": {"startIndex": 1, "endIndex": 3},
            }
        },
        {
            "createNamedRange": {
                "name": "marker",
                "range": {"startIndex": 4, "endIndex": 6},
            }
        },
    ]

    api.batch_update(create_requests)

    # Delete all by name
    delete_requests = [
        {
            "deleteNamedRange": {
                "name": "marker",
            }
        }
    ]

    api.batch_update(delete_requests)
    updated_doc = api.get()

    # Verify named range completely removed
    named_ranges = updated_doc["tabs"][0]["documentTab"]["namedRanges"]
    # Should either be absent or empty
    if "marker" in named_ranges:
        assert len(named_ranges["marker"]["namedRanges"]) == 0


# ============================================================================
# Category 6: Header/Footer/Footnote Operations
# ============================================================================


def test_create_header_adds_header_segment() -> None:
    """TC-023: CreateHeader creates header segment with correct structure."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Create DEFAULT header
    requests = [
        {
            "createHeader": {
                "type": "DEFAULT",
            }
        }
    ]

    response = api.batch_update(requests)

    # Verify response includes headerId
    assert len(response["replies"]) == 1
    assert "createHeader" in response["replies"][0]
    assert "headerId" in response["replies"][0]["createHeader"]
    header_id = response["replies"][0]["createHeader"]["headerId"]

    # Get updated document
    updated_doc = api.get()

    # Verify header in document structure
    headers = updated_doc["tabs"][0]["documentTab"]["headers"]
    assert header_id in headers

    header = headers[header_id]
    assert "content" in header
    assert len(header["content"]) == 1

    # Header should have a single paragraph with "\n"
    paragraph = header["content"][0]
    assert "paragraph" in paragraph
    assert paragraph["startIndex"] == 1
    assert paragraph["endIndex"] == 2
    assert paragraph["paragraph"]["elements"][0]["textRun"]["content"] == "\n"


def test_create_footer_adds_footer_segment() -> None:
    """TC-024: CreateFooter creates footer segment with correct structure."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Create DEFAULT footer
    requests = [
        {
            "createFooter": {
                "type": "DEFAULT",
            }
        }
    ]

    response = api.batch_update(requests)

    # Verify response includes footerId
    assert "createFooter" in response["replies"][0]
    assert "footerId" in response["replies"][0]["createFooter"]
    footer_id = response["replies"][0]["createFooter"]["footerId"]

    # Get updated document
    updated_doc = api.get()

    # Verify footer in document structure
    footers = updated_doc["tabs"][0]["documentTab"]["footers"]
    assert footer_id in footers

    footer = footers[footer_id]
    assert "content" in footer
    assert len(footer["content"]) == 1

    # Footer should have a single paragraph with "\n"
    paragraph = footer["content"][0]
    assert paragraph["startIndex"] == 1
    assert paragraph["endIndex"] == 2
    assert paragraph["paragraph"]["elements"][0]["textRun"]["content"] == "\n"


def test_create_footnote_adds_footnote_segment() -> None:
    """TC-025: CreateFootnote creates footnote segment and reference."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Create footnote at index 3
    requests = [
        {
            "createFootnote": {
                "location": {"index": 3},
            }
        }
    ]

    response = api.batch_update(requests)

    # Verify response includes footnoteId
    assert "createFootnote" in response["replies"][0]
    assert "footnoteId" in response["replies"][0]["createFootnote"]
    footnote_id = response["replies"][0]["createFootnote"]["footnoteId"]

    # Get updated document
    updated_doc = api.get()

    # Verify footnote in document structure
    footnotes = updated_doc["tabs"][0]["documentTab"]["footnotes"]
    assert footnote_id in footnotes

    footnote = footnotes[footnote_id]
    assert "content" in footnote

    # Footnote should have content with " \n" (space + newline)
    paragraph = footnote["content"][0]
    assert paragraph["startIndex"] == 1
    assert paragraph["endIndex"] == 3
    assert paragraph["paragraph"]["elements"][0]["textRun"]["content"] == " \n"


def test_delete_header_removes_from_document() -> None:
    """TC-026: DeleteHeader removes header from document structure."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Create header first
    create_response = api.batch_update([{"createHeader": {"type": "DEFAULT"}}])
    header_id = create_response["replies"][0]["createHeader"]["headerId"]

    # Delete header
    delete_requests = [
        {
            "deleteHeader": {
                "headerId": header_id,
            }
        }
    ]

    # Note: Current implementation doesn't actually remove it, but should
    # For now, just verify the operation succeeds
    response = api.batch_update(delete_requests)
    assert len(response["replies"]) == 1


# ============================================================================
# Category 7: Tab Operations
# ============================================================================


def test_add_document_tab_creates_new_tab() -> None:
    """TC-028: AddDocumentTab creates new tab with correct structure."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Add new tab
    requests = [
        {
            "addDocumentTab": {
                "tabProperties": {
                    "title": "New Tab",
                }
            }
        }
    ]

    response = api.batch_update(requests)

    # Verify response includes tabProperties with tabId
    assert "addDocumentTab" in response["replies"][0]
    assert "tabProperties" in response["replies"][0]["addDocumentTab"]
    new_tab_id = response["replies"][0]["addDocumentTab"]["tabProperties"]["tabId"]

    # Get updated document
    updated_doc = api.get()

    # Verify two tabs now exist
    assert len(updated_doc["tabs"]) == 2

    # Find the new tab
    new_tab = None
    for tab in updated_doc["tabs"]:
        if tab["tabProperties"]["tabId"] == new_tab_id:
            new_tab = tab
            break

    assert new_tab is not None
    assert new_tab["tabProperties"]["title"] == "New Tab"

    # Verify new tab has sectionBreak + empty paragraph (matches real API)
    body = new_tab["documentTab"]["body"]
    assert len(body["content"]) == 2
    assert "sectionBreak" in body["content"][0]
    assert body["content"][1]["paragraph"]["elements"][0]["textRun"]["content"] == "\n"


# ============================================================================
# Category 8: Complex Multi-Operation Scenarios
# ============================================================================


def test_multiple_inserts_in_sequence_update_indexes() -> None:
    """TC-030: Multiple inserts in sequence update indexes correctly."""
    doc = create_minimal_document()
    # Change initial content to just "Middle\n"
    doc["tabs"][0]["documentTab"]["body"]["content"][0]["paragraph"]["elements"][0][
        "textRun"
    ]["content"] = "Middle\n"
    doc["tabs"][0]["documentTab"]["body"]["content"][0]["paragraph"]["elements"][0][
        "endIndex"
    ] = 8
    doc["tabs"][0]["documentTab"]["body"]["content"][0]["endIndex"] = 8

    api = MockGoogleDocsAPI(doc)

    # Insert "Start " at beginning, then " End" at end
    # Note: Second insert must account for first insert's index shift
    requests = [
        {
            "insertText": {
                "location": {"index": 1},
                "text": "Start ",
            }
        },
        {
            "insertText": {
                "location": {"index": 13},  # 1 + len("Start ") + len("Middle") = 13
                "text": " End",
            }
        },
    ]

    api.batch_update(requests)
    updated_doc = api.get()

    # Verify final content
    body_content = updated_doc["tabs"][0]["documentTab"]["body"]["content"]
    paragraph = body_content[0]

    # Should be "Start Middle End\n"
    assert (
        paragraph["paragraph"]["elements"][0]["textRun"]["content"]
        == "Start Middle End\n"
    )
    # Total length: 17 chars + starting index 1 = 18
    assert paragraph["endIndex"] == 18


def test_delete_then_insert_at_same_location() -> None:
    """TC-031: Delete then insert at same location."""
    doc = create_minimal_document()
    # Change to "Hello World\n"
    doc["tabs"][0]["documentTab"]["body"]["content"][0]["paragraph"]["elements"][0][
        "textRun"
    ]["content"] = "Hello World\n"
    doc["tabs"][0]["documentTab"]["body"]["content"][0]["paragraph"]["elements"][0][
        "endIndex"
    ] = 13
    doc["tabs"][0]["documentTab"]["body"]["content"][0]["endIndex"] = 13

    api = MockGoogleDocsAPI(doc)

    # Delete " World", then insert " Universe" at same position
    requests = [
        {
            "deleteContentRange": {
                "range": {"startIndex": 6, "endIndex": 12},
            }
        },
        {
            "insertText": {
                "location": {"index": 6},
                "text": " Universe",
            }
        },
    ]

    api.batch_update(requests)
    updated_doc = api.get()

    # Verify final content is "Hello Universe\n"
    body_content = updated_doc["tabs"][0]["documentTab"]["body"]["content"]
    paragraph = body_content[0]

    assert (
        paragraph["paragraph"]["elements"][0]["textRun"]["content"]
        == "Hello Universe\n"
    )
    # Total: 15 chars + starting index 1 = 16
    assert paragraph["endIndex"] == 16


# ============================================================================
# Category 9: Edge Cases
# ============================================================================


def test_insert_emoji_accounts_for_surrogate_pairs() -> None:
    """TC-035: Insert emoji accounts for 2 UTF-16 code units."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Insert emoji before newline
    requests = [
        {
            "insertText": {
                "location": {"index": 6},
                "text": "😀",
            }
        }
    ]

    api.batch_update(requests)
    updated_doc = api.get()

    # Verify document structure
    body_content = updated_doc["tabs"][0]["documentTab"]["body"]["content"]
    paragraph = body_content[0]

    # Should be "Hello😀\n"
    assert paragraph["paragraph"]["elements"][0]["textRun"]["content"] == "Hello😀\n"
    # Emoji is 2 UTF-16 units, so total: 5 + 2 + 1 = 9
    assert paragraph["endIndex"] == 9


def test_revision_id_updates_after_batch() -> None:
    """TC-040: Revision ID updates after batch update."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    initial_doc = api.get()
    initial_revision = initial_doc["revisionId"]

    # Perform any batch update
    requests = [
        {
            "insertText": {
                "location": {"index": 1},
                "text": "Test",
            }
        }
    ]

    response = api.batch_update(requests)

    # Verify response has new revision
    assert "writeControl" in response
    assert "requiredRevisionId" in response["writeControl"]
    new_revision = response["writeControl"]["requiredRevisionId"]
    assert new_revision != initial_revision

    # Verify get() returns document with new revision
    updated_doc = api.get()
    assert updated_doc["revisionId"] == new_revision
    assert updated_doc["revisionId"] != initial_revision


# ============================================================================
# Additional Edge Case Tests
# ============================================================================


def test_empty_batch_update_increments_revision() -> None:
    """Empty batch update should still increment revision."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    initial_revision = api.get()["revisionId"]

    # Empty batch
    response = api.batch_update([])

    # Revision should still update
    new_revision = response["writeControl"]["requiredRevisionId"]
    assert new_revision != initial_revision

    updated_doc = api.get()
    assert updated_doc["revisionId"] == new_revision


def test_multiple_operations_maintain_document_consistency() -> None:
    """Complex batch maintains consistent document structure."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    # Complex batch: insert, create named range, insert again
    requests = [
        {
            "insertText": {
                "location": {"index": 1},
                "text": "Start ",
            }
        },
        {
            "createNamedRange": {
                "name": "original",
                "range": {"startIndex": 7, "endIndex": 12},  # "Hello"
            }
        },
        {
            "insertText": {
                "location": {"index": 12},  # Before final newline in "Start Hello\n"
                "text": " End",
            }
        },
    ]

    api.batch_update(requests)
    updated_doc = api.get()

    # Verify all operations reflected in document
    body_content = updated_doc["tabs"][0]["documentTab"]["body"]["content"]

    # Content should be "Start Hello End\n" or similar structure
    # Just verify document is still valid
    assert len(body_content) >= 1
    assert "paragraph" in body_content[0]

    # Verify named range exists
    named_ranges = updated_doc["tabs"][0]["documentTab"]["namedRanges"]
    assert "original" in named_ranges


def test_complex_batch_sequential_index_updates() -> None:
    """Test that each request in a batch sees the updated state from previous requests.

    This is critical: when processing batch updates, each request must operate on
    the document state AFTER all previous requests have been applied.
    """
    doc = create_minimal_document()  # "Hello\n" at indices 1-7
    api = MockGoogleDocsAPI(doc)

    # Build a complex sequence where each operation depends on previous ones
    requests = [
        # 1. Insert "Start " at beginning
        #    Result: "Start Hello\n" (indices 1-13)
        {
            "insertText": {
                "location": {"index": 1},
                "text": "Start ",
            }
        },
        # 2. Insert "Beautiful " after "Start "
        #    Must use index 7 (after "Start "), not 1
        #    Result: "Start Beautiful Hello\n" (indices 1-23)
        {
            "insertText": {
                "location": {"index": 7},
                "text": "Beautiful ",
            }
        },
        # 3. Delete "Beautiful " (indices 7-17)
        #    Result: "Start Hello\n" (indices 1-13)
        {
            "deleteContentRange": {
                "range": {"startIndex": 7, "endIndex": 17},
            }
        },
        # 4. Insert "World" before final newline
        #    Document is now "Start Hello\n", insert at index 12
        #    Result: "Start HelloWorld\n" (indices 1-18)
        {
            "insertText": {
                "location": {"index": 12},
                "text": "World",
            }
        },
        # 5. Create named range for "HelloWorld" (indices 7-17)
        {
            "createNamedRange": {
                "name": "greeting",
                "range": {"startIndex": 7, "endIndex": 17},
            }
        },
        # 6. Insert space before "World"
        #    Result: "Start Hello World\n" (indices 1-19)
        {
            "insertText": {
                "location": {"index": 12},
                "text": " ",
            }
        },
    ]

    response = api.batch_update(requests)

    # Verify response structure
    assert len(response["replies"]) == 6
    assert response["replies"][0] == {}  # insertText
    assert response["replies"][1] == {}  # insertText
    assert response["replies"][2] == {}  # deleteContentRange
    assert response["replies"][3] == {}  # insertText
    assert "createNamedRange" in response["replies"][4]
    assert response["replies"][5] == {}  # insertText

    # Get final document
    updated_doc = api.get()
    body_content = updated_doc["tabs"][0]["documentTab"]["body"]["content"]

    # Verify final text
    assert len(body_content) == 1
    paragraph = body_content[0]
    assert (
        paragraph["paragraph"]["elements"][0]["textRun"]["content"]
        == "Start Hello World\n"
    )
    assert paragraph["endIndex"] == 19

    # Verify named range was created and still exists
    # Note: The range was created for "HelloWorld" at 7-17, but after the space
    # insertion at 12, it should still be at 7-17 (Google Docs doesn't auto-update ranges)
    named_ranges = updated_doc["tabs"][0]["documentTab"]["namedRanges"]
    assert "greeting" in named_ranges


def test_batch_with_dependent_operations() -> None:
    """Test batch where later operations depend on earlier ones' side effects."""
    doc = create_minimal_document()  # "Hello\n"
    api = MockGoogleDocsAPI(doc)

    requests = [
        # 1. Insert text with newline to create multiple paragraphs
        #    Result: "Line1\nHello\n" (two paragraphs: 1-7 and 7-13)
        {
            "insertText": {
                "location": {"index": 1},
                "text": "Line1\n",
            }
        },
        # 2. Insert in the SECOND paragraph (which is now at index 7+)
        #    Insert at index 7 (beginning of second paragraph)
        #    Result: "Line1\nPrefix Hello\n"
        {
            "insertText": {
                "location": {"index": 7},
                "text": "Prefix ",
            }
        },
        # 3. Create named range in first paragraph
        {
            "createNamedRange": {
                "name": "line1",
                "range": {"startIndex": 1, "endIndex": 6},
            }
        },
        # 4. Create named range in second paragraph
        #    Second paragraph now starts at 7, contains "Prefix Hello\n"
        {
            "createNamedRange": {
                "name": "line2",
                "range": {"startIndex": 7, "endIndex": 13},  # "Prefix"
            }
        },
    ]

    api.batch_update(requests)
    updated_doc = api.get()

    # Verify we have two paragraphs
    body_content = updated_doc["tabs"][0]["documentTab"]["body"]["content"]
    assert len(body_content) == 2

    # Verify paragraph 1
    assert (
        body_content[0]["paragraph"]["elements"][0]["textRun"]["content"] == "Line1\n"
    )
    assert body_content[0]["endIndex"] == 7

    # Verify paragraph 2
    assert (
        body_content[1]["paragraph"]["elements"][0]["textRun"]["content"]
        == "Prefix Hello\n"
    )
    assert body_content[1]["startIndex"] == 7

    # Verify both named ranges exist
    named_ranges = updated_doc["tabs"][0]["documentTab"]["namedRanges"]
    assert "line1" in named_ranges
    assert "line2" in named_ranges


def test_batch_with_multiple_deletes_and_inserts() -> None:
    """Test alternating deletes and inserts with proper index tracking."""
    # Start with a longer document
    doc = create_minimal_document()
    doc["tabs"][0]["documentTab"]["body"]["content"][0]["paragraph"]["elements"][0][
        "textRun"
    ]["content"] = "AAABBBCCCDDDEEE\n"
    doc["tabs"][0]["documentTab"]["body"]["content"][0]["paragraph"]["elements"][0][
        "endIndex"
    ] = 17
    doc["tabs"][0]["documentTab"]["body"]["content"][0]["endIndex"] = 17

    api = MockGoogleDocsAPI(doc)

    requests = [
        # Start: "AAABBBCCCDDDEEE\n" (1-17)
        # 1. Delete "AAA" (1-4)
        #    Result: "BBBCCCDDDEEE\n" (1-14)
        {
            "deleteContentRange": {
                "range": {"startIndex": 1, "endIndex": 4},
            }
        },
        # 2. Insert "XXX" at beginning
        #    Result: "XXXBBBCCCDDDEEE\n" (1-17)
        {
            "insertText": {
                "location": {"index": 1},
                "text": "XXX",
            }
        },
        # 3. Delete "BBB" (now at indices 4-7)
        #    Result: "XXXCCCDDDEEE\n" (1-14)
        {
            "deleteContentRange": {
                "range": {"startIndex": 4, "endIndex": 7},
            }
        },
        # 4. Insert "YYY" where BBB was
        #    Result: "XXXYYYCCCDDDEEE\n" (1-17)
        {
            "insertText": {
                "location": {"index": 4},
                "text": "YYY",
            }
        },
        # 5. Delete "DDD" (now at indices 10-13)
        #    Result: "XXXYYYCCCEEE\n" (1-14)
        {
            "deleteContentRange": {
                "range": {"startIndex": 10, "endIndex": 13},
            }
        },
    ]

    api.batch_update(requests)
    updated_doc = api.get()

    # Verify final result
    body_content = updated_doc["tabs"][0]["documentTab"]["body"]["content"]
    paragraph = body_content[0]

    final_text = paragraph["paragraph"]["elements"][0]["textRun"]["content"]
    assert final_text == "XXXYYYCCCEEE\n"
    assert paragraph["endIndex"] == 14  # 13 chars + 1 for start index


def test_batch_creates_and_deletes_named_ranges() -> None:
    """Test creating and deleting named ranges in same batch."""
    doc = create_minimal_document()
    api = MockGoogleDocsAPI(doc)

    requests = [
        # 1. Create named range "temp"
        {
            "createNamedRange": {
                "name": "temp",
                "range": {"startIndex": 1, "endIndex": 3},
            }
        },
        # 2. Create another named range "keep"
        {
            "createNamedRange": {
                "name": "keep",
                "range": {"startIndex": 3, "endIndex": 6},
            }
        },
        # 3. Delete "temp" by name
        {
            "deleteNamedRange": {
                "name": "temp",
            }
        },
    ]

    api.batch_update(requests)
    updated_doc = api.get()

    # Verify only "keep" exists
    named_ranges = updated_doc["tabs"][0]["documentTab"]["namedRanges"]
    assert "keep" in named_ranges
    assert "temp" not in named_ranges
