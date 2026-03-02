"""Typed command models for the ExtraSuite token request protocol.

Each command class represents a single, fine-grained operation an agent can request.
The ``type`` field is the discriminator for the union; every other field carries
context that is:

- Useful for server-side risk modelling / anomaly detection
- Not sensitive content (subjects and file names are fine; email bodies are not)
- Exactly scoped to what matters for that operation — nothing more

The server resolves the command type to the required credential(s) via
``command_registry.resolve_credentials()``.

Usage::

    from extrasuite.server.commands import Command

    # FastAPI will deserialise {"type": "sheet.pull", "file_url": "..."} into
    # the correct concrete class automatically via the discriminated union.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# SA-backed commands (service account — Sheets, Docs, Slides, Forms, Drive)
# ---------------------------------------------------------------------------


class SheetPullCommand(BaseModel):
    type: Literal["sheet.pull"]
    file_url: str = Field("", description="Google Sheets URL being pulled")
    file_name: str = Field("", description="Spreadsheet title if known")


class SheetPushCommand(BaseModel):
    type: Literal["sheet.push"]
    file_url: str = Field("", description="Google Sheets URL being modified")
    file_name: str = Field("", description="Spreadsheet title if known")


class SheetBatchUpdateCommand(BaseModel):
    type: Literal["sheet.batchupdate"]
    file_url: str = Field("", description="Google Sheets URL being modified")
    file_name: str = Field("", description="Spreadsheet title if known")
    request_count: int = Field(0, description="Number of batchUpdate requests", ge=0)


class DocPullCommand(BaseModel):
    type: Literal["doc.pull"]
    file_url: str = Field("", description="Google Docs URL being pulled")
    file_name: str = Field("", description="Document title if known")


class DocPushCommand(BaseModel):
    type: Literal["doc.push"]
    file_url: str = Field("", description="Google Docs URL being modified")
    file_name: str = Field("", description="Document title if known")


class SlidePullCommand(BaseModel):
    type: Literal["slide.pull"]
    file_url: str = Field("", description="Google Slides URL being pulled")
    file_name: str = Field("", description="Presentation title if known")


class SlidePushCommand(BaseModel):
    type: Literal["slide.push"]
    file_url: str = Field("", description="Google Slides URL being modified")
    file_name: str = Field("", description="Presentation title if known")


class FormPullCommand(BaseModel):
    type: Literal["form.pull"]
    file_url: str = Field("", description="Google Forms URL being pulled")
    file_name: str = Field("", description="Form title if known")


class FormPushCommand(BaseModel):
    type: Literal["form.push"]
    file_url: str = Field("", description="Google Forms URL being modified")
    file_name: str = Field("", description="Form title if known")


class DriveLsCommand(BaseModel):
    type: Literal["drive.ls"]
    folder_url: str = Field("", description="Drive folder URL being listed")
    query: str = Field("", description="Drive query filter if any")


class DriveSearchCommand(BaseModel):
    type: Literal["drive.search"]
    query: str = Field("", description="Full-text or metadata search query")


# ---------------------------------------------------------------------------
# DWD-backed commands (domain-wide delegation — Gmail, Calendar, Contacts,
#                       Drive file management, Apps Script)
# ---------------------------------------------------------------------------


class GmailComposeCommand(BaseModel):
    type: Literal["gmail.compose"]
    subject: str = Field("", description="Email subject line")
    recipients: list[str] = Field(default_factory=list, description="To: recipient email addresses")
    cc: list[str] = Field(default_factory=list, description="Cc: recipient email addresses")


class GmailEditDraftCommand(BaseModel):
    type: Literal["gmail.edit_draft"]
    draft_id: str = Field("", description="ID of the draft being edited")
    subject: str = Field("", description="Updated email subject line")
    recipients: list[str] = Field(default_factory=list, description="Updated To: recipients")
    cc: list[str] = Field(default_factory=list, description="Updated Cc: recipients")


class GmailReplyCommand(BaseModel):
    type: Literal["gmail.reply"]
    thread_id: str = Field("", description="Thread ID being replied to")
    thread_subject: str = Field("", description="Subject of the thread being replied to")
    recipients: list[str] = Field(default_factory=list, description="To: recipients for the reply")
    cc: list[str] = Field(default_factory=list, description="Cc: recipients for the reply")


class GmailListCommand(BaseModel):
    type: Literal["gmail.list"]
    query: str = Field("", description="Gmail search query (e.g. 'from:alice@company.com')")
    max_results: int = Field(0, description="Maximum threads to list", ge=0)


class GmailReadCommand(BaseModel):
    type: Literal["gmail.read"]
    thread_id: str = Field("", description="Thread ID being read")


class CalendarViewCommand(BaseModel):
    type: Literal["calendar.view"]
    when: str = Field("", description="Time range description (e.g. 'today', 'this week')")
    calendar_id: str = Field("", description="Calendar ID if not primary")


class CalendarListCommand(BaseModel):
    type: Literal["calendar.list"]


class CalendarSearchCommand(BaseModel):
    type: Literal["calendar.search"]
    query: str = Field("", description="Text search query for events")
    attendee: str = Field("", description="Filter by attendee email")
    from_date: str = Field("", description="Search start date")
    to_date: str = Field("", description="Search end date")


class CalendarFreeBusyCommand(BaseModel):
    type: Literal["calendar.freebusy"]
    attendees: list[str] = Field(
        default_factory=list, description="Email addresses to check free/busy for"
    )
    when: str = Field("", description="Time range being checked")


class CalendarCreateCommand(BaseModel):
    type: Literal["calendar.create"]
    event_title: str = Field("", description="Title of the event being created")
    attendees: list[str] = Field(default_factory=list, description="Attendee email addresses")
    start_time: str = Field("", description="Event start time (ISO 8601)")
    end_time: str = Field("", description="Event end time (ISO 8601)")


class CalendarUpdateCommand(BaseModel):
    type: Literal["calendar.update"]
    event_id: str = Field("", description="ID of the event being updated")
    event_title: str = Field("", description="New or existing event title")
    attendees: list[str] = Field(default_factory=list, description="Updated attendee list")


class CalendarDeleteCommand(BaseModel):
    type: Literal["calendar.delete"]
    event_id: str = Field("", description="ID of the event being deleted")
    event_title: str = Field("", description="Event title for audit readability")


class CalendarRsvpCommand(BaseModel):
    type: Literal["calendar.rsvp"]
    event_id: str = Field("", description="ID of the event being RSVPed to")
    event_title: str = Field("", description="Event title for audit readability")
    response: str = Field(
        "",
        description="RSVP response: accepted, declined, or tentative",
    )


class ContactsReadCommand(BaseModel):
    type: Literal["contacts.read"]
    query: str = Field("", description="Search query if syncing due to a lookup")


class ContactsOtherCommand(BaseModel):
    type: Literal["contacts.other"]
    query: str = Field("", description="Search query if syncing due to a lookup")


class DriveFileCreateCommand(BaseModel):
    type: Literal["drive.file.create"]
    file_name: str = Field("", description="Title of the file being created")
    file_type: str = Field(
        "",
        description="File type: sheet, doc, slide, or form",
    )


class DriveFileShareCommand(BaseModel):
    type: Literal["drive.file.share"]
    file_url: str = Field("", description="Drive file URL being shared")
    file_name: str = Field("", description="File title for audit readability")
    share_with: list[str] = Field(
        default_factory=list, description="Email addresses being granted access"
    )


class ScriptPullCommand(BaseModel):
    type: Literal["script.pull"]
    file_url: str = Field("", description="Apps Script project URL being pulled")
    file_name: str = Field("", description="Project title if known")


class ScriptPushCommand(BaseModel):
    type: Literal["script.push"]
    file_url: str = Field("", description="Apps Script project URL being modified")
    file_name: str = Field("", description="Project title if known")


class ScriptCreateCommand(BaseModel):
    type: Literal["script.create"]
    title: str = Field("", description="Title for the new Apps Script project")
    bind_to: str = Field("", description="Drive file URL the script is bound to")


# ---------------------------------------------------------------------------
# Discriminated union — the type used by TokenRequest
# ---------------------------------------------------------------------------

Command = Annotated[
    SheetPullCommand
    | SheetPushCommand
    | SheetBatchUpdateCommand
    | DocPullCommand
    | DocPushCommand
    | SlidePullCommand
    | SlidePushCommand
    | FormPullCommand
    | FormPushCommand
    | DriveLsCommand
    | DriveSearchCommand
    | GmailComposeCommand
    | GmailEditDraftCommand
    | GmailReplyCommand
    | GmailListCommand
    | GmailReadCommand
    | CalendarViewCommand
    | CalendarListCommand
    | CalendarSearchCommand
    | CalendarFreeBusyCommand
    | CalendarCreateCommand
    | CalendarUpdateCommand
    | CalendarDeleteCommand
    | CalendarRsvpCommand
    | ContactsReadCommand
    | ContactsOtherCommand
    | DriveFileCreateCommand
    | DriveFileShareCommand
    | ScriptPullCommand
    | ScriptPushCommand
    | ScriptCreateCommand,
    Field(discriminator="type"),
]
