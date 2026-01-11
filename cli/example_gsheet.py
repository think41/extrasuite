#!/usr/bin/env python3
"""Example: Using Fabric authentication with Google Sheets.

This script demonstrates how to integrate Fabric authentication
with the gspread library to access Google Sheets.

Prerequisites:
    pip install gspread

Usage:
    python example_gsheet.py <spreadsheet_url>
"""

import sys

# Import the fabric authentication module
from fabric_auth import get_token

# Try to import gspread
try:
    import gspread
    from google.oauth2.credentials import Credentials
except ImportError:
    print("Error: gspread is required. Install with: pip install gspread")
    sys.exit(1)


def get_gspread_client(fabric_server: str = "http://localhost:8001") -> gspread.Client:
    """Get an authenticated gspread client using Fabric token exchange.

    This function:
    1. Gets a valid SA token from Fabric (authenticating if needed)
    2. Creates OAuth2 credentials from the token
    3. Returns an authenticated gspread client

    Args:
        fabric_server: URL of the Fabric server

    Returns:
        Authenticated gspread.Client
    """
    # Get token from Fabric (will authenticate if needed)
    token = get_token(fabric_server)

    # Create credentials from the access token
    # Note: This is a short-lived token (1 hour), no refresh token
    credentials = Credentials(token=token)

    # Create and return gspread client
    return gspread.authorize(credentials)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python example_gsheet.py <spreadsheet_url>")
        print("\nExample:")
        print("  python example_gsheet.py https://docs.google.com/spreadsheets/d/abc123/edit")
        sys.exit(1)

    spreadsheet_url = sys.argv[1]

    try:
        # Get authenticated client
        print("Getting authenticated gspread client...")
        gc = get_gspread_client()

        # Open the spreadsheet
        print(f"Opening spreadsheet: {spreadsheet_url}")
        spreadsheet = gc.open_by_url(spreadsheet_url)

        # Print some info
        print(f"\nSpreadsheet: {spreadsheet.title}")
        print(f"Worksheets: {len(spreadsheet.worksheets())}")

        for ws in spreadsheet.worksheets():
            print(f"  - {ws.title} ({ws.row_count} rows, {ws.col_count} cols)")

        # Read first worksheet
        worksheet = spreadsheet.sheet1
        print(f"\nFirst 5 rows of '{worksheet.title}':")
        rows = worksheet.get_all_values()[:5]
        for i, row in enumerate(rows):
            print(f"  Row {i+1}: {row[:5]}{'...' if len(row) > 5 else ''}")

    except gspread.exceptions.SpreadsheetNotFound:
        print("\nError: Spreadsheet not found.")
        print("Make sure the spreadsheet is shared with your service account email.")
        print("You can find your SA email in ~/.config/fabric/token.json")
        sys.exit(1)
    except gspread.exceptions.APIError as e:
        print(f"\nAPI Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
