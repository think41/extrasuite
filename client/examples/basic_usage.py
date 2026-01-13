#!/usr/bin/env python3
"""Basic usage example for Google Workspace Gateway.

This script demonstrates the simplest way to get an access token
using the GoogleWorkspaceGateway client.

Usage:
    python basic_usage.py --server https://your-gwg-server.example.com
"""

import argparse

from google_workspace_gateway import GoogleWorkspaceGateway


def main():
    parser = argparse.ArgumentParser(description="Basic Google Workspace Gateway usage")
    parser.add_argument(
        "--server",
        required=True,
        help="Google Workspace Gateway server URL",
    )
    args = parser.parse_args()

    # Create gateway client
    gateway = GoogleWorkspaceGateway(server_url=args.server)

    # Get a token (will open browser if not cached)
    token = gateway.get_token()

    print("\nToken obtained successfully!")
    print(f"Token (first 50 chars): {token[:50]}...")


if __name__ == "__main__":
    main()
