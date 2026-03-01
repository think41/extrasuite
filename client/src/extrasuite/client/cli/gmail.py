"""Gmail CLI commands: compose, edit-draft, reply, list, read."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from extrasuite.client.cli._common import (
    _get_credential,
    _get_reason,
    _trusted_contacts_setup,
)
from extrasuite.client.settings import _SETTINGS_PATH


def _parse_email_file_args(
    file_path: Path,
    cli_attachments: list[str] | None = None,
) -> tuple[list[str], str, str, list[str] | None, list[str] | None, list[Path] | None]:
    """Read and parse an email markdown file.

    Returns (to, subject, body, cc, bcc, attachments).
    """
    from extrasuite.client.google_api import parse_email_file

    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    content = file_path.read_text()
    metadata, body = parse_email_file(content)

    if "to" not in metadata:
        print("Error: 'to' field is required in front matter.", file=sys.stderr)
        sys.exit(1)
    if "subject" not in metadata:
        print("Error: 'subject' field is required in front matter.", file=sys.stderr)
        sys.exit(1)

    to = [addr.strip() for addr in metadata["to"].split(",")]
    subject = metadata["subject"]
    cc = (
        [addr.strip() for addr in metadata["cc"].split(",")]
        if metadata.get("cc")
        else None
    )
    bcc = (
        [addr.strip() for addr in metadata["bcc"].split(",")]
        if metadata.get("bcc")
        else None
    )

    attachments: list[Path] | None = None
    if cli_attachments:
        attachments = []
        for a in cli_attachments:
            p = Path(a)
            if not p.exists():
                print(f"Error: Attachment not found: {p}", file=sys.stderr)
                sys.exit(1)
            attachments.append(p)

    return to, subject, body, cc, bcc, attachments


def cmd_gmail_compose(args: Any) -> None:
    """Save an email draft from a markdown file with front matter."""
    from extrasuite.client.google_api import create_gmail_draft

    attach = getattr(args, "attach", None)
    to, subject, body, cc, bcc, attachments = _parse_email_file_args(
        Path(args.file), cli_attachments=attach
    )

    reason = _get_reason(args, default="Save email draft")
    cred = _get_credential(
        args,
        command={
            "type": "gmail.compose",
            "subject": subject,
            "recipients": to,
            "cc": cc or [],
        },
        reason=reason,
    )

    result = create_gmail_draft(
        cred.token,
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
        attachments=attachments,
    )
    draft_id = result.get("id", "")
    print(f"Draft saved (id: {draft_id})")


def cmd_gmail_edit_draft(args: Any) -> None:
    """Update an existing Gmail draft from a markdown file with front matter."""
    from extrasuite.client.google_api import update_gmail_draft

    attach = getattr(args, "attach", None)
    to, subject, body, cc, bcc, attachments = _parse_email_file_args(
        Path(args.file), cli_attachments=attach
    )

    reason = _get_reason(args, default="Edit email draft")
    cred = _get_credential(
        args,
        command={
            "type": "gmail.edit_draft",
            "draft_id": args.draft_id,
            "subject": subject,
            "recipients": to,
            "cc": cc or [],
        },
        reason=reason,
    )

    update_gmail_draft(
        cred.token,
        draft_id=args.draft_id,
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
        attachments=attachments,
    )
    print(f"Draft updated (id: {args.draft_id})")


def cmd_gmail_reply(args: Any) -> None:
    """Create a reply draft threaded into an existing conversation."""
    from extrasuite.client.google_api import (
        create_gmail_reply_draft,
        fetch_thread_reply_context,
        parse_email_file,
    )

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    metadata, body = parse_email_file(file_path.read_text())

    attachments: list[Path] | None = None
    cli_attachments = getattr(args, "attach", None)
    if cli_attachments:
        attachments = []
        for a in cli_attachments:
            p = Path(a)
            if not p.exists():
                print(f"Error: Attachment not found: {p}", file=sys.stderr)
                sys.exit(1)
            attachments.append(p)

    # gmail.reply maps to [gmail.readonly + gmail.compose] on the server —
    # a single request returns a token valid for both scopes.
    reason = _get_reason(args, default="Save reply draft")
    cred = _get_credential(
        args,
        command={
            "type": "gmail.reply",
            "thread_id": args.thread_id,
            "thread_subject": "",
            "recipients": [
                addr.strip()
                for addr in metadata.get("to", "").split(",")
                if addr.strip()
            ],
            "cc": [
                addr.strip()
                for addr in metadata.get("cc", "").split(",")
                if addr.strip()
            ],
        },
        reason=reason,
    )

    ctx = fetch_thread_reply_context(cred.token, args.thread_id)

    if "to" in metadata:
        to = [addr.strip() for addr in metadata["to"].split(",") if addr.strip()]
    else:
        to = [addr.strip() for addr in ctx["from_"].split(",") if addr.strip()]

    cc: list[str] | None
    if "cc" in metadata:
        cc = [addr.strip() for addr in metadata["cc"].split(",") if addr.strip()]
    elif ctx["to"] or ctx["cc"]:
        orig_addrs = []
        for f in [ctx["to"], ctx["cc"]]:
            if f:
                orig_addrs.extend(addr.strip() for addr in f.split(",") if addr.strip())
        cc = orig_addrs if orig_addrs else None
    else:
        cc = None

    result = create_gmail_reply_draft(
        cred.token,
        reply_context=ctx,
        to=to,
        body=body,
        cc=cc,
        attachments=attachments,
    )
    draft_id = result.get("id", "")
    print(f"Reply draft saved (id: {draft_id})")
    print(f"  Thread:  {ctx['thread_id']}")
    print(f"  To:      {', '.join(to)}")
    if cc:
        print(f"  Cc:      {', '.join(cc)}")
    print(f"  Subject: {ctx['subject']}")


def cmd_gmail_list(args: Any) -> None:
    """List Gmail threads (one row per conversation)."""
    import json as _json

    from extrasuite.client.gmail_reader import (
        _NO_TRUSTED_CONTACTS_NOTICE,
        format_thread_list,
        list_threads,
    )

    query = getattr(args, "query", "") or ""
    reason = _get_reason(args, default="List Gmail threads")
    cred = _get_credential(
        args,
        command={
            "type": "gmail.list",
            "query": query,
            "max_results": getattr(args, "max", 0),
        },
        reason=reason,
    )

    trusted = _trusted_contacts_setup(cred.token)
    settings_exists = _SETTINGS_PATH.exists()

    summaries, next_page_token = list_threads(
        cred.token,
        query=query,
        max_results=getattr(args, "max", 20),
        page_token=getattr(args, "page", "") or "",
        whitelist=trusted,
        trusted_only=not getattr(args, "all", False),
    )

    if getattr(args, "json", False):
        output = {
            "threads": [
                {
                    "thread_id": s.thread_id,
                    "date": s.date,
                    "from": s.from_,
                    "subject": s.subject,
                    "message_count": s.message_count,
                    "labels": s.labels,
                    "trusted": s.trusted,
                    "latest_message_id": s.latest_message_id,
                }
                for s in summaries
            ],
            "next_page_token": next_page_token,
        }
        print(_json.dumps(output, indent=2))
        if not settings_exists:
            print(_NO_TRUSTED_CONTACTS_NOTICE, file=sys.stderr)
    else:
        print(format_thread_list(summaries, next_page_token, settings_exists))


def cmd_gmail_read(args: Any) -> None:
    """Read a full Gmail thread (all messages in order)."""
    import json as _json
    from typing import Any as _Any

    from extrasuite.client.gmail_reader import (
        format_thread_detail,
        get_thread,
    )

    reason = _get_reason(args, default="Read Gmail thread")
    cred = _get_credential(
        args,
        command={"type": "gmail.read", "thread_id": args.thread_id},
        reason=reason,
    )

    trusted = _trusted_contacts_setup(cred.token)
    detail = get_thread(cred.token, args.thread_id, whitelist=trusted)

    if getattr(args, "json", False):
        output: dict[str, _Any] = {
            "thread_id": detail.thread_id,
            "subject": detail.subject,
            "messages": [
                {
                    "message_id": m.message_id,
                    "date": m.date,
                    "from": m.from_,
                    "to": m.to,
                    "cc": m.cc,
                    "subject": m.subject,
                    "labels": m.labels,
                    "trusted": m.trusted,
                    "body": m.body,
                    "attachments": m.attachments,
                }
                for m in detail.messages
            ],
        }
        print(_json.dumps(output, indent=2))
    else:
        print(format_thread_detail(detail))
