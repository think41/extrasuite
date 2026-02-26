"""Gmail read operations with sender whitelist enforcement.

Security model: emails from senders not in the whitelist have their body
and attachment content redacted. Only metadata (from, date, subject) is
returned for non-whitelisted senders.

The whitelist is stored in ~/.config/extrasuite/gmail_whitelist.json and
is managed by humans — no CLI command can modify it.

Threading model: all public commands (list, read, reply) work with thread IDs,
mirroring how Gmail's inbox works — one conversation per row.
"""

from __future__ import annotations

import base64
import email.utils
import html
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import ssl

    import certifi

    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    import ssl

    _SSL_CONTEXT = ssl.create_default_context()

_WHITELIST_PATH = Path.home() / ".config" / "extrasuite" / "gmail_whitelist.json"

# ---------------------------------------------------------------------------
# Whitelist
# ---------------------------------------------------------------------------


@dataclass
class Whitelist:
    domains: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    # The authenticated user's own domain — always trusted, not persisted to file.
    user_domain: str = ""

    def is_trusted(self, sender_raw: str) -> bool:
        """Return True if sender_raw matches a whitelisted domain or email.

        sender_raw may be a bare address or RFC 5322 formatted
        ("Display Name <addr@domain.com>"). The authenticated user's own domain
        is always trusted regardless of the whitelist file contents.
        """
        _, addr = email.utils.parseaddr(sender_raw)
        addr = addr.lower().strip()
        if not addr:
            return False

        # Exact email match
        if addr in (e.lower() for e in self.emails):
            return True

        # Domain match (exact — not subdomain)
        if "@" in addr:
            domain = addr.split("@", 1)[1]
            all_domains = list(self.domains)
            if self.user_domain:
                all_domains.append(self.user_domain)
            if domain in (d.lower() for d in all_domains):
                return True

        return False


def load_whitelist(path: Path = _WHITELIST_PATH) -> Whitelist:
    """Load the sender whitelist from disk. Returns an empty Whitelist if missing."""
    if not path.exists():
        return Whitelist()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Whitelist(
            domains=[str(d) for d in data.get("domains", [])],
            emails=[str(e) for e in data.get("emails", [])],
        )
    except (json.JSONDecodeError, OSError):
        return Whitelist()


# ---------------------------------------------------------------------------
# Gmail API helpers
# ---------------------------------------------------------------------------


def _gmail_get(
    token: str,
    path: str,
    params: dict[str, str] | list[tuple[str, str]] | None = None,
) -> Any:
    """GET from Gmail API.

    params may be a dict (single value per key) or a list of (key, value) tuples
    to support repeated keys such as metadataHeaders.
    """
    url = f"https://gmail.googleapis.com/gmail/v1/users/me{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_user_email(token: str) -> str:
    """Return the authenticated user's email address via the Gmail profile API."""
    profile = _gmail_get(token, "/profile")
    return profile.get("emailAddress", "")


def _header(headers: list[dict[str, str]], name: str) -> str:
    """Extract a header value by name (case-insensitive)."""
    name_lower = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name_lower:
            return h.get("value", "")
    return ""


def _decode_body_part(part: dict[str, Any]) -> str:
    """Decode a single MIME body part to plain text."""
    data = part.get("body", {}).get("data", "")
    if not data:
        return ""
    try:
        decoded = base64.urlsafe_b64decode(data + "==").decode(
            "utf-8", errors="replace"
        )
    except Exception:
        return ""
    return decoded


def _strip_html(text: str) -> str:
    """Very simple HTML → plain text: strip tags and unescape entities."""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</div>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</tr>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_body(payload: dict[str, Any]) -> str:
    """Extract the best plain-text body from a Gmail payload."""
    mime_type = payload.get("mimeType", "")
    parts = payload.get("parts", [])

    if not parts:
        body_text = _decode_body_part(payload)
        if mime_type.startswith("text/html"):
            body_text = _strip_html(body_text)
        return body_text

    plain = ""
    html_body = ""
    for part in parts:
        part_mime = part.get("mimeType", "")
        if part_mime == "text/plain":
            plain = _decode_body_part(part)
        elif part_mime == "text/html" and not plain:
            html_body = _strip_html(_decode_body_part(part))
        elif part_mime.startswith("multipart/"):
            nested = _extract_body(part)
            if nested and not plain:
                plain = nested

    return plain or html_body


def _extract_attachments(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Return list of {name, mime_type, size_bytes} for attachments."""
    results: list[dict[str, str]] = []
    parts = payload.get("parts", [])
    for part in parts:
        filename = part.get("filename", "")
        if not filename:
            continue
        body = part.get("body", {})
        size = body.get("size", 0)
        results.append(
            {
                "name": filename,
                "mime_type": part.get("mimeType", "application/octet-stream"),
                "size_bytes": str(size),
            }
        )
    return results


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ThreadSummary:
    """One row in the thread list — one conversation."""

    thread_id: str
    date: str  # Date of the latest message
    from_: str  # Sender of the latest message
    subject: str  # Subject from the first message
    message_count: int
    labels: list[str]
    trusted: bool  # True if latest sender is whitelisted
    latest_message_id: str = ""


@dataclass
class MessageDetail:
    """A single message within a thread."""

    message_id: str
    thread_id: str
    date: str
    from_: str
    to: str
    cc: str
    subject: str
    labels: list[str]
    trusted: bool
    body: str | None  # None when sender not trusted
    attachments: list[dict[str, str]] | None  # None when sender not trusted


@dataclass
class ThreadDetail:
    """A full thread: ordered list of messages."""

    thread_id: str
    subject: str
    messages: list[MessageDetail]

    @property
    def latest_message(self) -> MessageDetail | None:
        return self.messages[-1] if self.messages else None


# ---------------------------------------------------------------------------
# Public API: list_threads
# ---------------------------------------------------------------------------

_METADATA_HEADERS = [
    ("format", "metadata"),
    ("metadataHeaders", "From"),
    ("metadataHeaders", "Subject"),
    ("metadataHeaders", "Date"),
]


def list_threads(
    token: str,
    query: str = "",
    max_results: int = 20,
    page_token: str = "",
    whitelist: Whitelist | None = None,
    trusted_only: bool = True,
) -> tuple[list[ThreadSummary], str]:
    """List Gmail threads matching query (one row per conversation).

    Returns (threads, next_page_token).
    When trusted_only=True (default), only threads whose latest sender is
    whitelisted are returned.
    """
    if whitelist is None:
        whitelist = load_whitelist()

    params: dict[str, str] = {"maxResults": str(min(max_results, 100))}
    if query:
        params["q"] = query
    if page_token:
        params["pageToken"] = page_token

    data = _gmail_get(token, "/threads", params)
    raw_threads = data.get("threads", [])
    next_token = data.get("nextPageToken", "")

    summaries: list[ThreadSummary] = []
    for t in raw_threads:
        thread_id = t.get("id", "")
        if not thread_id:
            continue

        thread_data = _gmail_get(token, f"/threads/{thread_id}", _METADATA_HEADERS)
        msgs = thread_data.get("messages", [])
        if not msgs:
            continue

        first_hdrs = msgs[0].get("payload", {}).get("headers", [])
        latest = msgs[-1]
        latest_hdrs = latest.get("payload", {}).get("headers", [])

        from_ = _header(latest_hdrs, "From")
        subject = _header(first_hdrs, "Subject")
        date = _header(latest_hdrs, "Date")
        labels = latest.get("labelIds", [])

        summaries.append(
            ThreadSummary(
                thread_id=thread_id,
                date=date,
                from_=from_,
                subject=subject,
                message_count=len(msgs),
                labels=labels,
                trusted=whitelist.is_trusted(from_),
                latest_message_id=latest.get("id", ""),
            )
        )

    if trusted_only:
        summaries = [s for s in summaries if s.trusted]

    return summaries, next_token


# ---------------------------------------------------------------------------
# Public API: get_thread
# ---------------------------------------------------------------------------


def get_thread(
    token: str,
    thread_id: str,
    whitelist: Whitelist | None = None,
) -> ThreadDetail:
    """Fetch a full thread with all messages in chronological order.

    Each message's body/attachments are redacted if the sender is not trusted.
    """
    if whitelist is None:
        whitelist = load_whitelist()

    data = _gmail_get(token, f"/threads/{thread_id}", {"format": "full"})
    raw_msgs = data.get("messages", [])

    messages: list[MessageDetail] = []
    subject = ""

    for i, msg in enumerate(raw_msgs):
        payload = msg.get("payload", {})
        headers = payload.get("headers", [])
        from_ = _header(headers, "From")
        trusted = whitelist.is_trusted(from_)
        msg_subject = _header(headers, "Subject")
        if i == 0:
            subject = msg_subject

        messages.append(
            MessageDetail(
                message_id=msg.get("id", ""),
                thread_id=thread_id,
                date=_header(headers, "Date"),
                from_=from_,
                to=_header(headers, "To"),
                cc=_header(headers, "Cc"),
                subject=msg_subject,
                labels=msg.get("labelIds", []),
                trusted=trusted,
                body=_extract_body(payload) if trusted else None,
                attachments=_extract_attachments(payload) if trusted else None,
            )
        )

    return ThreadDetail(thread_id=thread_id, subject=subject, messages=messages)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

_REDACTION_NOTICE = "[REDACTED]"

_NO_WHITELIST_NOTICE = (
    "\nNote: No whitelist configured — all email bodies are redacted.\n"
    f"Create {_WHITELIST_PATH} to allow reading email content.\n"
    "Example:\n"
    '  {"domains": ["yourcompany.com"], "emails": []}\n'
)


def format_thread_list(
    summaries: list[ThreadSummary],
    next_page_token: str = "",
    whitelist_exists: bool = True,
) -> str:
    """Format a list of thread summaries as a plain-text table."""
    if not summaries:
        return "No threads found."

    lines: list[str] = []

    if not whitelist_exists:
        lines.append(_NO_WHITELIST_NOTICE.strip())
        lines.append("")

    lines.append(f"{'THREAD_ID':<25} {'MSGS':>4}  {'DATE':<28} {'FROM':<32} SUBJECT")
    lines.append("-" * 120)

    for s in summaries:
        trusted_marker = "" if s.trusted else " [!]"
        from_display = s.from_[: 31 - len(trusted_marker)] + trusted_marker
        subject_display = s.subject[:55] if len(s.subject) > 55 else s.subject
        date_display = s.date[:27] if len(s.date) > 27 else s.date
        lines.append(
            f"{s.thread_id:<25} {s.message_count:>4}  {date_display:<28} {from_display:<32} {subject_display}"
        )

    if next_page_token:
        lines.append("")
        lines.append(f"More results available. Use --page {next_page_token}")

    return "\n".join(lines)


def format_thread_detail(detail: ThreadDetail) -> str:
    """Format a full thread: each message in order with a separator."""
    lines: list[str] = []
    n = len(detail.messages)

    lines.append(f"Thread: {detail.thread_id}  •  {n} message{'s' if n != 1 else ''}")
    lines.append(f"Subject: {detail.subject}")
    lines.append("=" * 70)

    for i, msg in enumerate(detail.messages, 1):
        is_latest = i == n
        latest_tag = "  [latest]" if is_latest else ""
        lines.append(f"\n[{i}/{n}] From: {msg.from_}{latest_tag}")
        lines.append(f"       Date: {msg.date}")
        if msg.to:
            lines.append(f"       To:   {msg.to}")
        if msg.cc:
            lines.append(f"       CC:   {msg.cc}")
        lines.append("-" * 70)

        if msg.trusted:
            lines.append(msg.body or "(empty body)")
            if msg.attachments:
                lines.append("")
                lines.append("Attachments:")
                for att in msg.attachments:
                    size_kb = int(att["size_bytes"]) // 1024
                    size_str = (
                        f"{size_kb} KB" if size_kb > 0 else f"{att['size_bytes']} bytes"
                    )
                    lines.append(f"  - {att['name']} ({size_str}, {att['mime_type']})")
        else:
            lines.append(_REDACTION_NOTICE)

    lines.append("")
    lines.append(f"To reply: extrasuite gmail reply {detail.thread_id} reply.md")

    return "\n".join(lines)
