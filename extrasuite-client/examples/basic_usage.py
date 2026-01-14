#!/usr/bin/env python3
"""Basic usage example for ExtraSuite.

This script demonstrates the simplest way to get an access token
using the ExtraSuiteClient.

Usage:
    python basic_usage.py --server https://your-extrasuite-server.example.com
"""

import argparse

from extrasuite_client import ExtraSuiteClient


def main():
    parser = argparse.ArgumentParser(description="Basic ExtraSuite usage")
    parser.add_argument(
        "--server",
        required=True,
        help="ExtraSuite server URL",
    )
    args = parser.parse_args()

    # Create ExtraSuite client
    client = ExtraSuiteClient(server_url=args.server)

    # Get a token (will open browser if not cached)
    token = client.get_token()

    print("\nToken obtained successfully!")
    print(f"Token (first 50 chars): {token[:50]}...")


if __name__ == "__main__":
    main()
