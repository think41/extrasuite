"""Contacts CLI commands: sync, search, touch."""

from __future__ import annotations

import json
import sys
from typing import Any

from extrasuite.client.cli._common import _get_credential, _get_reason


def cmd_contacts_sync(args: Any) -> None:
    """Sync Google Contacts to local DB."""
    from extrasuite.client.contacts import sync

    reason = _get_reason(args, default="Sync Google Contacts")
    token = _get_credential(
        args,
        command={"type": "contacts.read", "query": ""},
        reason=reason,
    )
    other_token = _get_credential(
        args,
        command={"type": "contacts.other", "query": ""},
        reason=_get_reason(args, default="Sync Gmail-suggested contacts"),
    )
    people_count, other_count = sync(
        token.token, other_token=other_token.token, verbose=True
    )
    print(f"Synced {people_count} contacts and {other_count} other contacts.")


def cmd_contacts_search(args: Any) -> None:
    """Search local contacts DB."""
    from extrasuite.client.contacts import (
        _DB_PATH,
        _is_stale,
        _open_db,
        search,
    )

    queries: list[str] = args.queries
    if not queries:
        print("No search queries provided.", file=sys.stderr)
        sys.exit(1)

    # Check staleness before prompting for auth — avoids browser popup when not needed
    needs_sync = not _DB_PATH.exists()
    if not needs_sync:
        needs_sync = _is_stale(_open_db())

    token_str = None
    other_token_str = None
    if needs_sync:
        query_str = " ".join(queries)
        reason = _get_reason(args, default="Sync Google Contacts")
        cred = _get_credential(
            args,
            command={"type": "contacts.read", "query": query_str},
            reason=reason,
        )
        other_cred = _get_credential(
            args,
            command={"type": "contacts.other", "query": query_str},
            reason=_get_reason(args, default="Sync Gmail-suggested contacts"),
        )
        token_str = cred.token
        other_token_str = other_cred.token

    results = search(
        queries, token=token_str, other_token=other_token_str, auto_sync=needs_sync
    )
    print(json.dumps(results, indent=2))


def cmd_contacts_touch(args: Any) -> None:
    """Record that these email addresses were contacted."""
    from extrasuite.client.contacts import touch

    emails: list[str] = args.emails
    if not emails:
        print("No email addresses provided.", file=sys.stderr)
        sys.exit(1)

    touch(emails)
    print(f"Recorded interaction with {len(emails)} contact(s).")
