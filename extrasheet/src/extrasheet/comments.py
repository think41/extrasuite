"""Comments support for Google Sheets via Drive API v3.

Handles conversion between Drive API v3 comment responses and the
comments.json format used by extrasheet for agent interaction.

## Anchor Format

Google Sheets Drive API v3 comments use an opaque anchor format:
    {"type":"workbook-range","uid":<sheet_uid>,"range":"<opaque_int>"}

The `uid` field identifies the sheet (matches sheetId from the Sheets API).
The `range` field is an internal opaque integer — it cannot be decoded to
A1 notation without Google's internal metadata.

Because of this, comments.json stores `quotedContent` (the cell value that
was highlighted when the comment was created) as context, rather than an
A1 range. The exact cell position is not available.

## Supported Operations (on push)

- Add a reply: add an entry to `replies` without an `id` field
- Resolve a comment: set `"resolved": true`
- Create new top-level comments: NOT supported (cannot build the opaque anchor)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NewReply:
    """A new reply to add to an existing comment."""

    comment_id: str
    content: str


@dataclass
class ResolveComment:
    """A comment to resolve."""

    comment_id: str


@dataclass
class CommentOperations:
    """Operations extracted from diff between pristine and current comments.json."""

    new_replies: list[NewReply] = field(default_factory=list)
    resolves: list[ResolveComment] = field(default_factory=list)

    @property
    def has_operations(self) -> bool:
        return bool(self.new_replies or self.resolves)


def parse_anchor_sheet_uid(anchor_str: str) -> int | None:
    """Extract the sheet UID from a Drive API anchor JSON string.

    For Google Sheets, the anchor format is:
        {"type":"workbook-range","uid":<sheet_uid>,"range":"<opaque_int>"}

    The uid field identifies which sheet the comment belongs to and
    corresponds to the sheetId from the Google Sheets API.

    Args:
        anchor_str: JSON anchor string from Drive API

    Returns:
        Sheet UID (int), or None if the anchor cannot be parsed.
    """
    try:
        anchor_data = json.loads(anchor_str)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None

    if anchor_data.get("type") != "workbook-range":
        return None

    uid = anchor_data.get("uid")
    if uid is None:
        return None

    return int(uid)


def group_comments_by_sheet(
    comments: list[dict[str, Any]],
    file_id: str,
    sheet_id_to_folder: dict[int, str],
) -> dict[str, dict[str, Any]]:
    """Group Drive API comments by sheet folder and convert to comments.json format.

    Uses the `uid` field in the anchor to determine which sheet each comment
    belongs to (uid corresponds to the sheet's sheetId).

    Args:
        comments: List of comment dicts from Drive API v3
        file_id: The spreadsheet file ID
        sheet_id_to_folder: Mapping from numeric sheet ID to folder name

    Returns:
        Dict mapping sheet_folder -> comments.json content dict.
        Only includes sheets that have at least one non-deleted comment.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}

    for comment in comments:
        if comment.get("deleted", False):
            continue

        anchor_str = comment.get("anchor", "")
        uid = parse_anchor_sheet_uid(anchor_str)

        if uid is None:
            continue

        sheet_folder = sheet_id_to_folder.get(uid)
        if sheet_folder is None:
            continue

        if sheet_folder not in grouped:
            grouped[sheet_folder] = []

        # Build author string
        author = comment.get("author", {})
        author_name = author.get("displayName", "Unknown")
        author_email = author.get("emailAddress", "")
        author_str = (
            f"{author_name} <{author_email}>" if author_email else author_name
        )

        # Extract quoted content (the cell value that was selected)
        quoted = comment.get("quotedFileContent", {})
        quoted_content = quoted.get("value", "")

        comment_dict: dict[str, Any] = {
            "id": comment["id"],
            "author": author_str,
            "time": comment.get("createdTime", ""),
            "resolved": comment.get("resolved", False),
            "content": comment.get("content", ""),
        }
        if quoted_content:
            comment_dict["quotedContent"] = quoted_content

        # Add non-deleted replies
        replies = comment.get("replies", [])
        non_deleted = [r for r in replies if not r.get("deleted", False)]
        if non_deleted:
            comment_dict["replies"] = []
            for reply in non_deleted:
                reply_author = reply.get("author", {})
                reply_name = reply_author.get("displayName", "Unknown")
                reply_email = reply_author.get("emailAddress", "")
                reply_author_str = (
                    f"{reply_name} <{reply_email}>" if reply_email else reply_name
                )
                reply_dict: dict[str, Any] = {
                    "id": reply["id"],
                    "author": reply_author_str,
                    "time": reply.get("createdTime", ""),
                    "content": reply.get("content", ""),
                }
                comment_dict["replies"].append(reply_dict)

        grouped[sheet_folder].append(comment_dict)

    result: dict[str, dict[str, Any]] = {}
    for sheet_folder, sheet_comments in grouped.items():
        result[sheet_folder] = {
            "fileId": file_id,
            "comments": sheet_comments,
        }

    return result


def parse_comments_json(json_str: str) -> tuple[str, list[dict[str, Any]]]:
    """Parse comments.json content into structured data.

    Args:
        json_str: The comments.json content

    Returns:
        Tuple of (file_id, list of comment dicts)
    """
    data = json.loads(json_str)
    file_id: str = data.get("fileId", "")
    comments: list[dict[str, Any]] = data.get("comments", [])
    return file_id, comments


def diff_comments(
    pristine_json: str | None,
    current_json: str,
) -> CommentOperations:
    """Compare pristine and current comments.json to extract operations.

    Detects:
    - New replies (reply without id) → NewReply
    - Newly resolved comments → ResolveComment

    Note: Creating new top-level comments is not supported because the
    Drive API anchor format for Google Sheets is opaque and cannot be
    constructed from A1 notation.

    Args:
        pristine_json: Pristine comments.json content (None if no comments existed)
        current_json: Current comments.json content

    Returns:
        CommentOperations with detected changes
    """
    ops = CommentOperations()

    _, current_comments = parse_comments_json(current_json)

    # Parse pristine state
    pristine_comment_ids: set[str] = set()
    pristine_resolved: set[str] = set()

    if pristine_json:
        _, pristine_comments = parse_comments_json(pristine_json)
        for pc in pristine_comments:
            cid = pc.get("id", "")
            if cid:
                pristine_comment_ids.add(cid)
                if pc.get("resolved", False):
                    pristine_resolved.add(cid)

    for comment in current_comments:
        comment_id = comment.get("id")

        if not comment_id or comment_id not in pristine_comment_ids:
            # New top-level comment — not supported, skip silently
            # (anchor format is opaque, cannot create via API)
            continue

        # Existing comment — check for resolve
        if (
            comment.get("resolved", False)
            and comment_id not in pristine_resolved
        ):
            ops.resolves.append(ResolveComment(comment_id=comment_id))

        # Check for new replies (reply without id = agent-added)
        for reply in comment.get("replies", []):
            if not reply.get("id"):
                reply_content = reply.get("content", "")
                if reply_content:
                    ops.new_replies.append(
                        NewReply(comment_id=comment_id, content=reply_content)
                    )

    return ops
