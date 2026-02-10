"""CLI entry point for extrasuite.client.

Usage:
    python -m extrasuite.client login      # Authenticate with extrasuite-server
    python -m extrasuite.client logout     # Clear cached credentials
    python -m extrasuite.client authorize  # Get delegated token for user-level APIs
"""

import argparse
import sys

from extrasuite.client.credentials import CredentialsManager


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


def cmd_authorize(args: argparse.Namespace) -> int:
    """Get a delegated OAuth token for user-level API access."""
    try:
        scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
        if not scopes:
            print("Error: --scopes is required", file=sys.stderr)
            return 1

        manager = CredentialsManager(
            auth_url=args.auth_url,
            exchange_url=args.exchange_url,
        )
        token = manager.get_oauth_token(
            scopes,
            reason=args.reason or "",
            force_refresh=args.force,
        )
        if args.show_token:
            print(f"\nAccess Token:\n{token.access_token}")
        return 0
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Authorization failed: {e}", file=sys.stderr)
        return 1


def cmd_logout(_args: argparse.Namespace) -> int:
    """Clear cached credentials from token file."""
    token_path = CredentialsManager.DEFAULT_CACHE_PATH
    try:
        if token_path.exists():
            token_path.unlink()
            print(f"Credentials cleared from {token_path}")
        else:
            print("No cached credentials found.")
        return 0
    except OSError as e:
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

    # authorize subcommand
    authorize_parser = subparsers.add_parser(
        "authorize",
        help="Get delegated token for user-level APIs (Gmail, Calendar, etc.)",
    )
    authorize_parser.add_argument(
        "--scopes",
        required=True,
        help="Comma-separated scope aliases (e.g., gmail.send,calendar)",
    )
    authorize_parser.add_argument(
        "--reason",
        help="Reason for requesting access (logged server-side for audit)",
    )
    authorize_parser.add_argument(
        "--auth-url",
        help="URL to start authentication (or set EXTRASUITE_AUTH_URL env var)",
    )
    authorize_parser.add_argument(
        "--exchange-url",
        help="URL to exchange auth code (or set EXTRASUITE_EXCHANGE_URL env var)",
    )
    authorize_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force re-authorization even if cached token is valid",
    )
    authorize_parser.add_argument(
        "--show-token",
        action="store_true",
        help="Print the access token to stdout",
    )
    authorize_parser.set_defaults(func=cmd_authorize)

    # logout subcommand
    logout_parser = subparsers.add_parser(
        "logout",
        help="Clear cached credentials",
    )
    logout_parser.set_defaults(func=cmd_logout)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
