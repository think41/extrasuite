"""Script CLI commands: pull, diff, push, create, lint."""

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from extrasuite.client.cli._common import _cmd_share, _get_credential, _get_reason


def cmd_script_pull(args: Any) -> None:
    """Pull a Google Apps Script project."""
    from extrascript import GoogleAppsScriptTransport, ScriptClient
    from extrascript.client import parse_script_id

    script_id = parse_script_id(args.url)
    output_dir_arg = args.output_dir
    reason = _get_reason(args, default="Pull Apps Script project")
    cred = _get_credential(
        args,
        command={"type": "script.pull", "file_url": args.url, "file_name": ""},
        reason=reason,
    )

    tmp_parent = None
    if output_dir_arg:
        tmp_parent = Path(tempfile.mkdtemp())
        dest_dir = Path(output_dir_arg)
    else:
        dest_dir = Path() / script_id

    async def _run() -> None:
        transport = GoogleAppsScriptTransport(cred.token)
        client = ScriptClient(transport)
        pull_parent = tmp_parent if tmp_parent else Path()
        try:
            await client.pull(
                script_id,
                pull_parent,
                save_raw=not args.no_raw,
            )
            if tmp_parent is not None:
                dest_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(tmp_parent / script_id), str(dest_dir))
        finally:
            await transport.close()

    try:
        asyncio.run(_run())
    finally:
        if tmp_parent is not None:
            shutil.rmtree(tmp_parent, ignore_errors=True)

    print(f"Pulled to {dest_dir}/")


def cmd_script_diff(args: Any) -> None:
    """Preview changes to a Google Apps Script project."""
    from extrascript import ScriptClient

    client = ScriptClient.__new__(ScriptClient)
    diff_result = client.diff(args.folder)
    if not diff_result.has_changes:
        print("No changes detected.")
    else:
        if diff_result.added:
            print(f"Added: {', '.join(diff_result.added)}")
        if diff_result.removed:
            print(f"Removed: {', '.join(diff_result.removed)}")
        if diff_result.modified:
            print(f"Modified: {', '.join(diff_result.modified)}")


def cmd_script_push(args: Any) -> None:
    """Push changes to a Google Apps Script project."""
    from extrascript import GoogleAppsScriptTransport, ScriptClient

    reason = _get_reason(args, default="Push Apps Script project")
    cred = _get_credential(
        args,
        command={"type": "script.push", "file_url": "", "file_name": ""},
        reason=reason,
    )

    async def _run() -> None:
        transport = GoogleAppsScriptTransport(cred.token)
        client = ScriptClient(transport)
        try:
            if not args.skip_lint:
                lint_result = client.lint(args.folder)
                if lint_result.error_count > 0:
                    print("Lint errors found:", file=sys.stderr)
                    for d in lint_result.diagnostics:
                        print(f"  {d}", file=sys.stderr)
                    sys.exit(1)
                if lint_result.warning_count > 0:
                    print("Lint warnings:")
                    for d in lint_result.diagnostics:
                        print(f"  {d}")

            result = await client.push(args.folder)
            print(result.message)
            if not result.success:
                sys.exit(1)
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_script_create(args: Any) -> None:
    """Create a new Apps Script project."""
    from extrascript import GoogleAppsScriptTransport, ScriptClient
    from extrascript.client import parse_file_id

    reason = _get_reason(args, default="Create Apps Script project")
    bind_to = args.bind_to or ""
    cred = _get_credential(
        args,
        command={"type": "script.create", "title": args.title, "bind_to": bind_to},
        reason=reason,
    )
    parent_id = parse_file_id(bind_to) if bind_to else None
    output_dir = Path(args.output_dir) if args.output_dir else Path()

    async def _run() -> None:
        transport = GoogleAppsScriptTransport(cred.token)
        client = ScriptClient(transport)
        try:
            files = await client.create(
                args.title,
                output_dir,
                parent_id=parent_id,
            )
            print(f"Created project with {len(files)} files.")
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_script_lint(args: Any) -> None:
    """Lint an Apps Script project."""
    from extrascript import ScriptClient

    client = ScriptClient.__new__(ScriptClient)
    result = client.lint(args.folder)
    if result.diagnostics:
        for d in result.diagnostics:
            print(d)
        if result.error_count > 0:
            sys.exit(1)
    else:
        print("No lint issues found.")


def cmd_script_share(args: Any) -> None:
    """Share a Google Apps Script project with trusted contacts."""
    _cmd_share("script", args)
