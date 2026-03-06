"""Auth CLI commands: login, logout, status."""

from __future__ import annotations

import sys
from typing import Any

from extrasuite.client.cli._common import _auth_kwargs


def cmd_auth_login(args: Any) -> None:
    """Login and obtain a 30-day session token."""
    from datetime import datetime, timezone

    from extrasuite.client import CredentialsManager

    headless = getattr(args, "headless", False)
    manager = CredentialsManager(**_auth_kwargs(args), headless=headless)

    # If a valid session already exists, warn before revoking it.
    info = manager.status()
    if info.get("session") and info["session"].get("active"):
        existing = info["session"]
        expires_dt = datetime.fromtimestamp(existing["expires_at"], tz=timezone.utc)
        print(
            f"Active session found for {existing['email']} "
            f"(expires {expires_dt.strftime('%Y-%m-%d')}, "
            f"{existing['days_remaining']}d remaining).",
            file=sys.stderr,
        )
        if sys.stdin.isatty():
            response = input("Re-login and revoke current session? [y/N] ")
            if response.strip().lower() not in ("y", "yes"):
                print("Login cancelled.")
                return

    print(
        "Note: device fingerprint (MAC address, hostname, OS) will be sent to the server for audit.",
        file=sys.stderr,
    )
    session = manager.login(force=True)
    expires_dt = datetime.fromtimestamp(session.expires_at, tz=timezone.utc)
    print(f"Logged in as {session.email}.")
    print(f"Session valid until {expires_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC.")


def cmd_auth_logout(args: Any) -> None:
    """Revoke session token and clear cached credentials."""
    from extrasuite.client import CredentialsManager

    manager = CredentialsManager(**_auth_kwargs(args))
    manager.logout()
    print("Logged out.")


def cmd_auth_status(args: Any) -> None:
    """Show current auth status."""
    from datetime import datetime, timezone

    from extrasuite.client import CredentialsManager

    manager = CredentialsManager(**_auth_kwargs(args))
    info = manager.status()

    session = info["session"]
    if session:
        expires_dt = datetime.fromtimestamp(session["expires_at"], tz=timezone.utc)
        print(
            f"Session: active (email={session['email']}, expires={expires_dt.strftime('%Y-%m-%d')} UTC, {session['days_remaining']}d remaining)"
        )
    else:
        print("Session: not found or expired. Run: extrasuite auth login")

    credentials = info["credentials"]
    if not credentials:
        print("Credentials: not cached")
        return

    print("Credentials:")
    for command_type, cred_info in sorted(credentials.items()):
        if cred_info.get("invalid"):
            print(f"  {command_type}: invalid cache")
            continue
        state = "cached" if cred_info.get("cached") else "expired"
        expires_dt = datetime.fromtimestamp(cred_info["expires_at"], tz=timezone.utc)
        print(
            f"  {command_type}: {state} ({cred_info['kind']}, expires={expires_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC)"
        )
