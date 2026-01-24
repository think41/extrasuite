"""
Google Sheets Utility Library

Functions that extend gspread with capabilities it doesn't have:
- open_sheet(): Simplified auth with URL using ExtraSuite
- get_shape(): Get first/last rows for LLM to assess table structure
- has_table(): Check if worksheet has a table
- convert_to_table(): Create a table via batchUpdate API (auto-removes banded ranges)
- delete_table(): Delete a table via batchUpdate API
- get_banded_ranges(): Check for existing banded ranges (alternating colors)
- remove_banded_ranges(): Remove banded ranges that block table creation
- get_service_account_email(): Get the service account email for sharing instructions

For standard operations (read, write, delete rows/columns, formatting),
use gspread directly - see gsheet.md for examples.
"""

import json
from pathlib import Path

import gspread  # type: ignore[import-not-found]
from credentials import CredentialsManager
from google.oauth2.credentials import Credentials

TOKEN_CACHE_PATH = Path.home() / ".config" / "extrasuite" / "token.json"


def _get_gspread_client():
    """Get an authenticated gspread client using ExtraSuite."""
    manager = CredentialsManager()
    token = manager.get_token()
    creds = Credentials(token=token.access_token)
    return gspread.authorize(creds)


def open_sheet(url):
    """
    Open a spreadsheet by URL with automatic authentication via ExtraSuite.

    Args:
        url: Full Google Sheets URL

    Returns:
        gspread.Spreadsheet object

    Example:
        sheet = open_sheet("https://docs.google.com/spreadsheets/d/abc123/edit")
        ws = sheet.worksheet("Sheet1")
    """
    if not url.startswith("http"):
        raise ValueError(f"Expected URL, got: {url}")

    gc = _get_gspread_client()
    return gc.open_by_url(url)


def get_shape(ws, header_rows=5, footer_rows=3):
    """
    Get worksheet shape for LLM to determine if data is/can be a table.

    Returns first few rows and last few rows so LLM can assess:
    - Does first row look like headers?
    - Are subsequent rows in consistent shape?
    - Are there empty rows/columns that should be trimmed?

    Args:
        ws: gspread.Worksheet object
        header_rows: Number of rows to fetch from top (default 5)
        footer_rows: Number of rows to fetch from bottom (default 3)

    Returns:
        dict with spreadsheet title, worksheet title, and shape information
    """
    sh = ws.spreadsheet
    all_values = ws.get_all_values()

    if not all_values:
        return {
            "spreadsheet": sh.title,
            "worksheet": ws.title,
            "total_rows": 0,
            "total_cols": 0,
            "first_rows": [],
            "last_rows": [],
            "has_data": False,
        }

    total_rows = len(all_values)
    total_cols = max(len(row) for row in all_values) if all_values else 0

    # Get first N rows
    first_rows = all_values[:header_rows]

    # Get last N rows (non-overlapping with first)
    if total_rows > header_rows + footer_rows:
        last_rows = all_values[-footer_rows:]
        last_row_start = total_rows - footer_rows + 1
    elif total_rows > header_rows:
        last_rows = all_values[header_rows:]
        last_row_start = header_rows + 1
    else:
        last_rows = []
        last_row_start = None

    return {
        "spreadsheet": sh.title,
        "worksheet": ws.title,
        "total_rows": total_rows,
        "total_cols": total_cols,
        "first_rows": first_rows,
        "first_row_numbers": list(range(1, len(first_rows) + 1)),
        "last_rows": last_rows,
        "last_row_numbers": list(range(last_row_start, last_row_start + len(last_rows)))
        if last_row_start
        else [],
        "has_data": total_rows > 0,
    }


def has_table(ws):
    """
    Check if worksheet has a table defined.

    Args:
        ws: gspread.Worksheet object

    Returns:
        dict with spreadsheet title, worksheet title, and table info
    """
    sh = ws.spreadsheet
    metadata = sh.fetch_sheet_metadata()

    for sheet in metadata.get("sheets", []):
        if sheet.get("properties", {}).get("sheetId") == ws.id:
            tables = sheet.get("tables", [])
            if tables:
                return {
                    "spreadsheet": sh.title,
                    "worksheet": ws.title,
                    "has_table": True,
                    "tables": [
                        {
                            "table_id": t.get("tableId"),
                            "name": t.get("name"),
                            "range": t.get("range"),
                            "columns": [
                                {
                                    "name": col.get("columnName"),
                                    "type": col.get("columnType"),
                                    "index": col.get("columnIndex"),
                                }
                                for col in t.get("columnProperties", [])
                            ],
                        }
                        for t in tables
                    ],
                }
    return {"spreadsheet": sh.title, "worksheet": ws.title, "has_table": False, "tables": []}


def get_banded_ranges(ws):
    """
    Get all banded ranges (alternating row colors) on a worksheet.

    Banded ranges can block table creation - they must be removed first.

    Args:
        ws: gspread.Worksheet object

    Returns:
        list of banded range dicts with 'id' and 'range' info
    """
    sh = ws.spreadsheet
    metadata = sh.fetch_sheet_metadata()

    for sheet in metadata.get("sheets", []):
        if sheet.get("properties", {}).get("sheetId") == ws.id:
            banded = sheet.get("bandedRanges", [])
            return [{"id": br.get("bandedRangeId"), "range": br.get("range")} for br in banded]
    return []


def remove_banded_ranges(ws):
    """
    Remove all banded ranges (alternating row colors) from a worksheet.

    This is required before converting to a table, as banded ranges
    conflict with table creation.

    Args:
        ws: gspread.Worksheet object

    Returns:
        dict with spreadsheet title, worksheet title, and count of removed ranges

    Note:
        Uses 'deleteBanding' API request (not 'deleteBandedRange').
    """
    banded = get_banded_ranges(ws)
    sh = ws.spreadsheet

    if not banded:
        return {"spreadsheet": sh.title, "worksheet": ws.title, "removed": 0}

    # IMPORTANT: The correct API field is 'deleteBanding', not 'deleteBandedRange'
    requests = [{"deleteBanding": {"bandedRangeId": br["id"]}} for br in banded]
    sh.batch_update({"requests": requests})

    return {"spreadsheet": sh.title, "worksheet": ws.title, "removed": len(banded)}


def convert_to_table(
    ws, name=None, start_row=1, start_col=1, end_row=None, end_col=None, auto_remove_banding=True
):
    """
    Convert worksheet data range to a table.

    Args:
        ws: gspread.Worksheet object
        name: Table name (defaults to worksheet title + "_table")
        start_row: Starting row (1-indexed, default 1)
        start_col: Starting column (1-indexed, default 1)
        end_row: Ending row (1-indexed, default last row with data)
        end_col: Ending column (1-indexed, default last column with data)
        auto_remove_banding: If True (default), automatically removes any existing
            banded ranges (alternating colors) that would block table creation.

    Returns:
        dict with created table info, including 'banding_removed' count

    Raises:
        gspread.exceptions.APIError: If banded ranges exist and auto_remove_banding=False
    """
    sh = ws.spreadsheet

    # Remove banded ranges first - they block table creation
    banding_removed = 0
    if auto_remove_banding:
        result = remove_banded_ranges(ws)
        banding_removed = result["removed"]

    if end_row is None or end_col is None:
        all_values = ws.get_all_values()
        if not all_values:
            raise ValueError("Worksheet has no data to convert to table")
        if end_row is None:
            end_row = len(all_values)
        if end_col is None:
            end_col = max(len(row) for row in all_values)

    if name is None:
        name = f"{ws.title}_table"

    # GridRange uses 0-indexed values
    table_range = {
        "sheetId": ws.id,
        "startRowIndex": start_row - 1,
        "endRowIndex": end_row,
        "startColumnIndex": start_col - 1,
        "endColumnIndex": end_col,
    }

    request = {"requests": [{"addTable": {"table": {"name": name, "range": table_range}}}]}

    response = sh.batch_update(request)

    return {
        "success": True,
        "spreadsheet": sh.title,
        "worksheet": ws.title,
        "table_name": name,
        "range": {
            "start_row": start_row,
            "end_row": end_row,
            "start_col": start_col,
            "end_col": end_col,
        },
        "banding_removed": banding_removed,
        "response": response,
    }


def delete_table(ws, table_id):
    """
    Delete a table from the worksheet.

    Args:
        ws: gspread.Worksheet object
        table_id: The table ID to delete

    Returns:
        dict with spreadsheet title, worksheet title, and result
    """
    sh = ws.spreadsheet

    request = {"requests": [{"deleteTable": {"tableId": table_id}}]}

    response = sh.batch_update(request)
    return {"success": True, "spreadsheet": sh.title, "worksheet": ws.title, "response": response}


def get_service_account_email():
    """
    Get the service account email for sharing instructions.

    Reads from the cached token file created by ExtraSuite.
    Returns None if no token is cached.
    """
    if not TOKEN_CACHE_PATH.exists():
        return None

    try:
        with open(TOKEN_CACHE_PATH) as f:
            token_data = json.load(f)
        return token_data.get("service_account_email")
    except (json.JSONDecodeError, KeyError):
        return None
