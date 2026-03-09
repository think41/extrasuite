"""Drive CLI commands: ls, search."""

from __future__ import annotations

from typing import Any

from extrasuite.client.cli._common import (
    _get_credential,
    _get_reason,
    _parse_drive_file_id,
)


def cmd_drive_ls(args: Any) -> None:
    """List files visible to the service account in Google Drive."""
    from extrasuite.client.google_api import format_drive_files, list_drive_files

    folder_url = getattr(args, "folder", "") or ""
    query_parts: list[str] = []
    if folder_url:
        folder_id = _parse_drive_file_id(folder_url)
        query_parts.append(f"'{folder_id}' in parents")

    query = " and ".join(query_parts)
    reason = _get_reason(args)
    cred = _get_credential(
        args,
        command={"type": "drive.ls", "folder_url": folder_url, "query": query},
        reason=reason,
    )

    result = list_drive_files(
        cred.token,
        query=query,
        page_size=args.max,
        page_token=args.page or "",
    )
    files = result.get("files", [])
    next_token = result.get("nextPageToken", "")
    print(format_drive_files(files, next_token))


def cmd_drive_search(args: Any) -> None:
    """Search files visible to the service account in Google Drive."""
    from extrasuite.client.google_api import format_drive_files, list_drive_files

    reason = _get_reason(args)
    cred = _get_credential(
        args,
        command={"type": "drive.search", "query": args.query},
        reason=reason,
    )

    result = list_drive_files(
        cred.token,
        query=args.query,
        page_size=args.max,
        page_token=args.page or "",
    )
    files = result.get("files", [])
    next_token = result.get("nextPageToken", "")
    print(format_drive_files(files, next_token))
