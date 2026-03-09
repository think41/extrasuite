"""Form CLI commands: pull, diff, push, create."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from extrasuite.client.cli._common import (
    _cmd_create,
    _cmd_share,
    _get_credential,
    _get_reason,
    _parse_form_id,
)


def cmd_form_pull(args: Any) -> None:
    """Pull a Google Form."""
    from extraform import FormsClient, GoogleFormsTransport

    form_id = _parse_form_id(args.url)
    output_dir = Path(args.output_dir) if args.output_dir else Path()
    reason = _get_reason(args)
    cred = _get_credential(
        args,
        command={"type": "form.pull", "file_url": args.url, "file_name": ""},
        reason=reason,
    )

    async def _run() -> None:
        transport = GoogleFormsTransport(cred.token)
        client = FormsClient(transport)
        try:
            await client.pull(
                form_id,
                output_dir,
                include_responses=args.responses,
                max_responses=args.max_responses,
                save_raw=not args.no_raw,
            )
            print(f"Pulled form to {output_dir / form_id}/")
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_form_diff(args: Any) -> None:
    """Preview changes to a Google Form."""
    from extraform import FormsClient

    client = FormsClient.__new__(FormsClient)
    _diff_result, requests = client.diff(Path(args.folder))
    if not requests:
        print("No changes detected.")
    else:
        print(json.dumps(requests, indent=2))


def cmd_form_push(args: Any) -> None:
    """Push changes to a Google Form."""
    from extraform import FormsClient, GoogleFormsTransport

    reason = _get_reason(args)
    cred = _get_credential(
        args,
        command={"type": "form.push", "file_url": "", "file_name": ""},
        reason=reason,
    )

    async def _run() -> None:
        transport = GoogleFormsTransport(cred.token)
        client = FormsClient(transport)
        try:
            result = await client.push(Path(args.folder), force=args.force)
            print(result.message)
            if not result.success:
                sys.exit(1)
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_form_create(args: Any) -> None:
    """Create a new Google Form."""
    _cmd_create("form", args)


def cmd_form_share(args: Any) -> None:
    """Share a Google Form with trusted contacts."""
    _cmd_share("form", args)
