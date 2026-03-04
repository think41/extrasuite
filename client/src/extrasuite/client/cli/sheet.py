"""Sheet CLI commands: pull, diff, push, create, batchUpdate."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from extrasuite.client.cli._common import (
    _cmd_create,
    _cmd_share,
    _get_credential,
    _get_reason,
    _parse_spreadsheet_id,
)


def cmd_sheet_pull(args: Any) -> None:
    """Pull a Google Sheet."""
    import asyncio

    from extrasheet import GoogleSheetsTransport, SheetsClient

    spreadsheet_id = _parse_spreadsheet_id(args.url)
    output_dir = Path(args.output_dir) if args.output_dir else Path()
    reason = _get_reason(args, default="Pulling Google Sheet")
    cred = _get_credential(
        args,
        command={"type": "sheet.pull", "file_url": args.url, "file_name": ""},
        reason=reason,
    )
    max_rows = 0 if args.no_limit else args.max_rows

    async def _run() -> None:
        transport = GoogleSheetsTransport(cred.token)
        client = SheetsClient(transport)
        try:
            files = await client.pull(
                spreadsheet_id,
                output_dir,
                max_rows=max_rows,
                save_raw=not args.no_raw,
            )
            sheet_count = sum(1 for f in files if f.name == "data.tsv")
            print(
                f"Pulled {sheet_count} sheet{'s' if sheet_count != 1 else ''} to {output_dir / spreadsheet_id}/"
            )
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_sheet_diff(args: Any) -> None:
    """Preview changes to a Google Sheet."""
    from extrasheet import SheetsClient

    client = SheetsClient.__new__(SheetsClient)
    _diff_result, requests, validation, per_sheet_comment_ops = client.diff(args.folder)

    if validation.blocks:
        print("BLOCKED:", file=sys.stderr)
        for msg in validation.blocks:
            print(f"  - {msg}", file=sys.stderr)
        sys.exit(1)

    if validation.warnings:
        print("Warnings:", file=sys.stderr)
        for msg in validation.warnings:
            print(f"  - {msg}", file=sys.stderr)
        print("Use --force to push anyway.", file=sys.stderr)

    has_comment_ops = any(ops.has_operations for ops in per_sheet_comment_ops.values())
    has_changes = bool(requests) or has_comment_ops

    if not has_changes:
        print("No changes detected.")
    else:
        if requests:
            print(json.dumps(requests, indent=2))
        for sheet_folder, ops in per_sheet_comment_ops.items():
            if not ops.has_operations:
                continue
            parts: list[str] = []
            if ops.new_replies:
                parts.append(f"{len(ops.new_replies)} new reply/replies")
            if ops.resolves:
                parts.append(f"{len(ops.resolves)} resolve(s)")
            print(f"# {sheet_folder} comments: {', '.join(parts)}", file=sys.stderr)


def cmd_sheet_push(args: Any) -> None:
    """Push changes to a Google Sheet."""
    import asyncio

    from extrasheet import GoogleSheetsTransport, SheetsClient

    reason = _get_reason(args, default="Pushing changes to Google Sheet")
    cred = _get_credential(
        args,
        command={"type": "sheet.push", "file_url": "", "file_name": ""},
        reason=reason,
    )

    async def _run() -> None:
        transport = GoogleSheetsTransport(cred.token)
        client = SheetsClient(transport)
        try:
            result = client.push(args.folder, force=args.force)
            if asyncio.iscoroutine(result):
                result = await result
            print(result.message)
            if not result.success:
                sys.exit(1)
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_sheet_batchupdate(args: Any) -> None:
    """Execute raw batchUpdate requests."""
    import asyncio

    from extrasheet import GoogleSheetsTransport

    spreadsheet_id = _parse_spreadsheet_id(args.url)
    requests_path = Path(args.requests_file)
    if not requests_path.exists():
        print(f"Error: File not found: {requests_path}", file=sys.stderr)
        sys.exit(1)

    requests_data = json.loads(requests_path.read_text())
    if isinstance(requests_data, dict) and "requests" in requests_data:
        requests_list = requests_data["requests"]
    elif isinstance(requests_data, list):
        requests_list = requests_data
    else:
        print(
            "Error: Expected a list of requests or {requests: [...]}", file=sys.stderr
        )
        sys.exit(1)

    reason = _get_reason(args, default="Executing batchUpdate on Google Sheet")
    cred = _get_credential(
        args,
        command={
            "type": "sheet.batchupdate",
            "file_url": args.url,
            "file_name": "",
            "request_count": len(requests_list),
        },
        reason=reason,
    )

    async def _run() -> None:
        transport = GoogleSheetsTransport(cred.token)
        try:
            response = await transport.batch_update(spreadsheet_id, requests_list)
            print(f"Applied {len(requests_list)} requests.")
            if args.verbose:
                print(json.dumps(response, indent=2))
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_sheet_create(args: Any) -> None:
    """Create a new Google Sheet."""
    _cmd_create("sheet", args)


def cmd_sheet_share(args: Any) -> None:
    """Share a Google Sheet with trusted contacts."""
    _cmd_share("sheet", args)
