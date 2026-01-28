"""CLI entry point for extrasuite.client.

Usage:
    python -m extrasuite.client login    # Authenticate with extrasuite-server
    python -m extrasuite.client logout   # Clear cached credentials
"""

import argparse
import sys

import keyring

from extrasuite.client.credentials import (
    KEYRING_SERVICE,
    KEYRING_USERNAME,
    CredentialsManager,
)


def cmd_login(args: argparse.Namespace) -> int:
    """Authenticate with extrasuite-server and cache token."""
    try:
        manager = CredentialsManager(
            auth_url=args.auth_url,
            exchange_url=args.exchange_url,
            service_account_path=args.service_account,
        )
        manager.get_token(force_refresh=args.force)
        return 0
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Authentication failed: {e}", file=sys.stderr)
        return 1


def cmd_logout(_args: argparse.Namespace) -> int:
    """Clear cached credentials from keyring."""
    try:
        # Check if there's a token to delete
        existing = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        if existing:
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
            print("Credentials cleared from keyring.")
        else:
            print("No cached credentials found.")
        return 0
    except keyring.errors.PasswordDeleteError:
        print("No cached credentials found.")
        return 0
    except Exception as e:
        print(f"Failed to clear credentials: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="extrasuite.client",
        description="ExtraSuite authentication CLI - manage Google API credentials",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # login subcommand
    login_parser = subparsers.add_parser(
        "login",
        help="Authenticate with extrasuite-server (opens browser)",
    )
    login_parser.add_argument(
        "--auth-url",
        help="URL to start authentication (or set EXTRASUITE_AUTH_URL env var)",
    )
    login_parser.add_argument(
        "--exchange-url",
        help="URL to exchange auth code (or set EXTRASUITE_EXCHANGE_URL env var)",
    )
    login_parser.add_argument(
        "--service-account",
        help="Path to service account JSON file (or set SERVICE_ACCOUNT_PATH env var)",
    )
    login_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force re-authentication even if cached token is valid",
    )
    login_parser.set_defaults(func=cmd_login)

    # logout subcommand
    logout_parser = subparsers.add_parser(
        "logout",
        help="Clear cached credentials from keyring",
    )
    logout_parser.set_defaults(func=cmd_logout)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
