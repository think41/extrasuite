"""Maps Command types to credential generation logic.

This module is the single source of truth for:

- Which commands need a service-account (SA) token vs. a domain-wide-delegation
  (DWD) token
- Which Google OAuth scopes each DWD command requires
- Server-side scope allowlist enforcement

Extending to new providers:
  Add a new command type to ``_SA_COMMAND_TYPES`` or ``_DWD_COMMAND_SCOPES`` and
  the ``CommandCredentialRouter`` will route it correctly at runtime.
  The ``TokenResponse.credentials`` list can contain tokens for multiple providers
  simultaneously if an operation needs them.
"""

from __future__ import annotations

from pydantic import BaseModel

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
