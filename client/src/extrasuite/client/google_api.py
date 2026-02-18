"""Google API helpers for direct API calls.

Provides simple wrappers for Google APIs that don't have dedicated
extra* packages: file creation, Drive sharing, Gmail drafts, and Calendar.
"""

from __future__ import annotations

import base64
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import Any

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


def create_gmail_draft(
    token: str,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> dict[str, Any]:
    """Create a Gmail draft from the given fields."""
    msg = MIMEText(body)
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

    return _api_request(
        "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
        token,
        method="POST",
        body={"message": {"raw": raw}},
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
    """Format calendar events as a markdown list grouped by date."""
    if not events:
        return "No events found."

    lines: list[str] = []
    current_date = ""

    for event in events:
        start = event.get("start", {})
        end = event.get("end", {})
        summary = event.get("summary", "(No title)")

        if "date" in start:
            # All-day event
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

        lines.append(f"- **{time_str}** {summary}")

        location = event.get("location")
        if location:
            lines.append(f"  Location: {location}")

        description = event.get("description")
        if description:
            desc = description.replace("\n", " ").strip()
            if len(desc) > 200:
                desc = desc[:200] + "..."
            lines.append(f"  {desc}")

    return "\n".join(lines).strip()
