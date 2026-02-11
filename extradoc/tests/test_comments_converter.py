"""Tests for comments converter module."""

from __future__ import annotations

import json
from typing import Any

from extradoc.comments_converter import (
    CommentOperations,
    CommentRefPosition,
    NewComment,
    NewReply,
    ResolveComment,
    _build_anchor_json,
    _parse_anchor,
    compute_comment_ref_positions,
    convert_comments_to_xml,
    diff_comments,
    extract_comment_ref_ids,
    parse_comments_xml,
)

# --- Fixtures ---


def _make_comment(
    comment_id: str = "AAA",
    content: str = "Test comment",
    resolved: bool = False,
    deleted: bool = False,
    anchor: str | None = None,
    quoted_text: str = "",
    author_name: str = "Test User",
    author_email: str = "test@example.com",
    replies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    comment: dict[str, Any] = {
        "id": comment_id,
        "content": content,
        "resolved": resolved,
        "deleted": deleted,
        "author": {
            "displayName": author_name,
            "emailAddress": author_email,
        },
        "createdTime": "2025-01-15T10:30:00Z",
        "replies": replies or [],
    }
    if anchor:
        comment["anchor"] = anchor
    if quoted_text:
        comment["quotedFileContent"] = {
            "mimeType": "text/plain",
            "value": quoted_text,
        }
    return comment


def _make_reply(
    reply_id: str = "BBB",
    content: str = "Test reply",
    deleted: bool = False,
) -> dict[str, Any]:
    return {
        "id": reply_id,
        "content": content,
        "deleted": deleted,
        "author": {
            "displayName": "Reply Author",
            "emailAddress": "reply@example.com",
        },
        "createdTime": "2025-01-15T11:00:00Z",
    }


# --- convert_comments_to_xml tests ---


class TestConvertCommentsToXml:
    def test_basic_comment(self) -> None:
        comments = [_make_comment()]
        xml = convert_comments_to_xml(comments, "doc123")
        assert '<?xml version="1.0" encoding="UTF-8"?>' in xml
        assert 'fileId="doc123"' in xml
        assert 'id="AAA"' in xml
        assert 'author="Test User &lt;test@example.com&gt;"' in xml
        assert 'resolved="false"' in xml
        assert "<content>Test comment</content>" in xml

    def test_no_position_info(self) -> None:
        """comments.xml should NOT contain startIndex/endIndex or anchor."""
        anchor = '{"r":"head","a":[{"txt":{"o":42,"l":13}}]}'
        comments = [_make_comment(anchor=anchor, quoted_text="sample")]
        xml = convert_comments_to_xml(comments, "doc123")
        assert "startIndex" not in xml
        assert "endIndex" not in xml
        assert "<anchor" not in xml

    def test_comment_with_replies(self) -> None:
        replies = [_make_reply("R1", "First reply"), _make_reply("R2", "Second reply")]
        comments = [_make_comment(replies=replies)]
        xml = convert_comments_to_xml(comments, "doc123")
        assert "<replies>" in xml
        assert 'id="R1"' in xml
        assert 'id="R2"' in xml
        assert "First reply" in xml
        assert "Second reply" in xml

    def test_resolved_comment(self) -> None:
        comments = [_make_comment(resolved=True)]
        xml = convert_comments_to_xml(comments, "doc123")
        assert 'resolved="true"' in xml

    def test_deleted_comment_excluded(self) -> None:
        comments = [_make_comment(deleted=True)]
        xml = convert_comments_to_xml(comments, "doc123")
        assert 'id="AAA"' not in xml

    def test_deleted_reply_excluded(self) -> None:
        replies = [
            _make_reply("R1", "Visible"),
            _make_reply("R2", "Deleted", deleted=True),
        ]
        comments = [_make_comment(replies=replies)]
        xml = convert_comments_to_xml(comments, "doc123")
        assert 'id="R1"' in xml
        assert 'id="R2"' not in xml

    def test_empty_comments(self) -> None:
        xml = convert_comments_to_xml([], "doc123")
        assert '<?xml version="1.0" encoding="UTF-8"?>' in xml
        assert 'fileId="doc123"' in xml
        assert "<comment " not in xml

    def test_comment_author_without_email(self) -> None:
        comment = _make_comment()
        comment["author"] = {"displayName": "NoEmail User"}
        xml = convert_comments_to_xml([comment], "doc123")
        assert 'author="NoEmail User"' in xml


# --- parse_comments_xml tests ---


class TestParseCommentsXml:
    def test_parse_basic(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<comments fileId="doc123">
  <comment id="AAA" resolved="false">
    <content>Test comment</content>
  </comment>
</comments>"""
        file_id, comments = parse_comments_xml(xml)
        assert file_id == "doc123"
        assert len(comments) == 1
        assert comments[0]["id"] == "AAA"
        assert comments[0]["content"] == "Test comment"
        assert comments[0]["resolved"] is False

    def test_parse_new_comment_no_id(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<comments fileId="doc123">
  <comment>
    <content>New comment</content>
  </comment>
</comments>"""
        _, comments = parse_comments_xml(xml)
        assert len(comments) == 1
        assert "id" not in comments[0]
        assert comments[0]["content"] == "New comment"

    def test_parse_new_reply_no_id(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<comments fileId="doc123">
  <comment id="AAA">
    <replies>
      <reply id="R1">Existing reply</reply>
      <reply>New reply</reply>
    </replies>
  </comment>
</comments>"""
        _, comments = parse_comments_xml(xml)
        replies = comments[0]["replies"]
        assert len(replies) == 2
        assert replies[0]["id"] == "R1"
        assert "id" not in replies[1]
        assert replies[1]["content"] == "New reply"

    def test_parse_resolve(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<comments fileId="doc123">
  <comment id="AAA" resolved="true"/>
</comments>"""
        _, comments = parse_comments_xml(xml)
        assert comments[0]["resolved"] is True


# --- _parse_anchor tests ---


class TestParseAnchor:
    def test_basic_anchor(self) -> None:
        anchor = '{"r":"head","a":[{"txt":{"o":42,"l":13}}]}'
        start, end = _parse_anchor(anchor)
        assert start == 42
        assert end == 55

    def test_none_anchor(self) -> None:
        start, end = _parse_anchor(None)
        assert start is None
        assert end is None

    def test_empty_anchor(self) -> None:
        start, end = _parse_anchor("")
        assert start is None
        assert end is None

    def test_invalid_json(self) -> None:
        start, end = _parse_anchor("not json")
        assert start is None
        assert end is None

    def test_missing_txt_field(self) -> None:
        anchor = '{"r":"head","a":[{"other":{}}]}'
        start, end = _parse_anchor(anchor)
        assert start is None
        assert end is None

    def test_missing_a_field(self) -> None:
        anchor = '{"r":"head"}'
        start, end = _parse_anchor(anchor)
        assert start is None
        assert end is None


# --- _build_anchor_json tests ---


class TestBuildAnchorJson:
    def test_basic(self) -> None:
        result = _build_anchor_json(10, 25, "some text")
        parsed = json.loads(result)
        assert parsed["r"] == "head"
        assert parsed["a"][0]["txt"]["o"] == 10
        assert parsed["a"][0]["txt"]["l"] == 15

    def test_roundtrip(self) -> None:
        original_start, original_end = 42, 55
        anchor_json = _build_anchor_json(original_start, original_end)
        start, end = _parse_anchor(anchor_json)
        assert start == original_start
        assert end == original_end


# --- extract_comment_ref_ids tests ---


class TestExtractCommentRefIds:
    def test_finds_ids(self) -> None:
        xml = '<p>Hello <comment-ref id="abc">world</comment-ref></p>'
        ids = extract_comment_ref_ids(xml)
        assert ids == {"abc"}

    def test_multiple_ids(self) -> None:
        xml = (
            '<p><comment-ref id="a1">one</comment-ref> and '
            '<comment-ref id="b2">two</comment-ref></p>'
        )
        ids = extract_comment_ref_ids(xml)
        assert ids == {"a1", "b2"}

    def test_no_comment_refs(self) -> None:
        xml = "<p>No comments here</p>"
        ids = extract_comment_ref_ids(xml)
        assert ids == set()


# --- compute_comment_ref_positions tests ---


def _make_doc(body_content: str) -> str:
    return f'<doc id="d" revision="r"><tab id="t.0" title="Tab 1"><body class="_base">{body_content}</body></tab></doc>'


class TestComputeCommentRefPositions:
    def test_single_comment_ref(self) -> None:
        # Body starts at index 1. "Hello " = 6 chars, "world" = 5 chars
        doc = _make_doc('<p>Hello <comment-ref id="c1">world</comment-ref></p>')
        positions = compute_comment_ref_positions(doc)
        assert len(positions) == 1
        assert positions[0].comment_ref_id == "c1"
        assert positions[0].start_index == 7  # 1 (body start) + 6 ("Hello ")
        assert positions[0].end_index == 12  # 7 + 5 ("world")
        assert positions[0].quoted_text == "world"

    def test_comment_ref_with_formatting(self) -> None:
        # "Hello " = 6, then <b>world</b> = 5 chars of text
        doc = _make_doc('<p>Hello <comment-ref id="c1"><b>world</b></comment-ref></p>')
        positions = compute_comment_ref_positions(doc)
        assert len(positions) == 1
        assert positions[0].start_index == 7
        assert positions[0].end_index == 12
        assert positions[0].quoted_text == "world"

    def test_no_comment_refs(self) -> None:
        doc = _make_doc("<p>Hello world</p>")
        positions = compute_comment_ref_positions(doc)
        assert positions == []

    def test_comment_ref_at_start(self) -> None:
        doc = _make_doc('<p><comment-ref id="c1">Hello</comment-ref> world</p>')
        positions = compute_comment_ref_positions(doc)
        assert len(positions) == 1
        assert positions[0].start_index == 1  # body starts at 1
        assert positions[0].end_index == 6  # 1 + 5 ("Hello")

    def test_emoji_text(self) -> None:
        # Emoji U+1F600 takes 2 UTF-16 code units
        doc = _make_doc('<p>\U0001f600<comment-ref id="c1">hi</comment-ref></p>')
        positions = compute_comment_ref_positions(doc)
        assert len(positions) == 1
        assert positions[0].start_index == 3  # 1 + 2 (emoji)
        assert positions[0].end_index == 5  # 3 + 2 ("hi")

    def test_multiple_paragraphs(self) -> None:
        # First para: "First" = 5 + 1 newline = 6
        # Second para starts at 1+6=7, "Hello " = 6, comment at 13
        doc = _make_doc(
            '<p>First</p><p>Hello <comment-ref id="c1">world</comment-ref></p>'
        )
        positions = compute_comment_ref_positions(doc)
        assert len(positions) == 1
        assert positions[0].start_index == 13  # 1 + 6 + 6 = 13
        assert positions[0].end_index == 18


# --- diff_comments tests ---


class TestDiffComments:
    def test_new_comment_with_position(self) -> None:
        """New comment with matching comment-ref position."""
        pristine = """<?xml version="1.0" encoding="UTF-8"?>
<comments fileId="doc123">
  <comment id="AAA" resolved="false">
    <content>Existing comment</content>
  </comment>
</comments>"""
        current = """<?xml version="1.0" encoding="UTF-8"?>
<comments fileId="doc123">
  <comment id="AAA" resolved="false">
    <content>Existing comment</content>
  </comment>
  <comment id="new1">
    <content>New comment</content>
  </comment>
</comments>"""
        positions = [
            CommentRefPosition(
                comment_ref_id="new1",
                start_index=10,
                end_index=20,
                quoted_text="some text",
            )
        ]
        ops = diff_comments(pristine, current, positions)
        assert len(ops.new_comments) == 1
        assert ops.new_comments[0].content == "New comment"
        assert ops.new_comments[0].start_index == 10
        assert ops.new_comments[0].end_index == 20
        assert ops.new_comments[0].quoted_text == "some text"

    def test_new_comment_without_position(self) -> None:
        """New comment without any comment-ref (unanchored)."""
        pristine = """<?xml version="1.0" encoding="UTF-8"?>
<comments fileId="doc123"/>"""
        current = """<?xml version="1.0" encoding="UTF-8"?>
<comments fileId="doc123">
  <comment id="new1">
    <content>General comment</content>
  </comment>
</comments>"""
        ops = diff_comments(pristine, current)
        assert len(ops.new_comments) == 1
        assert ops.new_comments[0].start_index is None
        assert ops.new_comments[0].end_index is None

    def test_new_reply_detected(self) -> None:
        pristine = """<?xml version="1.0" encoding="UTF-8"?>
<comments fileId="doc123">
  <comment id="AAA" resolved="false">
    <content>Existing</content>
    <replies>
      <reply id="R1">Old reply</reply>
    </replies>
  </comment>
</comments>"""
        current = """<?xml version="1.0" encoding="UTF-8"?>
<comments fileId="doc123">
  <comment id="AAA" resolved="false">
    <content>Existing</content>
    <replies>
      <reply id="R1">Old reply</reply>
      <reply>New reply text</reply>
    </replies>
  </comment>
</comments>"""
        ops = diff_comments(pristine, current)
        assert len(ops.new_replies) == 1
        assert ops.new_replies[0].comment_id == "AAA"
        assert ops.new_replies[0].content == "New reply text"

    def test_resolve_detected(self) -> None:
        pristine = """<?xml version="1.0" encoding="UTF-8"?>
<comments fileId="doc123">
  <comment id="AAA" resolved="false">
    <content>Needs work</content>
  </comment>
</comments>"""
        current = """<?xml version="1.0" encoding="UTF-8"?>
<comments fileId="doc123">
  <comment id="AAA" resolved="true"/>
</comments>"""
        ops = diff_comments(pristine, current)
        assert len(ops.resolves) == 1
        assert ops.resolves[0].comment_id == "AAA"

    def test_already_resolved_not_detected(self) -> None:
        pristine = """<?xml version="1.0" encoding="UTF-8"?>
<comments fileId="doc123">
  <comment id="AAA" resolved="true">
    <content>Already done</content>
  </comment>
</comments>"""
        current = """<?xml version="1.0" encoding="UTF-8"?>
<comments fileId="doc123">
  <comment id="AAA" resolved="true"/>
</comments>"""
        ops = diff_comments(pristine, current)
        assert len(ops.resolves) == 0

    def test_no_pristine(self) -> None:
        current = """<?xml version="1.0" encoding="UTF-8"?>
<comments fileId="doc123">
  <comment id="new1">
    <content>Brand new comment</content>
  </comment>
</comments>"""
        ops = diff_comments(None, current)
        assert len(ops.new_comments) == 1

    def test_no_changes(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<comments fileId="doc123">
  <comment id="AAA" resolved="false">
    <content>Unchanged</content>
  </comment>
</comments>"""
        ops = diff_comments(xml, xml)
        assert not ops.has_operations

    def test_combined_operations(self) -> None:
        pristine = """<?xml version="1.0" encoding="UTF-8"?>
<comments fileId="doc123">
  <comment id="AAA" resolved="false">
    <content>Comment A</content>
  </comment>
  <comment id="BBB" resolved="false">
    <content>Comment B</content>
  </comment>
</comments>"""
        current = """<?xml version="1.0" encoding="UTF-8"?>
<comments fileId="doc123">
  <comment id="AAA" resolved="true"/>
  <comment id="BBB" resolved="false">
    <content>Comment B</content>
    <replies>
      <reply>New reply</reply>
    </replies>
  </comment>
  <comment id="new1">
    <content>New comment</content>
  </comment>
</comments>"""
        ops = diff_comments(pristine, current)
        assert len(ops.resolves) == 1
        assert len(ops.new_replies) == 1
        assert len(ops.new_comments) == 1
        assert ops.has_operations


# --- CommentOperations tests ---


class TestCommentOperations:
    def test_has_operations_empty(self) -> None:
        ops = CommentOperations()
        assert not ops.has_operations

    def test_has_operations_with_comments(self) -> None:
        ops = CommentOperations(new_comments=[NewComment("test")])
        assert ops.has_operations

    def test_has_operations_with_replies(self) -> None:
        ops = CommentOperations(new_replies=[NewReply("AAA", "reply")])
        assert ops.has_operations

    def test_has_operations_with_resolves(self) -> None:
        ops = CommentOperations(resolves=[ResolveComment("AAA")])
        assert ops.has_operations


# --- Roundtrip test ---


class TestRoundtrip:
    def test_convert_then_parse(self) -> None:
        """Converting API response to XML and parsing back preserves structure."""
        comments = [
            _make_comment(
                comment_id="C1",
                content="First comment",
                anchor='{"r":"head","a":[{"txt":{"o":10,"l":5}}]}',
                quoted_text="hello",
                replies=[
                    _make_reply("R1", "Reply one"),
                    _make_reply("R2", "Reply two"),
                ],
            ),
            _make_comment(
                comment_id="C2",
                content="Second comment",
                resolved=True,
            ),
        ]
        xml = convert_comments_to_xml(comments, "doc456")
        file_id, parsed = parse_comments_xml(xml)

        assert file_id == "doc456"
        assert len(parsed) == 2

        # First comment
        assert parsed[0]["id"] == "C1"
        assert parsed[0]["content"] == "First comment"
        assert parsed[0]["resolved"] is False
        # No position info in simplified format
        assert "startIndex" not in parsed[0]
        assert "endIndex" not in parsed[0]
        assert len(parsed[0]["replies"]) == 2

        # Second comment
        assert parsed[1]["id"] == "C2"
        assert parsed[1]["content"] == "Second comment"
        assert parsed[1]["resolved"] is True
