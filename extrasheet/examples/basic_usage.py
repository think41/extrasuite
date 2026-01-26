#!/usr/bin/env python3
"""
Basic usage example for extrasheet.

This example demonstrates how to use extrasheet to transform a Google Sheet
into a file-based representation.

Usage:
    # With real API access:
    python examples/basic_usage.py --spreadsheet-id YOUR_SPREADSHEET_ID --token YOUR_ACCESS_TOKEN

    # Transform from cached JSON (no API access needed):
    python examples/basic_usage.py --json-file path/to/spreadsheet.json
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from extrasheet import SheetsClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Transform Google Sheets to files")
    parser.add_argument(
        "--spreadsheet-id",
        help="Google Sheets spreadsheet ID",
    )
    parser.add_argument(
        "--token",
        help="OAuth2 access token with sheets.readonly scope",
    )
    parser.add_argument(
        "--json-file",
        type=Path,
        help="Path to cached spreadsheet JSON (for offline processing)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("./output"),
        help="Output directory (default: ./output)",
    )
    args = parser.parse_args()

    if args.json_file:
        # Transform from cached JSON file
        print(f"Transforming from cached JSON: {args.json_file}")
        with open(args.json_file) as f:
            json_data = json.load(f)

        client = SheetsClient(access_token="unused")  # Token not needed for cached data
        files = client.transform_from_json(json_data, args.output)

        print(f"\nWrote {len(files)} files:")
        for path in files:
            print(f"  {path}")

    elif args.spreadsheet_id and args.token:
        # Pull from Google Sheets API
        print(f"Pulling spreadsheet: {args.spreadsheet_id}")
        client = SheetsClient(access_token=args.token)

        try:
            files = client.pull(args.spreadsheet_id, args.output)
            print(f"\nWrote {len(files)} files:")
            for path in files:
                print(f"  {path}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    else:
        parser.print_help()
        print("\nError: Provide either --json-file or both --spreadsheet-id and --token")
        sys.exit(1)


if __name__ == "__main__":
    main()
