"""
CLI entry point for extrasheet.

Usage:
    python -m extrasheet download <spreadsheet_id_or_url> <output_dir>
"""

import argparse
import re
import sys
from pathlib import Path

from extrasheet import SheetsClient
from extrasheet.credentials import CredentialsManager


def parse_spreadsheet_id(id_or_url: str) -> str:
    """Extract spreadsheet ID from a URL or return as-is if already an ID."""
    # Pattern to match Google Sheets URLs
    # https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit...
    url_pattern = r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)"
    match = re.search(url_pattern, id_or_url)
    if match:
        return match.group(1)
    # Assume it's already an ID
    return id_or_url


def cmd_download(args: argparse.Namespace) -> int:
    """Download a spreadsheet to local files."""
    spreadsheet_id = parse_spreadsheet_id(args.spreadsheet)
    output_path = Path(args.output)

    # Get token via CredentialsManager
    print("Authenticating...")
    try:
        manager = CredentialsManager()
        token_obj = manager.get_token()
    except Exception as e:
        print(f"Authentication failed: {e}", file=sys.stderr)
        return 1

    # Pull spreadsheet
    max_rows = None if args.no_limit else args.max_rows
    if max_rows:
        print(
            f"Downloading spreadsheet: {spreadsheet_id} (limited to {max_rows} rows per sheet)"
        )
    else:
        print(f"Downloading spreadsheet: {spreadsheet_id} (fetching all rows)")
    client = SheetsClient(access_token=token_obj.access_token)

    try:
        files = client.pull(
            spreadsheet_id, output_path, save_raw=args.save_raw, max_rows=max_rows
        )
        print(f"\nWrote {len(files)} files to {output_path}:")
        for path in files:
            print(f"  {path}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="extrasheet",
        description="Transform Google Sheets to LLM-friendly file format",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # download subcommand
    download_parser = subparsers.add_parser(
        "download",
        help="Download a spreadsheet to local files",
    )
    download_parser.add_argument(
        "spreadsheet",
        help="Spreadsheet ID or full Google Sheets URL",
    )
    download_parser.add_argument(
        "output",
        help="Output directory",
    )
    download_parser.add_argument(
        "--save-raw",
        action="store_true",
        help="Also save the raw API response",
    )
    download_parser.add_argument(
        "--max-rows",
        type=int,
        default=100,
        help="Maximum number of rows to fetch per sheet (default: 100)",
    )
    download_parser.add_argument(
        "--no-limit",
        action="store_true",
        help="Fetch all rows (may timeout on large spreadsheets)",
    )
    download_parser.set_defaults(func=cmd_download)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
