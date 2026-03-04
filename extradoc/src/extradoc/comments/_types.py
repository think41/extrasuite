"""Typed dataclasses for comments.

Reply, Comment, FileComments, DocumentWithComments, and operation types
for the comment diff/push workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from extradoc.api_types._generated import Document


@dataclass
class Reply:
    """A reply on a comment."""

    id: str
    author: str
    created_time: str
    content: str
    action: str | None = None  # "resolve", "reopen" — read-only on pull
    deleted: bool = False


@dataclass
class Comment:
    """A comment on a document."""

    id: str
    author: str
    created_time: str
    content: str
    anchor: str  # raw Drive API anchor string — always preserved verbatim
    resolved: bool
    deleted: bool
    replies: list[Reply] = field(default_factory=list)


@dataclass
class FileComments:
    """All comments on a file."""

    file_id: str
    comments: list[Comment] = field(default_factory=list)

    @property
    def active_comments(self) -> list[Comment]:
        """Return non-deleted comments."""
        return [c for c in self.comments if not c.deleted]


@dataclass
class DocumentWithComments:
    """Aggregate unit of a document and its comments."""

    document: Document
    comments: FileComments


# ---------------------------------------------------------------------------
# Operation types for comment diff
# ---------------------------------------------------------------------------


@dataclass
class NewReply:
    """A new reply to add to an existing comment."""

    comment_id: str
    content: str


@dataclass
class Resolve:
    """A comment to resolve."""

    comment_id: str


@dataclass
class EditComment:
    """Edit the content of an existing comment."""

    comment_id: str
    content: str


@dataclass
class EditReply:
    """Edit the content of an existing reply."""

    comment_id: str
    reply_id: str
    content: str


@dataclass
class DeleteComment:
    """Delete a comment."""

    comment_id: str


@dataclass
class CommentOperations:
    """Operations extracted from diff between base and desired FileComments."""

    new_replies: list[NewReply] = field(default_factory=list)
    resolves: list[Resolve] = field(default_factory=list)
    edits: list[EditComment] = field(default_factory=list)
    reply_edits: list[EditReply] = field(default_factory=list)
    deletes: list[DeleteComment] = field(default_factory=list)

    @property
    def has_operations(self) -> bool:
        return bool(
            self.new_replies
            or self.resolves
            or self.edits
            or self.reply_edits
            or self.deletes
        )
