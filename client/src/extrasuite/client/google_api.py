"""Google API helpers for direct API calls.

Provides simple wrappers for Google APIs that don't have dedicated
extra* packages: file creation, Drive sharing, Gmail drafts, and Calendar.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import ssl
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import markdown as _markdown

try:
    import certifi

    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()


def _api_request(
    url: str,
    token: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Make an authenticated Google API request."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
    if body is not None:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as response:
            response_data = response.read().decode("utf-8")
            return json.loads(response_data) if response_data else {}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else str(e)
        try:
            error_json = json.loads(error_body)
            error_message = error_json.get("error", {}).get("message", error_body)
        except (json.JSONDecodeError, AttributeError):
            error_message = error_body
        raise Exception(f"Google API error ({e.code}): {error_message}") from e


# ---------------------------------------------------------------------------
# File creation
# ---------------------------------------------------------------------------


def create_file_via_drive(token: str, title: str, mime_type: str) -> dict[str, Any]:
    """Create a Google Workspace file via Drive API. Returns a File resource with 'id'."""
    return _api_request(
        "https://www.googleapis.com/drive/v3/files",
        token,
        method="POST",
        body={"name": title, "mimeType": mime_type},
    )


def create_spreadsheet(token: str, title: str) -> dict[str, Any]:
    """Create a new Google Sheet. Returns the Sheets API response."""
    return _api_request(
        "https://sheets.googleapis.com/v4/spreadsheets",
        token,
        method="POST",
        body={"properties": {"title": title}},
    )


def create_document(token: str, title: str) -> dict[str, Any]:
    """Create a new Google Doc. Returns the Docs API response."""
    return _api_request(
        "https://docs.googleapis.com/v1/documents",
        token,
        method="POST",
        body={"title": title},
    )


def create_presentation(token: str, title: str) -> dict[str, Any]:
    """Create a new Google Slides presentation. Returns the Slides API response."""
    return _api_request(
        "https://slides.googleapis.com/v1/presentations",
        token,
        method="POST",
        body={"title": title},
    )


def create_form(token: str, title: str) -> dict[str, Any]:
    """Create a new Google Form. Returns the Forms API response."""
    return _api_request(
        "https://forms.googleapis.com/v1/forms",
        token,
        method="POST",
        body={"info": {"title": title}},
    )


# ---------------------------------------------------------------------------
# Drive sharing
# ---------------------------------------------------------------------------


def share_file(
    token: str, file_id: str, email: str, role: str = "writer"
) -> dict[str, Any]:
    """Share a file with a user via Google Drive API."""
    return _api_request(
        f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions",
        token,
        method="POST",
        body={
            "type": "user",
            "role": role,
            "emailAddress": email,
        },
        params={"sendNotificationEmail": "false"},
    )


# ---------------------------------------------------------------------------
# Gmail
# ---------------------------------------------------------------------------


def parse_email_file(content: str) -> tuple[dict[str, str], str]:
    """Parse a markdown file with front matter for email composition.

    Expected format::

        ---
        subject: Email subject
        to: alice@example.com, bob@example.com
        cc: charlie@example.com
        bcc: dave@example.com
        ---

        Email body here.

    Returns:
        (metadata dict, body string)
    """
    if not content.startswith("---"):
        raise ValueError("Email file must start with '---' front matter delimiter")

    end = content.find("\n---", 3)
    if end == -1:
        raise ValueError("Missing closing '---' front matter delimiter")

    front = content[3:end].strip()
    body = content[end + 4 :].strip()

    metadata: dict[str, str] = {}
    for line in front.split("\n"):
        line = line.strip()
        if not line:
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip().lower()] = value.strip()

    return metadata, body


def markdown_to_html(text: str) -> str:
    """Convert markdown text to HTML suitable for Gmail."""
    html_body = _markdown.markdown(text, extensions=["nl2br", "tables"])
    return (
        '<div style="font-family: Arial, sans-serif; font-size: 14px;'
        ' line-height: 1.6; color: #333;">'
        f"{html_body}</div>"
    )


def _build_email_message(
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    attachments: list[Path] | None = None,
) -> MIMEMultipart:
    """Build a multipart MIME message from a markdown body with optional attachments."""
    if attachments:
        msg = MIMEMultipart("mixed")
        body_part = MIMEMultipart("alternative")
        body_part.attach(MIMEText(body, "plain"))
        body_part.attach(MIMEText(markdown_to_html(body), "html"))
        msg.attach(body_part)
        for filepath in attachments:
            mime_type, _ = mimetypes.guess_type(str(filepath))
            if mime_type is None:
                mime_type = "application/octet-stream"
            main_type, sub_type = mime_type.split("/", 1)
            part = MIMEBase(main_type, sub_type)
            part.set_payload(filepath.read_bytes())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=filepath.name)
            msg.attach(part)
    else:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(markdown_to_html(body), "html"))
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    return msg


def create_gmail_draft(
    token: str,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    attachments: list[Path] | None = None,
) -> dict[str, Any]:
    """Create a Gmail draft. Body is markdown and rendered as HTML in the draft."""
    msg = _build_email_message(to, subject, body, cc, bcc, attachments=attachments)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    return _api_request(
        "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
        token,
        method="POST",
        body={"message": {"raw": raw}},
    )


def update_gmail_draft(
    token: str,
    draft_id: str,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    attachments: list[Path] | None = None,
) -> dict[str, Any]:
    """Update an existing Gmail draft. Body is markdown and rendered as HTML."""
    msg = _build_email_message(to, subject, body, cc, bcc, attachments=attachments)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    return _api_request(
        f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{draft_id}",
        token,
        method="PUT",
        body={"message": {"raw": raw}},
    )


def fetch_thread_reply_context(token: str, thread_id: str) -> dict[str, Any]:
    """Fetch reply context from the latest message in a thread.

    Fetches the thread metadata, picks the last message, and returns the
    same dict shape as fetch_message_reply_context so the draft builder
    can use either.
    """
    url = (
        "https://gmail.googleapis.com/gmail/v1/users/me/threads/"
        + thread_id
        + "?"
        + urllib.parse.urlencode(
            [
                ("format", "metadata"),
                ("metadataHeaders", "From"),
                ("metadataHeaders", "To"),
                ("metadataHeaders", "Cc"),
                ("metadataHeaders", "Subject"),
                ("metadataHeaders", "Message-ID"),
                ("metadataHeaders", "References"),
            ]
        )
    )
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    messages = data.get("messages", [])
    if not messages:
        raise ValueError(f"Thread {thread_id} has no messages")

    latest = messages[-1]

    def _hdr(name: str) -> str:
        for h in latest.get("payload", {}).get("headers", []):
            if h.get("name", "").lower() == name.lower():
                return h.get("value", "")
        return ""

    # Subject from first message (clean thread subject)
    def _first_hdr(name: str) -> str:
        for h in messages[0].get("payload", {}).get("headers", []):
            if h.get("name", "").lower() == name.lower():
                return h.get("value", "")
        return ""

    message_id_hdr = _hdr("Message-ID")
    original_refs = _hdr("References")
    references = (
        f"{original_refs} {message_id_hdr}".strip() if original_refs else message_id_hdr
    )

    subject = _first_hdr("Subject")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    return {
        "thread_id": thread_id,
        "message_id_hdr": message_id_hdr,
        "references": references,
        "from_": _hdr("From"),
        "to": _hdr("To"),
        "cc": _hdr("Cc"),
        "subject": subject,
    }


def fetch_message_reply_context(token: str, message_id: str) -> dict[str, Any]:
    """Fetch the headers needed to construct a proper reply to a Gmail message.

    Returns a dict with:
        thread_id       - Gmail thread ID (for threadId on the draft)
        message_id_hdr  - RFC 2822 Message-ID header value (for In-Reply-To)
        references      - References header value (for chaining)
        from_           - Original sender (becomes reply To)
        to              - Original To addresses
        cc              - Original Cc addresses
        subject         - Original subject (with Re: prefix added if needed)
    """
    url = (
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/"
        + message_id
        + "?"
        + urllib.parse.urlencode(
            [
                ("format", "metadata"),
                ("metadataHeaders", "From"),
                ("metadataHeaders", "To"),
                ("metadataHeaders", "Cc"),
                ("metadataHeaders", "Subject"),
                ("metadataHeaders", "Message-ID"),
                ("metadataHeaders", "References"),
            ]
        )
    )
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    def _hdr(name: str) -> str:
        for h in data.get("payload", {}).get("headers", []):
            if h.get("name", "").lower() == name.lower():
                return h.get("value", "")
        return ""

    thread_id = data.get("threadId", "")
    message_id_hdr = _hdr("Message-ID")
    original_refs = _hdr("References")
    # Build References: append Message-ID to existing chain
    if original_refs:
        references = f"{original_refs} {message_id_hdr}".strip()
    else:
        references = message_id_hdr

    subject = _hdr("Subject")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    return {
        "thread_id": thread_id,
        "message_id_hdr": message_id_hdr,
        "references": references,
        "from_": _hdr("From"),
        "to": _hdr("To"),
        "cc": _hdr("Cc"),
        "subject": subject,
    }


def create_gmail_reply_draft(
    token: str,
    reply_context: dict[str, Any],
    to: list[str],
    body: str,
    cc: list[str] | None = None,
    attachments: list[Path] | None = None,
) -> dict[str, Any]:
    """Create a Gmail draft that is a proper reply in an existing thread.

    reply_context must come from fetch_message_reply_context().
    Sets In-Reply-To, References, and threadId so Gmail threads it correctly.
    """
    msg = _build_email_message(
        to, reply_context["subject"], body, cc, attachments=attachments
    )
    msg["In-Reply-To"] = reply_context["message_id_hdr"]
    msg["References"] = reply_context["references"]
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    return _api_request(
        "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
        token,
        method="POST",
        body={
            "message": {
                "raw": raw,
                "threadId": reply_context["thread_id"],
            }
        },
    )


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


def parse_time_value(value: str) -> tuple[datetime, datetime]:
    """Parse a relative or absolute time value into a (start, end) range.

    Supported values:
        today, tomorrow, yesterday, this-week, next-week, or YYYY-MM-DD.
    """
    now = datetime.now().astimezone()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    mapping: dict[str, tuple[datetime, datetime]] = {
        "today": (day_start, day_start + timedelta(days=1)),
        "tomorrow": (
            day_start + timedelta(days=1),
            day_start + timedelta(days=2),
        ),
        "yesterday": (day_start - timedelta(days=1), day_start),
        "this-week": (
            day_start - timedelta(days=day_start.weekday()),
            day_start - timedelta(days=day_start.weekday()) + timedelta(weeks=1),
        ),
        "next-week": (
            day_start - timedelta(days=day_start.weekday()) + timedelta(weeks=1),
            day_start - timedelta(days=day_start.weekday()) + timedelta(weeks=2),
        ),
    }

    if value in mapping:
        return mapping[value]

    # Try ISO date
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=now.tzinfo)
        dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return dt, dt + timedelta(days=1)
    except ValueError:
        valid = ", ".join([*mapping.keys(), "YYYY-MM-DD"])
        raise ValueError(f"Unknown time value: {value!r}. Use: {valid}") from None


def _format_attendees(attendees: list[dict[str, Any]]) -> str:
    """Format attendee list as a compact string."""
    parts = []
    status_labels = {
        "accepted": "✓",
        "declined": "✗",
        "tentative": "?",
        "needsAction": "-",
    }
    for a in attendees:
        email = a.get("email", "")
        status = status_labels.get(a.get("responseStatus", "needsAction"), "-")
        label = a.get("displayName", email)
        optional = " (optional)" if a.get("optional") else ""
        parts.append(f"{label} [{status}]{optional}")
    return ", ".join(parts)


def _format_conferencing(conference_data: dict[str, Any]) -> str | None:
    """Extract the video join URL from conferenceData."""
    for ep in conference_data.get("entryPoints", []):
        if ep.get("entryPointType") == "video":
            uri = ep.get("uri", "")
            if uri:
                return uri
    return None


def list_calendar_events(
    token: str,
    calendar_id: str = "primary",
    time_min: datetime | None = None,
    time_max: datetime | None = None,
) -> list[dict[str, Any]]:
    """List calendar events in the given time range."""
    params: dict[str, str] = {
        "singleEvents": "true",
        "orderBy": "startTime",
    }
    if time_min:
        params["timeMin"] = time_min.isoformat()
    if time_max:
        params["timeMax"] = time_max.isoformat()

    encoded_id = urllib.parse.quote(calendar_id, safe="")
    result = _api_request(
        f"https://www.googleapis.com/calendar/v3/calendars/{encoded_id}/events",
        token,
        params=params,
    )
    return result.get("items", [])


def format_events_markdown(events: list[dict[str, Any]]) -> str:
    """Format calendar events as a markdown list grouped by date.

    Includes event ID, attendees, and conferencing link.
    """
    if not events:
        return "No events found."

    lines: list[str] = []
    current_date = ""

    for event in events:
        start = event.get("start", {})
        end = event.get("end", {})
        summary = event.get("summary", "(No title)")
        event_id = event.get("id", "")

        if "date" in start:
            event_date = start["date"]
            time_str = "All day"
        else:
            start_dt = datetime.fromisoformat(start.get("dateTime", ""))
            end_dt = datetime.fromisoformat(end.get("dateTime", ""))
            event_date = start_dt.strftime("%Y-%m-%d")
            time_str = (
                f"{start_dt.strftime('%I:%M %p').lstrip('0')} - "
                f"{end_dt.strftime('%I:%M %p').lstrip('0')}"
            )

        if event_date != current_date:
            current_date = event_date
            if "date" in start:
                header_dt = datetime.strptime(event_date, "%Y-%m-%d")
            else:
                header_dt = start_dt  # type: ignore[possibly-undefined]
            lines.append(f"\n## {header_dt.strftime('%A, %B %d, %Y')}\n")

        lines.append(f"### {time_str}  {summary}")
        lines.append(f"Event ID: {event_id}")

        location = event.get("location")
        if location:
            lines.append(f"Location: {location}")

        conference_data = event.get("conferenceData")
        if conference_data:
            meet_url = _format_conferencing(conference_data)
            if meet_url:
                lines.append(f"Meet: {meet_url}")

        attendees = event.get("attendees", [])
        if attendees:
            lines.append(f"Attendees: {_format_attendees(attendees)}")

        description = event.get("description")
        if description:
            desc = description.replace("\n", " ").strip()
            if len(desc) > 200:
                desc = desc[:200] + "..."
            lines.append(desc)

        lines.append("")

    return "\n".join(lines).strip()


def list_calendars(token: str) -> list[dict[str, Any]]:
    """List all calendars in the user's calendar list."""
    result = _api_request(
        "https://www.googleapis.com/calendar/v3/users/me/calendarList",
        token,
        params={"maxResults": "250"},
    )
    return result.get("items", [])


def format_calendars_markdown(calendars: list[dict[str, Any]]) -> str:
    """Format calendar list as markdown."""
    if not calendars:
        return "No calendars found."

    own: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for cal in calendars:
        if cal.get("accessRole") in ("owner", "writer"):
            own.append(cal)
        else:
            other.append(cal)

    lines: list[str] = []
    if own:
        lines.append("## My Calendars\n")
        for cal in own:
            name = cal.get("summary", "(Unnamed)")
            cal_id = cal.get("id", "")
            lines.append(f"- **{name}**  ID: `{cal_id}`")
        lines.append("")

    if other:
        lines.append("## Other Calendars\n")
        for cal in other:
            name = cal.get("summary", "(Unnamed)")
            cal_id = cal.get("id", "")
            lines.append(f"- **{name}**  ID: `{cal_id}`")

    return "\n".join(lines).strip()


def search_calendar_events(
    token: str,
    query: str | None = None,
    attendee: str | None = None,
    calendar_id: str = "primary",
    time_min: datetime | None = None,
    time_max: datetime | None = None,
) -> list[dict[str, Any]]:
    """Search calendar events by query text or attendee email."""
    params: dict[str, str] = {
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "100",
    }
    if query:
        params["q"] = query
    if time_min:
        params["timeMin"] = time_min.isoformat()
    if time_max:
        params["timeMax"] = time_max.isoformat()

    encoded_id = urllib.parse.quote(calendar_id, safe="")
    result = _api_request(
        f"https://www.googleapis.com/calendar/v3/calendars/{encoded_id}/events",
        token,
        params=params,
    )
    events = result.get("items", [])

    # The Calendar API doesn't support attendee filtering natively; filter client-side.
    if attendee:
        attendee_lower = attendee.lower()
        events = [
            e
            for e in events
            if any(
                a.get("email", "").lower() == attendee_lower
                for a in e.get("attendees", [])
            )
        ]

    return events


def get_freebusy(
    token: str,
    attendees: list[str],
    time_min: datetime,
    time_max: datetime,
) -> dict[str, Any]:
    """Query the freebusy API for a list of attendees."""
    body: dict[str, Any] = {
        "timeMin": time_min.isoformat(),
        "timeMax": time_max.isoformat(),
        "items": [{"id": email} for email in attendees],
    }
    return _api_request(
        "https://www.googleapis.com/calendar/v3/freeBusy",
        token,
        method="POST",
        body=body,
    )


def _compute_free_slots(
    busy_blocks: list[tuple[datetime, datetime]],
    day_start: datetime,
    day_end: datetime,
    work_start_hour: int = 9,
    work_end_hour: int = 18,
) -> list[tuple[datetime, datetime]]:
    """Compute free slots within working hours given a list of busy blocks."""
    work_start = day_start.replace(
        hour=work_start_hour, minute=0, second=0, microsecond=0
    )
    work_end = day_start.replace(hour=work_end_hour, minute=0, second=0, microsecond=0)

    # Clamp to the requested range
    window_start = max(work_start, day_start)
    window_end = min(work_end, day_end)
    if window_start >= window_end:
        return []

    # Sort and merge busy blocks that overlap the window
    relevant = sorted(
        [
            (max(s, window_start), min(e, window_end))
            for s, e in busy_blocks
            if s < window_end and e > window_start
        ]
    )

    free: list[tuple[datetime, datetime]] = []
    cursor = window_start
    for busy_s, busy_e in relevant:
        if cursor < busy_s:
            free.append((cursor, busy_s))
        cursor = max(cursor, busy_e)
    if cursor < window_end:
        free.append((cursor, window_end))

    # Drop slots shorter than 15 minutes
    return [(s, e) for s, e in free if (e - s).total_seconds() >= 900]


def format_freebusy_markdown(
    freebusy_result: dict[str, Any],
    attendees: list[str],
    time_min: datetime,
    time_max: datetime,
) -> str:
    """Format freebusy results as markdown with per-person and common free slots."""
    calendars = freebusy_result.get("calendars", {})
    lines: list[str] = []

    # Header
    range_str = f"{time_min.strftime('%a %b %d')} - {(time_max - timedelta(seconds=1)).strftime('%a %b %d, %Y')}"
    lines.append(f"## Free/Busy: {range_str}\n")

    # Per-person busy times
    per_person_busy: dict[str, list[tuple[datetime, datetime]]] = {}
    for email in attendees:
        cal_data = calendars.get(email, {})
        errors = cal_data.get("errors", [])
        busy_raw = cal_data.get("busy", [])

        lines.append(f"### {email}")
        if errors:
            lines.append(
                f"_(Could not retrieve: {errors[0].get('reason', 'unknown')})_"
            )
            lines.append("")
            continue

        busy_blocks: list[tuple[datetime, datetime]] = [
            (
                datetime.fromisoformat(b["start"]).astimezone(),
                datetime.fromisoformat(b["end"]).astimezone(),
            )
            for b in busy_raw
        ]
        per_person_busy[email] = busy_blocks

        if not busy_blocks:
            lines.append("Free all day (within working hours 9 AM - 6 PM)")
        else:
            busy_strs = [
                f"{s.strftime('%a %-I:%M %p')} - {e.strftime('%-I:%M %p')}"
                for s, e in busy_blocks
            ]
            lines.append(f"Busy: {', '.join(busy_strs)}")
        lines.append("")

    # Common free slots across all attendees with valid data
    if per_person_busy:
        lines.append("## Common Free Slots (9 AM - 6 PM, working days)\n")

        # Walk day by day
        current = time_min.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end_bound = time_max.replace(hour=0, minute=0, second=0, microsecond=0)
        found_any = False

        while current < day_end_bound:
            # Skip weekends
            if current.weekday() < 5:
                next_day = current + timedelta(days=1)
                # Compute free slots for each person on this day
                all_free = None
                for _email, busy in per_person_busy.items():
                    person_free = _compute_free_slots(busy, current, next_day)
                    if all_free is None:
                        all_free = person_free
                    else:
                        # Intersect with existing free slots
                        intersected: list[tuple[datetime, datetime]] = []
                        for fs, fe in all_free:
                            for ps, pe in person_free:
                                s = max(fs, ps)
                                e = min(fe, pe)
                                if e - s >= timedelta(minutes=15):
                                    intersected.append((s, e))
                        all_free = intersected

                if all_free:
                    found_any = True
                    date_label = current.strftime("%A, %B %d")
                    slot_strs = [
                        f"{s.strftime('%-I:%M %p')} - {e.strftime('%-I:%M %p')}"
                        for s, e in all_free
                    ]
                    lines.append(f"- **{date_label}**: {', '.join(slot_strs)}")

            current += timedelta(days=1)

        if not found_any:
            lines.append("No common free slots found in the requested range.")

    return "\n".join(lines).strip()


def create_calendar_event(
    token: str,
    event_json: dict[str, Any],
    calendar_id: str = "primary",
    send_notifications: bool = True,
) -> dict[str, Any]:
    """Create a calendar event. Returns the created event resource."""
    body = _build_event_body(event_json)

    params: dict[str, str] = {
        "sendUpdates": "all" if send_notifications else "none",
    }
    add_meet = event_json.get("add_meet", False)
    if add_meet:
        params["conferenceDataVersion"] = "1"
        body["conferenceData"] = {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }

    encoded_id = urllib.parse.quote(calendar_id, safe="")
    return _api_request(
        f"https://www.googleapis.com/calendar/v3/calendars/{encoded_id}/events",
        token,
        method="POST",
        body=body,
        params=params,
    )


def _build_event_body(event_json: dict[str, Any]) -> dict[str, Any]:
    """Build a Google Calendar event body from the agent-facing JSON schema."""
    tz = event_json.get("timezone")
    all_day = event_json.get("all_day", False)

    def _make_time(value: str) -> dict[str, str]:
        if all_day:
            # Use date-only format
            dt = datetime.fromisoformat(value)
            return {"date": dt.strftime("%Y-%m-%d")}
        result: dict[str, str] = {"dateTime": value}
        if tz:
            result["timeZone"] = tz
        return result

    body: dict[str, Any] = {
        "summary": event_json["summary"],
        "start": _make_time(event_json["start"]),
        "end": _make_time(event_json["end"]),
    }

    if "description" in event_json:
        body["description"] = event_json["description"]
    if "location" in event_json:
        body["location"] = event_json["location"]
    if "status" in event_json:
        body["status"] = event_json["status"]
    if "recurrence" in event_json:
        recurrence = event_json["recurrence"]
        body["recurrence"] = [recurrence] if isinstance(recurrence, str) else recurrence

    raw_attendees = event_json.get("attendees", [])
    if raw_attendees:
        attendee_list = []
        for a in raw_attendees:
            if isinstance(a, str):
                attendee_list.append({"email": a})
            else:
                entry: dict[str, Any] = {"email": a["email"]}
                if a.get("optional"):
                    entry["optional"] = True
                attendee_list.append(entry)
        body["attendees"] = attendee_list

    return body


def format_created_event_markdown(event: dict[str, Any]) -> str:
    """Format a newly created event as a confirmation message."""
    lines: list[str] = []
    summary = event.get("summary", "(No title)")
    event_id = event.get("id", "")
    lines.append(f"Event created: **{summary}**")
    lines.append(f"Event ID: {event_id}")

    start = event.get("start", {})
    end = event.get("end", {})
    if "dateTime" in start:
        start_dt = datetime.fromisoformat(start["dateTime"])
        end_dt = datetime.fromisoformat(end["dateTime"])
        lines.append(
            f"Date: {start_dt.strftime('%A, %B %d, %Y, %-I:%M %p')} - {end_dt.strftime('%-I:%M %p %Z')}"
        )
    elif "date" in start:
        lines.append(f"Date: {start['date']} (all day)")

    recurrence = event.get("recurrence", [])
    if recurrence:
        lines.append(f"Recurrence: {recurrence[0]}")

    conference_data = event.get("conferenceData")
    if conference_data:
        meet_url = _format_conferencing(conference_data)
        if meet_url:
            lines.append(f"Meet: {meet_url}")

    attendees = event.get("attendees", [])
    if attendees:
        sent = len([a for a in attendees if not a.get("self")])
        lines.append(f"Attendees: {_format_attendees(attendees)}")
        if sent:
            lines.append(f"Invites sent to {sent} attendee(s).")

    return "\n".join(lines)


def update_calendar_event(
    token: str,
    event_id: str,
    patch_json: dict[str, Any],
    calendar_id: str = "primary",
    send_notifications: bool = True,
) -> dict[str, Any]:
    """Patch an existing calendar event. Only fields present in patch_json are changed."""
    encoded_id = urllib.parse.quote(calendar_id, safe="")
    encoded_event = urllib.parse.quote(event_id, safe="")
    base_url = f"https://www.googleapis.com/calendar/v3/calendars/{encoded_id}/events/{encoded_event}"

    body: dict[str, Any] = {}
    tz = patch_json.get("timezone")
    all_day = patch_json.get("all_day", False)

    def _make_time(value: str) -> dict[str, str]:
        if all_day:
            dt = datetime.fromisoformat(value)
            return {"date": dt.strftime("%Y-%m-%d")}
        result: dict[str, str] = {"dateTime": value}
        if tz:
            result["timeZone"] = tz
        return result

    for field in ("summary", "description", "location", "status"):
        if field in patch_json:
            body[field] = patch_json[field]

    if "start" in patch_json:
        body["start"] = _make_time(patch_json["start"])
    if "end" in patch_json:
        body["end"] = _make_time(patch_json["end"])
    if "recurrence" in patch_json:
        rec = patch_json["recurrence"]
        body["recurrence"] = [rec] if isinstance(rec, str) else rec

    # Attendee merging — only fetch existing event when needed
    add_emails = {
        a if isinstance(a, str) else a["email"]
        for a in patch_json.get("add_attendees", [])
    }
    remove_emails = {e.lower() for e in patch_json.get("remove_attendees", [])}

    if add_emails or remove_emails:
        existing = _api_request(base_url, token)
        current_attendees = existing.get("attendees", [])
        merged = [
            a
            for a in current_attendees
            if a.get("email", "").lower() not in remove_emails
        ]
        existing_emails = {a.get("email", "").lower() for a in merged}
        for email in add_emails:
            if email.lower() not in existing_emails:
                merged.append({"email": email})
        body["attendees"] = merged

    if patch_json.get("add_meet"):
        body["conferenceData"] = {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }

    params: dict[str, str] = {
        "sendUpdates": "all" if send_notifications else "none",
    }
    if "conferenceData" in body:
        params["conferenceDataVersion"] = "1"

    return _api_request(base_url, token, method="PATCH", body=body, params=params)


def format_updated_event_markdown(event: dict[str, Any]) -> str:
    """Format an updated event as a confirmation message."""
    lines: list[str] = []
    summary = event.get("summary", "(No title)")
    event_id = event.get("id", "")
    lines.append(f"Event updated: **{summary}**")
    lines.append(f"Event ID: {event_id}")

    start = event.get("start", {})
    end = event.get("end", {})
    if "dateTime" in start:
        start_dt = datetime.fromisoformat(start["dateTime"])
        end_dt = datetime.fromisoformat(end["dateTime"])
        lines.append(
            f"Date: {start_dt.strftime('%A, %B %d, %Y, %-I:%M %p')} - {end_dt.strftime('%-I:%M %p %Z')}"
        )
    elif "date" in start:
        lines.append(f"Date: {start['date']} (all day)")

    conference_data = event.get("conferenceData")
    if conference_data:
        meet_url = _format_conferencing(conference_data)
        if meet_url:
            lines.append(f"Meet: {meet_url}")

    attendees = event.get("attendees", [])
    if attendees:
        lines.append(f"Attendees: {_format_attendees(attendees)}")

    return "\n".join(lines)


def delete_calendar_event(
    token: str,
    event_id: str,
    calendar_id: str = "primary",
    send_notifications: bool = True,
    this_and_following: bool = False,  # noqa: ARG001
) -> None:
    """Delete (cancel) a calendar event."""
    encoded_id = urllib.parse.quote(calendar_id, safe="")
    encoded_event = urllib.parse.quote(event_id, safe="")
    url = f"https://www.googleapis.com/calendar/v3/calendars/{encoded_id}/events/{encoded_event}"

    params: dict[str, str] = {
        "sendUpdates": "all" if send_notifications else "none",
    }

    # For recurring events, delete this-and-following by fetching the instance
    # and setting the recurrence end. For simplicity, we use a direct DELETE
    # which cancels the single instance (or all if not a recurring instance).
    _api_request(url, token, method="DELETE", params=params)


def rsvp_calendar_event(
    token: str,
    event_id: str,
    response: str,
    comment: str | None = None,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """Update the authenticated user's RSVP status for an event.

    response must be one of: accepted, declined, tentative.
    """
    valid_responses = {"accepted", "declined", "tentative"}
    if response not in valid_responses:
        raise ValueError(
            f"Invalid response {response!r}. Must be one of: {', '.join(sorted(valid_responses))}"
        )

    encoded_id = urllib.parse.quote(calendar_id, safe="")
    encoded_event = urllib.parse.quote(event_id, safe="")
    base_url = f"https://www.googleapis.com/calendar/v3/calendars/{encoded_id}/events/{encoded_event}"

    # GET the event to find the self attendee entry
    event = _api_request(base_url, token)
    attendees = event.get("attendees", [])

    self_entry = next((a for a in attendees if a.get("self")), None)
    if self_entry is None:
        raise ValueError("You are not listed as an attendee for this event.")

    self_entry["responseStatus"] = response
    if comment:
        self_entry["comment"] = comment

    return _api_request(
        base_url,
        token,
        method="PATCH",
        body={"attendees": attendees},
        params={"sendUpdates": "all"},
    )
