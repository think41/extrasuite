"""Maps Command types to credential generation logic.

This module is the single source of truth for:

- Which commands need a service-account (SA) token vs. a domain-wide-delegation
  (DWD) token
- Which Google OAuth scopes each DWD command requires
- Server-side scope allowlist enforcement

Extending to new providers:
  Add a new branch in ``resolve_credentials`` that returns ``Credential`` objects
  with a different ``provider`` value (e.g. ``"slack"``, ``"github"``).  The
  ``TokenResponse.credentials`` list can contain tokens for multiple providers
  simultaneously if an operation needs them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from extrasuite.server.commands import Command
    from extrasuite.server.token_generator import TokenGenerator

_GOOGLE_SCOPE_PREFIX = "https://www.googleapis.com/auth/"

# ---------------------------------------------------------------------------
# Command → credential type mapping
# ---------------------------------------------------------------------------

# Commands that use a per-user service account (SA) token.
# The SA token grants access to Sheets / Docs / Slides / Forms / Drive APIs
# via IAM permissions — no explicit OAuth scopes are requested.
_SA_COMMAND_TYPES: frozenset[str] = frozenset(
    {
        "sheet.pull",
        "sheet.push",
        "sheet.batchupdate",
        "doc.pull",
        "doc.push",
        "slide.pull",
        "slide.push",
        "form.pull",
        "form.push",
        "drive.ls",
        "drive.search",
    }
)

# Commands that use domain-wide delegation (DWD).
# Maps command type → list of full Google OAuth scope URLs.
# Multi-scope commands (e.g. gmail.reply) mint a single DWD token covering all
# listed scopes — no need for the client to make multiple requests.
_DWD_COMMAND_SCOPES: dict[str, list[str]] = {
    "gmail.compose": [f"{_GOOGLE_SCOPE_PREFIX}gmail.compose"],
    "gmail.edit_draft": [f"{_GOOGLE_SCOPE_PREFIX}gmail.compose"],
    "gmail.reply": [
        f"{_GOOGLE_SCOPE_PREFIX}gmail.readonly",
        f"{_GOOGLE_SCOPE_PREFIX}gmail.compose",
    ],
    "gmail.list": [f"{_GOOGLE_SCOPE_PREFIX}gmail.readonly"],
    "gmail.read": [f"{_GOOGLE_SCOPE_PREFIX}gmail.readonly"],
    "calendar.view": [f"{_GOOGLE_SCOPE_PREFIX}calendar"],
    "calendar.list": [f"{_GOOGLE_SCOPE_PREFIX}calendar"],
    "calendar.search": [f"{_GOOGLE_SCOPE_PREFIX}calendar"],
    "calendar.freebusy": [f"{_GOOGLE_SCOPE_PREFIX}calendar"],
    "calendar.create": [f"{_GOOGLE_SCOPE_PREFIX}calendar"],
    "calendar.update": [f"{_GOOGLE_SCOPE_PREFIX}calendar"],
    "calendar.delete": [f"{_GOOGLE_SCOPE_PREFIX}calendar"],
    "calendar.rsvp": [f"{_GOOGLE_SCOPE_PREFIX}calendar"],
    "contacts.read": [f"{_GOOGLE_SCOPE_PREFIX}contacts.readonly"],
    "contacts.other": [f"{_GOOGLE_SCOPE_PREFIX}contacts.other.readonly"],
    "drive.file.create": [f"{_GOOGLE_SCOPE_PREFIX}drive.file"],
    "drive.file.share": [f"{_GOOGLE_SCOPE_PREFIX}drive.file"],
    "script.pull": [f"{_GOOGLE_SCOPE_PREFIX}script.projects"],
    "script.push": [f"{_GOOGLE_SCOPE_PREFIX}script.projects"],
    "script.create": [f"{_GOOGLE_SCOPE_PREFIX}script.projects"],
}

_ALL_COMMAND_TYPES: frozenset[str] = _SA_COMMAND_TYPES | frozenset(_DWD_COMMAND_SCOPES)


# ---------------------------------------------------------------------------
# Response model (provider-agnostic credential)
# ---------------------------------------------------------------------------


class Credential(BaseModel):
    """A single credential issued for a specific provider.

    Designed to be extensible: future providers (Slack, GitHub, etc.) add
    entries to the ``credentials`` list in ``TokenResponse`` without changing
    this interface.
    """

    provider: str = "google"
    kind: str  # "bearer_sa" | "bearer_dwd" | "api_key" | …
    token: str
    expires_at: str  # ISO 8601; empty string if non-expiring
    scopes: list[str] = []  # OAuth scopes granted (empty for SA tokens)
    metadata: dict[str, str] = {}  # provider-specific extras (e.g. service_account_email)


# ---------------------------------------------------------------------------
# Core resolution function
# ---------------------------------------------------------------------------


async def resolve_credentials(
    command: Command,
    email: str,
    token_generator: TokenGenerator,
    settings: Any,  # Settings — passed as Any to avoid circular import
) -> list[Credential]:
    """Validate the command, check allowlists, and generate credential(s).

    Returns a list because future commands may require tokens from multiple
    providers simultaneously.

    Raises:
        ValueError: Unknown command type (should not happen if validation passed).
        HTTPException(403): Scope not permitted by server configuration.
        DelegationError: DWD token generation failed.
    """
    from fastapi import HTTPException

    cmd_type = command.type

    if cmd_type not in _ALL_COMMAND_TYPES:
        raise ValueError(f"Unknown command type: {cmd_type!r}")

    if cmd_type in _SA_COMMAND_TYPES:
        result = await token_generator.generate_token(email)
        return [
            Credential(
                provider="google",
                kind="bearer_sa",
                token=result.token,
                expires_at=result.expires_at.isoformat(),
                scopes=[],
                metadata={"service_account_email": result.service_account_email},
            )
        ]

    # DWD path
    scopes = _DWD_COMMAND_SCOPES[cmd_type]

    # Enforce server-side scope allowlist for each requested scope
    disallowed = [s for s in scopes if not settings.is_scope_allowed(s)]
    if disallowed:
        short_names = [s.removeprefix(_GOOGLE_SCOPE_PREFIX) for s in disallowed]
        raise HTTPException(
            status_code=403,
            detail=f"Scope(s) {short_names!r} are not permitted by server configuration.",
        )

    result = await token_generator.generate_delegated_token(email, scopes)
    return [
        Credential(
            provider="google",
            kind="bearer_dwd",
            token=result.token,
            expires_at=result.expires_at.isoformat(),
            scopes=scopes,
            metadata={"service_account_email": result.service_account_email},
        )
    ]
