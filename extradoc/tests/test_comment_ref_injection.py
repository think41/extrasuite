"""Tests for comment-ref injection in xml_converter."""

from __future__ import annotations

from typing import Any

from extradoc.comments_converter import compute_comment_ref_positions
from extradoc.xml_converter import convert_document_to_xml


def _make_api_doc(
    body_elements: list[dict[str, Any]],
    doc_id: str = "test_doc",
) -> dict[str, Any]:
    """Build a minimal Google Docs API response."""
    return {
        "documentId": doc_id,
        "title": "Test Document",
        "revisionId": "rev1",
        "tabs": [
            {
                "tabProperties": {"tabId": "t.0", "title": ""},
                "documentTab": {
                    "body": {"content": body_elements},
                    "headers": {},
                    "footers": {},
                    "footnotes": {},
                    "lists": {},
                    "namedStyles": {
                        "styles": [
                            {
                                "namedStyleType": "NORMAL_TEXT",
                                "paragraphStyle": {},
                                "textStyle": {},
                            }
                        ]
                    },
                },
            }
        ],
        "namedStyles": {
            "styles": [
                {
                    "namedStyleType": "NORMAL_TEXT",
                    "paragraphStyle": {},
                    "textStyle": {},
                }
            ]
        },
    }


def _make_paragraph(
    text: str, start_index: int, style: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build a paragraph element with a single text run."""
    text_with_newline = text + "\n"
    end_index = start_index + len(text_with_newline)
    return {
        "startIndex": start_index,
        "endIndex": end_index,
        "paragraph": {
            "elements": [
                {
                    "startIndex": start_index,
                    "endIndex": end_index,
                    "textRun": {
                        "content": text_with_newline,
                        "textStyle": style or {},
                    },
                }
            ],
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
        },
    }


def _make_paragraph_multi_runs(
    runs: list[tuple[str, int, int, dict[str, Any]]],
    para_start: int,
) -> dict[str, Any]:
    """Build a paragraph element with multiple text runs.

    runs: list of (text, start_index, end_index, text_style)
    """
    elements = []
    for text, si, ei, style in runs:
        elements.append(
            {
                "startIndex": si,
                "endIndex": ei,
                "textRun": {
                    "content": text,
                    "textStyle": style,
                },
            }
        )
    last_end = runs[-1][2] if runs else para_start
    return {
        "startIndex": para_start,
        "endIndex": last_end,
        "paragraph": {
            "elements": elements,
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
        },
    }


def _make_comment(
    comment_id: str,
    content: str,
    start_offset: int,
    length: int,
    resolved: bool = False,
    replies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a Drive API comment with anchor."""
    anchor = f'{{"r":"head","a":[{{"txt":{{"o":{start_offset},"l":{length}}}}}]}}'
    return {
        "id": comment_id,
        "content": content,
        "anchor": anchor,
        "author": {"displayName": "Test", "emailAddress": "test@test.com"},
        "createdTime": "2025-01-01T00:00:00Z",
        "resolved": resolved,
        "deleted": False,
        "quotedFileContent": {"mimeType": "text/plain", "value": ""},
        "replies": replies or [],
    }


class TestCommentRefInjection:
    def test_no_comments(self) -> None:
        """Without comments, document.xml has no comment-ref tags."""
        doc = _make_api_doc([{"sectionBreak": {}}, _make_paragraph("Hello world", 1)])
        xml, _ = convert_document_to_xml(doc)
        assert "comment-ref" not in xml
        assert "Hello world" in xml

    def test_empty_comments_list(self) -> None:
        """Empty comments list produces no comment-ref tags."""
        doc = _make_api_doc([{"sectionBreak": {}}, _make_paragraph("Hello world", 1)])
        xml, _ = convert_document_to_xml(doc, comments=[])
        assert "comment-ref" not in xml

    def test_single_comment_within_text_run(self) -> None:
        """Comment covering part of a text run inserts comment-ref."""
        # "Hello world\n" starts at index 1, "world" at index 7-12
        doc = _make_api_doc([{"sectionBreak": {}}, _make_paragraph("Hello world", 1)])
        comments = [_make_comment("c1", "Nice word", 7, 5)]
        xml, _ = convert_document_to_xml(doc, comments=comments)
        assert '<comment-ref id="c1"' in xml
        assert "world</comment-ref>" in xml
        assert "Hello " in xml  # text before comment

    def test_comment_at_start_of_paragraph(self) -> None:
        """Comment starting at beginning of paragraph text."""
        doc = _make_api_doc([{"sectionBreak": {}}, _make_paragraph("Hello world", 1)])
        # "Hello" at index 1-6
        comments = [_make_comment("c1", "Greeting", 1, 5)]
        xml, _ = convert_document_to_xml(doc, comments=comments)
        assert '<comment-ref id="c1"' in xml
        assert "Hello</comment-ref>" in xml

    def test_comment_covering_entire_text_run(self) -> None:
        """Comment spans the full text of a run."""
        doc = _make_api_doc([{"sectionBreak": {}}, _make_paragraph("Hello", 1)])
        # "Hello" at index 1-6
        comments = [_make_comment("c1", "All of it", 1, 5)]
        xml, _ = convert_document_to_xml(doc, comments=comments)
        assert '<comment-ref id="c1"' in xml
        assert "Hello</comment-ref>" in xml

    def test_comment_across_multiple_text_runs(self) -> None:
        """Comment spans across two text runs with different formatting."""
        # "Hello" (plain) + "world\n" (bold), comment covers "lo wor"
        runs = [
            ("Hello", 1, 6, {}),
            ("world\n", 6, 12, {"bold": True}),
        ]
        doc = _make_api_doc([{"sectionBreak": {}}, _make_paragraph_multi_runs(runs, 1)])
        # "lo" at index 4-6, "wor" at index 6-9
        comments = [_make_comment("c1", "Spanning", 4, 5)]
        xml, _ = convert_document_to_xml(doc, comments=comments)
        assert '<comment-ref id="c1"' in xml
        assert "</comment-ref>" in xml

    def test_unanchored_comment_no_injection(self) -> None:
        """Comment without anchor produces no comment-ref."""
        doc = _make_api_doc([{"sectionBreak": {}}, _make_paragraph("Hello world", 1)])
        comments = [
            {
                "id": "c1",
                "content": "General note",
                "author": {"displayName": "Test"},
                "createdTime": "2025-01-01T00:00:00Z",
                "resolved": False,
                "deleted": False,
                "replies": [],
            }
        ]
        xml, _ = convert_document_to_xml(doc, comments=comments)
        assert "comment-ref" not in xml

    def test_deleted_comment_no_injection(self) -> None:
        """Deleted comment is skipped."""
        doc = _make_api_doc([{"sectionBreak": {}}, _make_paragraph("Hello world", 1)])
        comments = [
            {
                "id": "c1",
                "content": "Deleted",
                "anchor": '{"r":"head","a":[{"txt":{"o":1,"l":5}}]}',
                "author": {"displayName": "Test"},
                "createdTime": "2025-01-01T00:00:00Z",
                "resolved": False,
                "deleted": True,
                "replies": [],
            }
        ]
        xml, _ = convert_document_to_xml(doc, comments=comments)
        assert "comment-ref" not in xml

    def test_resolved_comment_still_injected(self) -> None:
        """Resolved comment still appears as comment-ref."""
        doc = _make_api_doc([{"sectionBreak": {}}, _make_paragraph("Hello world", 1)])
        comments = [_make_comment("c1", "Resolved", 1, 5, resolved=True)]
        xml, _ = convert_document_to_xml(doc, comments=comments)
        assert '<comment-ref id="c1"' in xml
        assert 'resolved="true"' in xml

    def test_comment_ref_attributes(self) -> None:
        """Verify comment-ref includes message, replies, resolved attributes."""
        doc = _make_api_doc([{"sectionBreak": {}}, _make_paragraph("Hello world", 1)])
        replies = [
            {
                "id": "r1",
                "content": "Reply",
                "author": {"displayName": "R"},
                "createdTime": "2025-01-01T00:00:00Z",
                "deleted": False,
            },
            {
                "id": "r2",
                "content": "Reply 2",
                "author": {"displayName": "R"},
                "createdTime": "2025-01-01T00:00:00Z",
                "deleted": False,
            },
        ]
        comments = [
            _make_comment("c1", "A long comment message here", 1, 5, replies=replies)
        ]
        xml, _ = convert_document_to_xml(doc, comments=comments)
        assert 'message="A long comment messa..."' in xml
        assert 'replies="2"' in xml
        assert 'resolved="false"' in xml

    def test_bold_text_with_comment(self) -> None:
        """Comment on text that has bold formatting."""
        runs = [
            ("Hello\n", 1, 7, {"bold": True}),
        ]
        doc = _make_api_doc([{"sectionBreak": {}}, _make_paragraph_multi_runs(runs, 1)])
        comments = [_make_comment("c1", "Bold comment", 1, 5)]
        xml, _ = convert_document_to_xml(doc, comments=comments)
        assert '<comment-ref id="c1"' in xml
        # The bold formatting should be inside the comment-ref
        # (may also have span class wrapping due to style factorization)
        assert "<b>Hello</b>" in xml
        assert "</comment-ref>" in xml


class TestCommentRefRoundtrip:
    """Test that injected comment-refs produce correct positions when re-computed."""

    def test_position_roundtrip(self) -> None:
        """Inject comment-ref during pull, then compute positions — should match original."""
        doc = _make_api_doc([{"sectionBreak": {}}, _make_paragraph("Hello world", 1)])
        # Comment on "world" at index 7-12
        comments = [_make_comment("c1", "Test", 7, 5)]
        xml, _ = convert_document_to_xml(doc, comments=comments)

        positions = compute_comment_ref_positions(xml)
        assert len(positions) == 1
        assert positions[0].comment_ref_id == "c1"
        assert positions[0].start_index == 7
        assert positions[0].end_index == 12
        assert positions[0].quoted_text == "world"

    def test_position_roundtrip_multiple_paragraphs(self) -> None:
        """Roundtrip across multiple paragraphs."""
        doc = _make_api_doc(
            [
                {"sectionBreak": {}},
                _make_paragraph("First line", 1),
                _make_paragraph("Second line", 12),
            ]
        )
        # Comment on "Second" at index 12-18
        comments = [_make_comment("c1", "Test", 12, 6)]
        xml, _ = convert_document_to_xml(doc, comments=comments)

        positions = compute_comment_ref_positions(xml)
        assert len(positions) == 1
        assert positions[0].start_index == 12
        assert positions[0].end_index == 18
        assert positions[0].quoted_text == "Second"
