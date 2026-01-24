#!/usr/bin/env python3
"""
Google Sheets Skill - Verify Spreadsheet Access

Usage: venv/bin/python verify_access.py <spreadsheet_url>

Exit codes:
  0 - Success (spreadsheet info printed to stdout as JSON)
  1 - Authentication error
  2 - Spreadsheet not found or not shared
  3 - API not enabled
  4 - Rate limit exceeded
  5 - Invalid URL format
  6 - Other API error

Prerequisites: Run checks.py first to set up the environment.
"""

import sys

import gspread  # type: ignore[import-not-found]
from credentials import CredentialsManager
from google.oauth2.credentials import Credentials
from gspread.exceptions import APIError, SpreadsheetNotFound  # type: ignore[import-not-found]


def extract_spreadsheet_id(url):
    """Extract spreadsheet ID from URL. Returns (id, error_msg)."""
    if not url.startswith("http"):
        # Assume it's already an ID
        return url, None

    # Expected: https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/...
    parts = url.split("/")
    try:
        d_index = parts.index("d")
        return parts[d_index + 1], None
    except (ValueError, IndexError):
        return (
            None,
            f"Invalid Google Sheets URL format.\n\nExpected: https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit\nGot: {url}",
        )


def main():
    if len(sys.argv) < 2:
        print("Usage: venv/bin/python verify_access.py <spreadsheet_url>", file=sys.stderr)
        print("\nExample:", file=sys.stderr)
        print(
            "  venv/bin/python verify_access.py https://docs.google.com/spreadsheets/d/abc123/edit",
            file=sys.stderr,
        )
        sys.exit(1)

    url = sys.argv[1]
    spreadsheet_id, error = extract_spreadsheet_id(url)
    if error:
        print(error, file=sys.stderr)
        sys.exit(5)

    # Authenticate via ExtraSuite
    try:
        manager = CredentialsManager()
        token = manager.get_token()
        access_token = token.access_token
    except Exception as e:
        print(
            f"""Authentication failed.

Error: {e}

Please try again. If the problem persists, check:
- Your internet connection
- The ExtraSuite server is accessible""",
            file=sys.stderr,
        )
        sys.exit(1)

    client_email = token.service_account_email or "your service account"

    try:
        creds = Credentials(token=access_token)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(spreadsheet_id)

        # Success - gather spreadsheet info
        worksheets = []
        for ws in sh.worksheets():
            worksheets.append(
                {"title": ws.title, "id": ws.id, "rows": ws.row_count, "cols": ws.col_count}
            )

        # Print friendly message with spreadsheet title first
        print(f"Spreadsheet: {sh.title}")
        print(f"Worksheets: {', '.join(ws['title'] for ws in worksheets)}")
        sys.exit(0)

    except SpreadsheetNotFound:
        # Reconstruct the URL for the error message
        sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
        print(
            f"""Spreadsheet (ID: {spreadsheet_id}) not accessible.

To fix this:
1. Open the spreadsheet: {sheet_url}
2. Click the "Share" button (top right)
3. In the "Add people" field, enter: {client_email}
4. Select role: Editor (or Viewer if read-only access is sufficient)
5. Click "Send"

Then run this command again.""",
            file=sys.stderr,
        )
        sys.exit(2)

    except (APIError, PermissionError) as e:
        # Handle PermissionError which wraps APIError in gspread
        original_error = e.__cause__ if isinstance(e, PermissionError) and e.__cause__ else e
        error_str = str(original_error)
        status = getattr(original_error, "response", None)
        status_code = status.status_code if status else None

        # Check for API not enabled - multiple patterns
        api_not_enabled_patterns = [
            "PERMISSION_DENIED",
            "accessNotConfigured",
            "has not been used in project",
            "API has not been used",
            "is disabled",
            "Enable it by visiting",
        ]
        is_api_not_enabled = any(pattern in error_str for pattern in api_not_enabled_patterns)

        if is_api_not_enabled:
            print(
                """Google Sheets API is not enabled for the service account's project.

This is a server-side configuration issue. Please contact the administrator
of the ExtraSuite server.""",
                file=sys.stderr,
            )
            sys.exit(3)

        elif status_code == 403 or "403" in error_str:
            # Generic 403 - likely not shared
            sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
            print(
                f"""Spreadsheet (ID: {spreadsheet_id}) - Access forbidden.

To fix this:
1. Open the spreadsheet: {sheet_url}
2. Click the "Share" button (top right)
3. In the "Add people" field, enter: {client_email}
4. Select role: Editor (or Viewer if read-only access is sufficient)
5. Click "Send"

Then run this command again.""",
                file=sys.stderr,
            )
            sys.exit(2)

        elif status_code == 404 or "404" in error_str:
            print(
                f"""Spreadsheet (ID: {spreadsheet_id}) not found.

The spreadsheet does not exist or has been deleted.

Please verify:
- The URL is correct
- The spreadsheet has not been deleted""",
                file=sys.stderr,
            )
            sys.exit(2)

        elif status_code == 429 or "429" in error_str or "RATE_LIMIT" in error_str:
            print(
                """Rate limit exceeded.

Google Sheets API has usage quotas. Please wait 1-2 minutes and try again.""",
                file=sys.stderr,
            )
            sys.exit(4)

        else:
            # For unexpected errors, still provide actionable info
            sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
            print(
                f"""Spreadsheet (ID: {spreadsheet_id}) - Unable to access.

Error: {error_str}

Possible fixes:
1. Ensure the spreadsheet is shared with: {client_email}
2. Verify the URL is correct: {sheet_url}

Then run this command again.""",
                file=sys.stderr,
            )
            sys.exit(6)

    except Exception as e:
        # Catch-all with helpful context
        sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
        print(
            f"""Spreadsheet (ID: {spreadsheet_id}) - Unable to access.

Error: {type(e).__name__}: {e}

Possible fixes:
1. Ensure the spreadsheet is shared with: {client_email}
2. Verify the URL is correct: {sheet_url}

Then run this command again.""",
            file=sys.stderr,
        )
        sys.exit(6)


if __name__ == "__main__":
    main()
