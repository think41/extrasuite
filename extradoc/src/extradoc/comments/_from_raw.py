"""Parse Drive API v3 comment response into FileComments.

FileComments.from_raw(file_id, raw_comments) is the entry point.
"""

from __future__ import annotations

from typing import Any

from ._types import Comment, FileComments, Reply


def _parse_author(author_dict: dict[str, Any]) -> str:
    """Format author as 'Display Name <email>' or just 'Display Name'."""
    name = str(author_dict.get("displayName", "Unknown"))
    email = str(author_dict.get("emailAddress", ""))
    if email:
        return f"{name} <{email}>"
    return name


def _parse_reply(reply_dict: dict[str, Any]) -> Reply:
    """Parse a single Drive API reply dict into a Reply."""
    author = _parse_author(reply_dict.get("author", {}))
    return Reply(
        id=reply_dict.get("id", ""),
        author=author,
        created_time=reply_dict.get("createdTime", ""),
        content=reply_dict.get("content", ""),
        action=reply_dict.get("action"),
        deleted=bool(reply_dict.get("deleted", False)),
    )


def _parse_comment(comment_dict: dict[str, Any]) -> Comment:
    """Parse a single Drive API comment dict into a Comment."""
    author = _parse_author(comment_dict.get("author", {}))
    replies = [_parse_reply(r) for r in comment_dict.get("replies", [])]
    return Comment(
        id=comment_dict.get("id", ""),
        author=author,
        created_time=comment_dict.get("createdTime", ""),
        content=comment_dict.get("content", ""),
        anchor=comment_dict.get("anchor", ""),
        resolved=bool(comment_dict.get("resolved", False)),
        deleted=bool(comment_dict.get("deleted", False)),
        replies=replies,
    )


def from_raw(file_id: str, raw_comments: list[dict[str, Any]]) -> FileComments:
    """Parse Drive API v3 comment response into FileComments.

    Args:
        file_id: The document file ID
        raw_comments: List of comment dicts from Drive API v3

    Returns:
        FileComments with all comments (including deleted ones, for completeness)
    """
    comments = [_parse_comment(c) for c in raw_comments]
    return FileComments(file_id=file_id, comments=comments)
