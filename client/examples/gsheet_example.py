#!/usr/bin/env python3
"""Example: Using Google Workspace Gateway with Google Sheets.

This script demonstrates how to integrate Google Workspace Gateway
with the gspread library to access Google Sheets.

Prerequisites:
    pip install gspread google-auth

Usage:
    python gsheet_example.py --server https://your-gwg-server.example.com <spreadsheet_url>
"""

import argparse
import sys

from google_workspace_gateway import GoogleWorkspaceGateway

# Try to import gspread
try:
    import gspread
    from google.oauth2.credentials import Credentials
except ImportError:
    print("Error: gspread and google-auth are required.")
    print("Install with: pip install gspread google-auth")
    sys.exit(1)


def get_gspread_client(server_url: str) -> gspread.Client:
    """Get an authenticated gspread client using Google Workspace Gateway.

    This function:
    1. Gets a valid SA token from the gateway (authenticating if needed)
    2. Creates OAuth2 credentials from the token
    3. Returns an authenticated gspread client

    Args:
        server_url: URL of the Google Workspace Gateway server

    Returns:
        Authenticated gspread.Client
    """
    # Create gateway and get token
    gateway = GoogleWorkspaceGateway(server_url=server_url)
    token = gateway.get_token()

    # Create credentials from the access token
    # Note: This is a short-lived token (1 hour), no refresh token
    credentials = Credentials(token=token)

    # Create and return gspread client
    return gspread.authorize(credentials)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Access Google Sheets using Google Workspace Gateway"
    )
    parser.add_argument(
        "--server",
        required=True,
        help="Google Workspace Gateway server URL",
    )
    parser.add_argument(
        "spreadsheet_url",
        help="URL of the Google Spreadsheet to access",
    )
    args = parser.parse_args()

    try:
        # Get authenticated client
        print("Getting authenticated gspread client...")
        gc = get_gspread_client(args.server)

        # Open the spreadsheet
        print(f"Opening spreadsheet: {args.spreadsheet_url}")
        spreadsheet = gc.open_by_url(args.spreadsheet_url)

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
        print("Check ~/.config/google-workspace-gateway/token.json for your SA email.")
        sys.exit(1)
    except gspread.exceptions.APIError as e:
        print(f"\nAPI Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
