"""Slide CLI commands: pull, diff, push, create."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from extrasuite.client.cli._common import (
    _cmd_create,
    _get_token,
    _parse_presentation_id,
)


def cmd_slide_pull(args: Any) -> None:
    """Pull a Google Slides presentation."""
    from extraslide import GoogleSlidesTransport, SlidesClient

    presentation_id = _parse_presentation_id(args.url)
    output_dir = Path(args.output_dir) if args.output_dir else Path()
    access_token = _get_token(args, reason="Pulling Google Slides", scope="slide.pull")

    async def _run() -> None:
        transport = GoogleSlidesTransport(access_token)
        client = SlidesClient(transport)
        try:
            files = await client.pull(
                presentation_id,
                output_dir,
                save_raw=not args.no_raw,
            )
            slide_count = sum(1 for f in files if f.name == "content.sml")
            print(
                f"Pulled {slide_count} slide{'s' if slide_count != 1 else ''} to {output_dir / presentation_id}/"
            )
        finally:
            await transport.close()

    asyncio.run(_run())


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

    access_token = _get_token(
        args, reason="Pushing changes to Google Slides", scope="slide.push"
    )

    async def _run() -> None:
        transport = GoogleSlidesTransport(access_token)
        client = SlidesClient(transport)
        try:
            response = await client.push(args.folder)
            count = len(response.get("replies", []))
            print(f"Push successful. Applied {count} changes.")
        finally:
            await transport.close()

    asyncio.run(_run())


def cmd_slide_create(args: Any) -> None:
    """Create a new Google Slides presentation."""
    _cmd_create("slide", args)
