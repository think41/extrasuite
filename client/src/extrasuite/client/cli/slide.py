"""Slide CLI commands: pull, diff, push, create."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from extrasuite.client.cli._common import (
    _cmd_create,
    _cmd_share,
    _get_credential,
    _get_reason,
    _parse_presentation_id,
)


def cmd_slide_pull(args: Any) -> None:
    """Pull a Google Slides presentation."""
    from extraslide import GoogleSlidesTransport, SlidesClient

    presentation_id = _parse_presentation_id(args.url)
    output_dir_arg = args.output_dir
    reason = _get_reason(args, default="Pulling Google Slides")
    cred = _get_credential(
        args,
        command={"type": "slide.pull", "file_url": args.url, "file_name": ""},
        reason=reason,
    )

    tmp_parent = None
    if output_dir_arg:
        tmp_parent = Path(tempfile.mkdtemp())
        dest_dir = Path(output_dir_arg)
    else:
        dest_dir = Path() / presentation_id

    slide_count_holder: list[int] = []

    async def _run() -> None:
        transport = GoogleSlidesTransport(cred.token)
        client = SlidesClient(transport)
        pull_parent = tmp_parent if tmp_parent else Path()
        try:
            files = await client.pull(
                presentation_id,
                pull_parent,
                save_raw=not args.no_raw,
            )
            slide_count_holder.append(sum(1 for f in files if f.name == "content.sml"))
            if tmp_parent is not None:
                dest_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(tmp_parent / presentation_id), str(dest_dir))
        finally:
            await transport.close()

    try:
        asyncio.run(_run())
    finally:
        if tmp_parent is not None:
            shutil.rmtree(tmp_parent, ignore_errors=True)

    slide_count = slide_count_holder[0] if slide_count_holder else 0
    print(f"Pulled {slide_count} slide{'s' if slide_count != 1 else ''} to {dest_dir}/")


def cmd_slide_diff(args: Any) -> None:
    """Preview changes to a Google Slides presentation."""
    from extraslide import SlidesClient

    async def _run() -> None:
        client = SlidesClient.__new__(SlidesClient)
        requests = await client.diff(args.folder)
        if not requests:
            print("No changes detected.")
        else:
            print(json.dumps(requests, indent=2))

    asyncio.run(_run())


def cmd_slide_push(args: Any) -> None:
    """Push changes to a Google Slides presentation."""
    from extraslide import GoogleSlidesTransport, SlidesClient

    reason = _get_reason(args, default="Pushing changes to Google Slides")
    cred = _get_credential(
        args,
        command={"type": "slide.push", "file_url": "", "file_name": ""},
        reason=reason,
    )

    async def _run() -> None:
        transport = GoogleSlidesTransport(cred.token)
        client = SlidesClient(transport)
        try:
            response = await client.push(args.folder)
            count = len(response.get("replies", []))
            print(f"Push successful. Applied {count} changes.")
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_slide_create(args: Any) -> None:
    """Create a new Google Slides presentation and pull it locally."""
    from extraslide import GoogleSlidesTransport, SlidesClient

    file_id, url = _cmd_create("slide", args)

    output_dir_arg = getattr(args, "output_dir", None)
    tmp_parent = None
    if output_dir_arg:
        tmp_parent = Path(tempfile.mkdtemp())
        dest_dir = Path(output_dir_arg)
    else:
        dest_dir = Path() / file_id

    reason = _get_reason(
        args, default="Pulling newly created Google Slides presentation"
    )
    cred = _get_credential(
        args,
        command={"type": "slide.pull", "file_url": url, "file_name": args.title},
        reason=reason,
    )

    slide_count_holder: list[int] = []

    async def _run() -> None:
        transport = GoogleSlidesTransport(cred.token)
        client = SlidesClient(transport)
        pull_parent = tmp_parent if tmp_parent else Path()
        try:
            files = await client.pull(file_id, pull_parent, save_raw=True)
            slide_count_holder.append(sum(1 for f in files if f.name == "content.sml"))
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

    slide_count = slide_count_holder[0] if slide_count_holder else 0
    print(f"Pulled {slide_count} slide{'s' if slide_count != 1 else ''} to {dest_dir}/")


def cmd_slide_share(args: Any) -> None:
    """Share a Google Slides presentation with trusted contacts."""
    _cmd_share("slide", args)
