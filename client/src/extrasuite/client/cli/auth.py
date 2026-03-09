"""Auth CLI commands: login, logout, status, activate."""

from __future__ import annotations

import sys
from typing import Any

from extrasuite.client.cli._common import _auth_kwargs


def cmd_auth_login(args: Any) -> None:
    """Login and obtain a 30-day session token."""
    from datetime import datetime, timezone

    from extrasuite.client import CredentialsManager

    headless = getattr(args, "headless", False)
    profile = getattr(args, "profile", None)
    manager = CredentialsManager(**_auth_kwargs(args), headless=headless)

    # Check if a valid session already exists for the target profile.
    info = manager.status()
    resolved_profile = profile or info.get("active") or "default"
    profile_info = info.get("profiles", {}).get(resolved_profile)
    if profile_info and profile_info.get("active"):
        expires_dt = datetime.fromtimestamp(profile_info["expires_at"], tz=timezone.utc)
        print(
            f"Active session found for {profile_info['email']} "
            f"(profile: {resolved_profile}, expires {expires_dt.strftime('%Y-%m-%d')}, "
            f"{profile_info['days_remaining']}d remaining).",
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
    session = manager.login(force=True, profile=profile)
    expires_dt = datetime.fromtimestamp(session.expires_at, tz=timezone.utc)
    print(f"Logged in as {session.email} (profile: {resolved_profile}).")
    print(f"Session valid until {expires_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC.")


def cmd_auth_logout(args: Any) -> None:
    """Revoke session token and remove it from the OS keyring."""
    from extrasuite.client import CredentialsManager

    profile = getattr(args, "profile", None)
    manager = CredentialsManager(**_auth_kwargs(args))
    manager.logout(profile=profile)
    print("Logged out.")


def cmd_auth_status(args: Any) -> None:
    """Show current auth status."""
    from datetime import datetime, timezone

    from extrasuite.client import CredentialsManager

    manager = CredentialsManager(**_auth_kwargs(args))
    info = manager.status()

    profiles = info.get("profiles", {})
    active = info.get("active")

    if not profiles:
        print("No profiles found. Run: extrasuite auth login")
        return

    for name, pinfo in sorted(profiles.items()):
        marker = "* " if name == active else "  "
        if pinfo.get("active"):
            expires_dt = datetime.fromtimestamp(pinfo["expires_at"], tz=timezone.utc)
            print(
                f"{marker}{name}: active (email={pinfo['email']}, "
                f"expires={expires_dt.strftime('%Y-%m-%d')} UTC, "
                f"{pinfo['days_remaining']}d remaining)"
            )
        else:
            print(
                f"{marker}{name}: expired or invalid (email={pinfo['email']}). "
                f"Run: extrasuite auth login --profile {name}"
            )


def cmd_auth_activate(args: Any) -> None:
    """Set the active profile."""
    from extrasuite.client import CredentialsManager

    manager = CredentialsManager(**_auth_kwargs(args))
    manager.activate(args.profile_name)
    print(f"Active profile set to '{args.profile_name}'.")
