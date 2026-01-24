#!/usr/bin/env python3
"""Basic usage example for ExtraSuite.

This script demonstrates the simplest way to get an access token
using the CredentialsManager.

Usage:
    python basic_usage.py \\
        --auth-url https://your-server.example.com/api/token/auth \\
        --exchange-url https://your-server.example.com/api/token/exchange
"""

import argparse

from extrasuite_client import CredentialsManager


def main():
    parser = argparse.ArgumentParser(description="Basic ExtraSuite usage")
    parser.add_argument(
        "--auth-url",
        required=True,
        help="URL to start authentication flow",
    )
    parser.add_argument(
        "--exchange-url",
        required=True,
        help="URL to exchange auth code for token",
    )
    args = parser.parse_args()

    # Create credentials manager
    manager = CredentialsManager(
        auth_url=args.auth_url,
        exchange_url=args.exchange_url,
    )

    # Get a token (will open browser if not cached)
    token = manager.get_token()

    print("\nToken obtained successfully!")
    print(f"Service account: {token.service_account_email}")
    print(f"Token (first 50 chars): {token.access_token[:50]}...")


if __name__ == "__main__":
    main()
