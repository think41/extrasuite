"""Contacts CLI commands: sync, search, touch."""

from __future__ import annotations

import json
import sys
from typing import Any

from extrasuite.client.cli._common import _get_oauth_token


def cmd_contacts_sync(args: Any) -> None:
    """Sync Google Contacts to local DB."""
    from extrasuite.client.contacts import _CONTACTS_OTHER_SCOPE, _CONTACTS_SCOPE, sync

    token = _get_oauth_token(
        args,
        scopes=[_CONTACTS_SCOPE],
        reason="Sync Google Contacts",
    )
    other_token = _get_oauth_token(
        args,
        scopes=[_CONTACTS_OTHER_SCOPE],
        reason="Sync Gmail-suggested contacts",
    )
    people_count, other_count = sync(token, other_token=other_token, verbose=True)
    print(f"Synced {people_count} contacts and {other_count} other contacts.")


def cmd_contacts_search(args: Any) -> None:
    """Search local contacts DB."""
    from extrasuite.client.contacts import (
        _CONTACTS_OTHER_SCOPE,
        _CONTACTS_SCOPE,
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

    token = None
    other_token = None
    if needs_sync:
        token = _get_oauth_token(
            args,
            scopes=[_CONTACTS_SCOPE],
            reason="Sync Google Contacts",
        )
        other_token = _get_oauth_token(
            args,
            scopes=[_CONTACTS_OTHER_SCOPE],
            reason="Sync Gmail-suggested contacts",
        )

    results = search(
        queries, token=token, other_token=other_token, auto_sync=needs_sync
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
