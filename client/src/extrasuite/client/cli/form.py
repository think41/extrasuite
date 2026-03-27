"""Form CLI commands: pull, diff, push, create."""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
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
    output_dir_arg = args.output_dir
    reason = _get_reason(args, default="Pulling Google Form")
    cred = _get_credential(
        args,
        command={"type": "form.pull", "file_url": args.url, "file_name": ""},
        reason=reason,
    )

    tmp_parent = None
    if output_dir_arg:
        tmp_parent = Path(tempfile.mkdtemp())
        dest_dir = Path(output_dir_arg)
    else:
        dest_dir = Path() / form_id

    async def _run() -> None:
        transport = GoogleFormsTransport(cred.token)
        client = FormsClient(transport)
        pull_parent = tmp_parent if tmp_parent else Path()
        try:
            await client.pull(
                form_id,
                pull_parent,
                include_responses=args.responses,
                max_responses=args.max_responses,
                save_raw=not args.no_raw,
            )
            if tmp_parent is not None:
                dest_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(tmp_parent / form_id), str(dest_dir))
        finally:
            await transport.close()

    try:
        asyncio.run(_run())
    finally:
        if tmp_parent is not None:
            shutil.rmtree(tmp_parent, ignore_errors=True)

    print(f"Pulled to {dest_dir}/")


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

    reason = _get_reason(args, default="Pushing changes to Google Form")
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
    """Create a new Google Form and pull it locally."""
    from extraform import FormsClient, GoogleFormsTransport

    file_id, url = _cmd_create("form", args)

    output_dir_arg = getattr(args, "output_dir", None)
    tmp_parent = None
    if output_dir_arg:
        tmp_parent = Path(tempfile.mkdtemp())
        dest_dir = Path(output_dir_arg)
    else:
        dest_dir = Path() / file_id

    reason = _get_reason(args, default="Pulling newly created Google Form")
    cred = _get_credential(
        args,
        command={"type": "form.pull", "file_url": url, "file_name": args.title},
        reason=reason,
    )

    async def _run() -> None:
        transport = GoogleFormsTransport(cred.token)
        client = FormsClient(transport)
        pull_parent = tmp_parent if tmp_parent else Path()
        try:
            await client.pull(file_id, pull_parent, save_raw=True)
            if tmp_parent is not None:
                dest_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(tmp_parent / file_id), str(dest_dir))
        finally:
            await transport.close()

    try:
        asyncio.run(_run())
    finally:
        if tmp_parent is not None:
            shutil.rmtree(tmp_parent, ignore_errors=True)

    print(f"Pulled to {dest_dir}/")


def cmd_form_share(args: Any) -> None:
    """Share a Google Form with trusted contacts."""
    _cmd_share("form", args)
