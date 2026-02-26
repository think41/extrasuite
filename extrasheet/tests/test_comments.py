"""Tests for the comments module."""

from __future__ import annotations

import json
import zipfile
from typing import TYPE_CHECKING

import pytest

from extrasheet import LocalFileTransport, SheetsClient
from extrasheet.comments import (
    diff_comments,
    group_comments_by_sheet,
    parse_anchor_sheet_uid,
    parse_comments_json,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Tests for parse_anchor_sheet_uid
# ---------------------------------------------------------------------------


class TestParseAnchorSheetUid:
    """Tests for extracting sheet UID from Drive API anchor JSON."""

    def test_basic_workbook_range(self) -> None:
        """Parses a standard workbook-range anchor."""
        anchor = json.dumps({"type": "workbook-range", "uid": 0, "range": "153741113"})
        assert parse_anchor_sheet_uid(anchor) == 0

    def test_nonzero_uid(self) -> None:
        """Returns the correct non-zero sheet UID."""
        anchor = json.dumps({"type": "workbook-range", "uid": 123456, "range": "999"})
        assert parse_anchor_sheet_uid(anchor) == 123456

    def test_wrong_type(self) -> None:
        """Returns None for non-workbook-range anchor types."""
        anchor = json.dumps({"type": "other", "uid": 0, "range": "1"})
        assert parse_anchor_sheet_uid(anchor) is None

    def test_no_type(self) -> None:
        """Returns None when type field is missing."""
        anchor = json.dumps({"uid": 0, "range": "1"})
        assert parse_anchor_sheet_uid(anchor) is None

    def test_no_uid(self) -> None:
        """Returns None when uid field is missing."""
        anchor = json.dumps({"type": "workbook-range", "range": "1"})
        assert parse_anchor_sheet_uid(anchor) is None

    def test_invalid_json(self) -> None:
        """Returns None for invalid JSON."""
        assert parse_anchor_sheet_uid("not json") is None

    def test_empty_string(self) -> None:
        """Returns None for empty string."""
        assert parse_anchor_sheet_uid("") is None

    def test_docs_style_anchor(self) -> None:
        """Returns None for Docs-style kix anchor (not a workbook-range)."""
        assert parse_anchor_sheet_uid("kix.abcdef123") is None

    def test_old_grid_anchor(self) -> None:
        """Returns None for old-style grid anchor format."""
        anchor = json.dumps({"r": "head", "a": [{"g": {"ro": 0, "co": 0, "s": 0}}]})
        assert parse_anchor_sheet_uid(anchor) is None


# ---------------------------------------------------------------------------
# Tests for group_comments_by_sheet
# ---------------------------------------------------------------------------


def _make_anchor(sheet_uid: int, range_id: str = "12345") -> str:
    return json.dumps({"type": "workbook-range", "uid": sheet_uid, "range": range_id})


def _make_comment(
    comment_id: str,
    content: str,
    sheet_uid: int,
    quoted_content: str = "",
    *,
    resolved: bool = False,
    deleted: bool = False,
    replies: list[dict] | None = None,
) -> dict:
    """Create a mock Drive API comment dict."""
    comment: dict = {
        "id": comment_id,
        "anchor": _make_anchor(sheet_uid),
        "content": content,
        "resolved": resolved,
        "deleted": deleted,
        "createdTime": "2024-01-01T00:00:00.000Z",
        "author": {
            "displayName": "Test User",
            "emailAddress": "test@example.com",
        },
    }
    if quoted_content:
        comment["quotedFileContent"] = {"mimeType": "text/html", "value": quoted_content}
    if replies:
        comment["replies"] = replies
    return comment


class TestGroupCommentsBySheet:
    """Tests for grouping Drive API comments by sheet."""

    def test_single_comment(self) -> None:
        """Single comment maps to correct sheet folder."""
        comments = [_make_comment("c1", "Hello", sheet_uid=0, quoted_content="Phone")]
        result = group_comments_by_sheet(comments, "file1", {0: "Sheet1"})
        assert "Sheet1" in result
        assert result["Sheet1"]["fileId"] == "file1"
        assert len(result["Sheet1"]["comments"]) == 1
        c = result["Sheet1"]["comments"][0]
        assert c["id"] == "c1"
        assert c["content"] == "Hello"
        assert c["quotedContent"] == "Phone"

    def test_no_quoted_content(self) -> None:
        """Comment without quotedFileContent omits quotedContent field."""
        comments = [_make_comment("c1", "Hello", sheet_uid=0)]
        result = group_comments_by_sheet(comments, "file1", {0: "Sheet1"})
        c = result["Sheet1"]["comments"][0]
        assert "quotedContent" not in c

    def test_deleted_comment_skipped(self) -> None:
        """Deleted comments are not included."""
        comments = [_make_comment("c1", "Hello", sheet_uid=0, deleted=True)]
        result = group_comments_by_sheet(comments, "file1", {0: "Sheet1"})
        assert not result

    def test_comments_on_different_sheets(self) -> None:
        """Comments on different sheets go to different folders."""
        comments = [
            _make_comment("c1", "Sheet1 comment", sheet_uid=0),
            _make_comment("c2", "Sheet2 comment", sheet_uid=999),
        ]
        result = group_comments_by_sheet(comments, "file1", {0: "Sheet1", 999: "Summary"})
        assert "Sheet1" in result
        assert "Summary" in result
        assert result["Sheet1"]["comments"][0]["id"] == "c1"
        assert result["Summary"]["comments"][0]["id"] == "c2"

    def test_unknown_sheet_uid_skipped(self) -> None:
        """Comments whose UID doesn't match any known sheet are skipped."""
        comments = [_make_comment("c1", "Hello", sheet_uid=999)]
        result = group_comments_by_sheet(comments, "file1", {0: "Sheet1"})
        assert not result

    def test_invalid_anchor_skipped(self) -> None:
        """Comments with unparseable anchors are skipped."""
        comment = {
            "id": "c1",
            "anchor": "not-valid-json",
            "content": "Hello",
            "resolved": False,
            "deleted": False,
            "createdTime": "2024-01-01T00:00:00.000Z",
            "author": {"displayName": "User", "emailAddress": "u@example.com"},
        }
        result = group_comments_by_sheet([comment], "file1", {0: "Sheet1"})
        assert not result

    def test_reply_included(self) -> None:
        """Non-deleted replies are included."""
        reply = {
            "id": "r1",
            "content": "A reply",
            "deleted": False,
            "createdTime": "2024-01-01T01:00:00.000Z",
            "author": {"displayName": "Replier", "emailAddress": "r@example.com"},
        }
        comments = [_make_comment("c1", "Main", sheet_uid=0, replies=[reply])]
        result = group_comments_by_sheet(comments, "file1", {0: "Sheet1"})
        c = result["Sheet1"]["comments"][0]
        assert len(c["replies"]) == 1
        assert c["replies"][0]["id"] == "r1"
        assert c["replies"][0]["content"] == "A reply"
        assert c["replies"][0]["author"] == "Replier <r@example.com>"

    def test_deleted_reply_excluded(self) -> None:
        """Deleted replies are not included."""
        reply = {
            "id": "r1",
            "content": "Deleted",
            "deleted": True,
            "createdTime": "2024-01-01T01:00:00.000Z",
            "author": {"displayName": "Replier", "emailAddress": ""},
        }
        comments = [_make_comment("c1", "Main", sheet_uid=0, replies=[reply])]
        result = group_comments_by_sheet(comments, "file1", {0: "Sheet1"})
        c = result["Sheet1"]["comments"][0]
        assert "replies" not in c

    def test_author_with_email(self) -> None:
        """Author with email uses 'Name <email>' format."""
        comments = [_make_comment("c1", "Hello", sheet_uid=0)]
        result = group_comments_by_sheet(comments, "file1", {0: "Sheet1"})
        assert result["Sheet1"]["comments"][0]["author"] == "Test User <test@example.com>"

    def test_author_without_email(self) -> None:
        """Author without email uses name only."""
        comment = {
            "id": "c1",
            "anchor": _make_anchor(0),
            "content": "Hello",
            "resolved": False,
            "deleted": False,
            "createdTime": "2024-01-01T00:00:00.000Z",
            "author": {"displayName": "No Email User", "emailAddress": ""},
        }
        result = group_comments_by_sheet([comment], "file1", {0: "Sheet1"})
        assert result["Sheet1"]["comments"][0]["author"] == "No Email User"

    def test_resolved_comment(self) -> None:
        """Resolved status is preserved."""
        comments = [_make_comment("c1", "Hello", sheet_uid=0, resolved=True)]
        result = group_comments_by_sheet(comments, "file1", {0: "Sheet1"})
        assert result["Sheet1"]["comments"][0]["resolved"] is True


# ---------------------------------------------------------------------------
# Tests for parse_comments_json
# ---------------------------------------------------------------------------


class TestParseCommentsJson:
    """Tests for parsing comments.json content."""

    def test_basic_parse(self) -> None:
        data = {
            "fileId": "abc",
            "comments": [{"id": "c1", "content": "Hello", "resolved": False}],
        }
        file_id, comments = parse_comments_json(json.dumps(data))
        assert file_id == "abc"
        assert len(comments) == 1
        assert comments[0]["id"] == "c1"

    def test_empty_comments(self) -> None:
        data = {"fileId": "abc", "comments": []}
        file_id, comments = parse_comments_json(json.dumps(data))
        assert file_id == "abc"
        assert comments == []


# ---------------------------------------------------------------------------
# Tests for diff_comments
# ---------------------------------------------------------------------------


def _make_comments_json(
    file_id: str = "file1",
    comments: list[dict] | None = None,
) -> str:
    return json.dumps({"fileId": file_id, "comments": comments or []})


class TestDiffComments:
    """Tests for detecting changes between pristine and current comments.json."""

    def test_no_changes(self) -> None:
        data = _make_comments_json(
            comments=[{"id": "c1", "content": "Hello", "resolved": False}]
        )
        ops = diff_comments(data, data)
        assert not ops.has_operations

    def test_new_reply(self) -> None:
        """Detects a new reply (reply without id)."""
        pristine = _make_comments_json(
            comments=[{"id": "c1", "content": "Hello", "resolved": False}]
        )
        current = _make_comments_json(
            comments=[
                {
                    "id": "c1",
                    "content": "Hello",
                    "resolved": False,
                    "replies": [{"content": "New reply"}],
                }
            ]
        )
        ops = diff_comments(pristine, current)
        assert len(ops.new_replies) == 1
        assert ops.new_replies[0].comment_id == "c1"
        assert ops.new_replies[0].content == "New reply"

    def test_existing_reply_not_duplicated(self) -> None:
        """Replies with an existing id are not treated as new."""
        data = _make_comments_json(
            comments=[
                {
                    "id": "c1",
                    "content": "Hello",
                    "resolved": False,
                    "replies": [{"id": "r1", "content": "Old reply"}],
                }
            ]
        )
        ops = diff_comments(data, data)
        assert not ops.new_replies

    def test_resolve_comment(self) -> None:
        """Detects a comment that was resolved."""
        pristine = _make_comments_json(
            comments=[{"id": "c1", "content": "Hello", "resolved": False}]
        )
        current = _make_comments_json(
            comments=[{"id": "c1", "content": "Hello", "resolved": True}]
        )
        ops = diff_comments(pristine, current)
        assert len(ops.resolves) == 1
        assert ops.resolves[0].comment_id == "c1"

    def test_already_resolved_not_duplicated(self) -> None:
        data = _make_comments_json(
            comments=[{"id": "c1", "content": "Hello", "resolved": True}]
        )
        ops = diff_comments(data, data)
        assert not ops.resolves

    def test_new_top_level_comment_ignored(self) -> None:
        """New top-level comments (no id) are silently ignored."""
        pristine = _make_comments_json(comments=[])
        current = _make_comments_json(
            comments=[{"content": "New comment without id"}]
        )
        ops = diff_comments(pristine, current)
        assert not ops.has_operations

    def test_pristine_none(self) -> None:
        """Works when pristine is None (no prior comments)."""
        current = _make_comments_json(
            comments=[{"id": "c1", "content": "Hello", "resolved": False}]
        )
        ops = diff_comments(None, current)
        assert not ops.has_operations

    def test_multiple_operations(self) -> None:
        pristine = _make_comments_json(
            comments=[
                {"id": "c1", "content": "Open", "resolved": False},
                {"id": "c2", "content": "Will resolve", "resolved": False},
            ]
        )
        current = _make_comments_json(
            comments=[
                {
                    "id": "c1",
                    "content": "Open",
                    "resolved": False,
                    "replies": [{"content": "My reply"}],
                },
                {"id": "c2", "content": "Will resolve", "resolved": True},
            ]
        )
        ops = diff_comments(pristine, current)
        assert len(ops.new_replies) == 1
        assert ops.new_replies[0].comment_id == "c1"
        assert len(ops.resolves) == 1
        assert ops.resolves[0].comment_id == "c2"


# ---------------------------------------------------------------------------
# Integration: pull with comments via LocalFileTransport
# ---------------------------------------------------------------------------


@pytest.fixture
def golden_dir(tmp_path: Path) -> Path:
    """Create a golden directory with a spreadsheet and Drive API comments."""
    golden = tmp_path / "golden"
    golden.mkdir()
    spreadsheet_dir = golden / "test_sheet"
    spreadsheet_dir.mkdir()

    metadata = {
        "spreadsheetId": "test_sheet",
        "properties": {"title": "Test Sheet"},
        "sheets": [
            {
                "properties": {
                    "sheetId": 0,
                    "title": "Sheet1",
                    "gridProperties": {"rowCount": 10, "columnCount": 5},
                }
            }
        ],
    }
    (spreadsheet_dir / "metadata.json").write_text(json.dumps(metadata))

    data = {
        "spreadsheetId": "test_sheet",
        "sheets": [
            {
                "properties": {
                    "sheetId": 0,
                    "title": "Sheet1",
                    "gridProperties": {"rowCount": 10, "columnCount": 5},
                },
                "data": [
                    {
                        "startRow": 0,
                        "startColumn": 0,
                        "rowData": [
                            {"values": [{"userEnteredValue": {"stringValue": "Name"}}]},
                            {"values": [{"userEnteredValue": {"stringValue": "Alice"}}]},
                        ],
                    }
                ],
            }
        ],
    }
    (spreadsheet_dir / "data.json").write_text(json.dumps(data))

    # Drive API comment format (workbook-range anchor)
    comments_raw = {
        "comments": [
            {
                "id": "comment1",
                "anchor": json.dumps(
                    {"type": "workbook-range", "uid": 0, "range": "12345"}
                ),
                "content": "Check this cell",
                "resolved": False,
                "deleted": False,
                "createdTime": "2024-01-01T00:00:00.000Z",
                "quotedFileContent": {"mimeType": "text/html", "value": "Alice"},
                "author": {
                    "displayName": "Alice",
                    "emailAddress": "alice@example.com",
                },
                "replies": [],
            }
        ]
    }
    (spreadsheet_dir / "comments.json").write_text(json.dumps(comments_raw))

    return golden


@pytest.mark.asyncio
async def test_pull_creates_comments_json(golden_dir: Path, tmp_path: Path) -> None:
    """Pull creates per-sheet comments.json when comments exist."""
    transport = LocalFileTransport(golden_dir)
    client = SheetsClient(transport)

    output = tmp_path / "output"
    output.mkdir()

    await client.pull("test_sheet", output)

    comments_path = output / "test_sheet" / "Sheet1" / "comments.json"
    assert comments_path.exists(), "comments.json should be created for Sheet1"

    data = json.loads(comments_path.read_text())
    assert data["fileId"] == "test_sheet"
    assert len(data["comments"]) == 1
    c = data["comments"][0]
    assert c["id"] == "comment1"
    assert c["content"] == "Check this cell"
    assert c["quotedContent"] == "Alice"
    assert c["author"] == "Alice <alice@example.com>"
    assert "anchor" not in c


@pytest.mark.asyncio
async def test_pull_no_comments_no_file(golden_dir: Path, tmp_path: Path) -> None:
    """Pull does NOT create comments.json when there are no comments."""
    (golden_dir / "test_sheet" / "comments.json").unlink()

    transport = LocalFileTransport(golden_dir)
    client = SheetsClient(transport)

    output = tmp_path / "output"
    output.mkdir()

    await client.pull("test_sheet", output)

    comments_path = output / "test_sheet" / "Sheet1" / "comments.json"
    assert not comments_path.exists()


@pytest.mark.asyncio
async def test_pull_includes_comments_in_pristine(golden_dir: Path, tmp_path: Path) -> None:
    """Pull includes comments.json in the pristine zip."""
    transport = LocalFileTransport(golden_dir)
    client = SheetsClient(transport)

    output = tmp_path / "output"
    output.mkdir()

    await client.pull("test_sheet", output)

    pristine_zip = output / "test_sheet" / ".pristine" / "spreadsheet.zip"
    with zipfile.ZipFile(pristine_zip, "r") as zf:
        assert "Sheet1/comments.json" in zf.namelist()


# ---------------------------------------------------------------------------
# Integration: diff detects comment changes
# ---------------------------------------------------------------------------


def _create_pristine_zip(folder: Path, files: dict[str, str]) -> None:
    pristine_dir = folder / ".pristine"
    pristine_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pristine_dir / "spreadsheet.zip", "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)


def _write_files(folder: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


class TestDiffAllComments:
    """Integration tests for comment diff via SheetsClient.diff()."""

    def _spreadsheet_json(self) -> str:
        return json.dumps(
            {
                "spreadsheetId": "test",
                "title": "Test",
                "sheets": [{"sheetId": 0, "title": "Sheet1", "folder": "Sheet1"}],
            }
        )

    def test_no_comments_files(self, tmp_path: Path) -> None:
        """No comment ops when no comments.json exist."""
        pristine_files = {
            "spreadsheet.json": self._spreadsheet_json(),
            "Sheet1/data.tsv": "A\tB\n1\t2\n",
        }
        _create_pristine_zip(tmp_path, pristine_files)
        _write_files(tmp_path, pristine_files)

        client = SheetsClient.__new__(SheetsClient)
        _, _, _, comment_ops = client.diff(tmp_path)
        assert not any(ops.has_operations for ops in comment_ops.values())

    def test_new_reply_detected(self, tmp_path: Path) -> None:
        """diff() detects a new reply added to a comment."""
        pristine_comments = json.dumps(
            {
                "fileId": "test",
                "comments": [{"id": "c1", "content": "Hello", "resolved": False}],
            }
        )
        current_comments = json.dumps(
            {
                "fileId": "test",
                "comments": [
                    {
                        "id": "c1",
                        "content": "Hello",
                        "resolved": False,
                        "replies": [{"content": "My reply"}],
                    }
                ],
            }
        )

        pristine_files = {
            "spreadsheet.json": self._spreadsheet_json(),
            "Sheet1/data.tsv": "A\n1\n",
            "Sheet1/comments.json": pristine_comments,
        }
        current_files = {
            "spreadsheet.json": self._spreadsheet_json(),
            "Sheet1/data.tsv": "A\n1\n",
            "Sheet1/comments.json": current_comments,
        }

        _create_pristine_zip(tmp_path, pristine_files)
        _write_files(tmp_path, current_files)

        client = SheetsClient.__new__(SheetsClient)
        _, _, _, comment_ops = client.diff(tmp_path)

        assert "Sheet1" in comment_ops
        ops = comment_ops["Sheet1"]
        assert len(ops.new_replies) == 1
        assert ops.new_replies[0].comment_id == "c1"
        assert ops.new_replies[0].content == "My reply"

    def test_resolve_detected(self, tmp_path: Path) -> None:
        """diff() detects a comment being resolved."""
        pristine_comments = json.dumps(
            {
                "fileId": "test",
                "comments": [{"id": "c1", "content": "Hello", "resolved": False}],
            }
        )
        current_comments = json.dumps(
            {
                "fileId": "test",
                "comments": [{"id": "c1", "content": "Hello", "resolved": True}],
            }
        )

        pristine_files = {
            "spreadsheet.json": self._spreadsheet_json(),
            "Sheet1/data.tsv": "A\n1\n",
            "Sheet1/comments.json": pristine_comments,
        }
        current_files = {
            "spreadsheet.json": self._spreadsheet_json(),
            "Sheet1/data.tsv": "A\n1\n",
            "Sheet1/comments.json": current_comments,
        }

        _create_pristine_zip(tmp_path, pristine_files)
        _write_files(tmp_path, current_files)

        client = SheetsClient.__new__(SheetsClient)
        _, _, _, comment_ops = client.diff(tmp_path)

        assert "Sheet1" in comment_ops
        ops = comment_ops["Sheet1"]
        assert len(ops.resolves) == 1
        assert ops.resolves[0].comment_id == "c1"
