"""Drive CLI commands: ls, search."""

from __future__ import annotations

from typing import Any

from extrasuite.client.cli._common import _get_token, _parse_drive_file_id


def cmd_drive_ls(args: Any) -> None:
    """List files visible to the service account in Google Drive."""
    from extrasuite.client.google_api import format_drive_files, list_drive_files

    query_parts: list[str] = []
    if getattr(args, "folder", None):
        folder_id = _parse_drive_file_id(args.folder)
        query_parts.append(f"'{folder_id}' in parents")

    query = " and ".join(query_parts)
    access_token = _get_token(args, reason="Listing Drive files", scope="drive.ls")

    result = list_drive_files(
        access_token,
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

    access_token = _get_token(args, reason="Searching Drive files", scope="drive.ls")

    result = list_drive_files(
        access_token,
        query=args.query,
        page_size=args.max,
        page_token=args.page or "",
    )
    files = result.get("files", [])
    next_token = result.get("nextPageToken", "")
    print(format_drive_files(files, next_token))
