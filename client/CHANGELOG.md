# Changelog

All notable changes to the extrasuite client library will be documented in this file.

## [0.8.1] - 2026-03-27

### Added

- **`trust_all` option for Gmail** — power users can set `trust_all = true` in `[trusted_contacts]` of `~/.config/extrasuite/settings.toml` to allow reading email from any sender. Preserves security model (agent cannot modify the file).

### Fixed

- Keyring-based session storage now correctly supports multiple profiles.
- Headless auth displays the auth code on the page instead of redirecting to localhost.
- Fixed stale keyring install hint in auth docs.
- Corrected whitelist setup help doc (was referencing old `gmail_whitelist.json` format; now correctly documents `settings.toml`).

### Changed

- Reduced duplication in pull/push command help files.
- Updated minimum dependency versions: `extrasheet>=0.3.1`, `extraslide>=0.2.3`, `extraform>=0.3.1`, `extradoc>=0.4.1`.

## [0.8.0] - 2026-02-26

### Added

- **Session-token auth (v2 protocol):** One browser login per 30 days, then fully headless. The CLI no longer opens the browser mid-task.
- **`extrasuite auth login [--headless]`** — explicitly log in and obtain a 30-day session token. `--headless` prints the URL and prompts for a code on stdin instead of opening a browser.
- **`extrasuite auth logout`** — revokes session server-side and clears all cached credential files.
- **`extrasuite auth status`** — shows session validity, access token cache status, and OAuth token cache status.
- **`SessionToken` dataclass** — long-lived token stored at `~/.config/extrasuite/session.json`.
- **Device fingerprint collection** — MAC address, hostname, OS, and platform captured at session issuance for server-side audit.

### Changed

- Programmatic credential requests now require a `reason` keyword argument.
- DWD credential cache reduced to 10 minutes.
- All `extrasuite <module> pull/push` commands now use the headless session-token flow when a server URL is configured.

## [0.7.0] - 2026-02-18

### Added

- **`extrasuite contacts sync`** — syncs Google Contacts (people + other contacts) to a local SQLite DB at `~/.config/extrasuite/contacts.db`; supports full and incremental sync with automatic token-expiry fallback
- **`extrasuite contacts search <query>`** — multi-query fuzzy search ranked by source, touch frequency, recency, and domain clustering from touch sessions
- **`extrasuite contacts touch <email>`** — records interactions and groups emails into sessions for future ranking

### Changed

- Help text for `diff` commands simplified to one-liner "Debugging tool only" to discourage casual use
- `SKILL.md` rewritten for concision: shorter intro, `@latest` only on first command, added contacts/create examples

## [0.6.0] - 2026-02-18

### Added

- **`extrasuite gmail compose <file>`** — save a Gmail draft from a markdown file with YAML front matter; body is converted from markdown to HTML (headings, bold, lists, tables all render correctly in Gmail); plain-text fallback included for clients that don't render HTML
- **`extrasuite gmail edit-draft <draft_id> <file>`** — update an existing Gmail draft in place; draft ID is printed by `compose`
- **`extrasuite calendar view`** — list calendar events for a time range (`today`, `tomorrow`, `this-week`, `next-week`, `YYYY-MM-DD`)
- **`extrasuite <sheet|slide|doc|form> create <title>`** — create a new Google Workspace file and automatically share it with the service account
- **Bundled help system** — all `--help` text is now loaded from markdown files in `client/help/`, making it easy to update documentation without rebuilding

### Changed

- Bump `extradoc` dependency to `>=0.3.0` (paragraph styling reconciliation, Pydantic models)
- `gmail.compose` and `gmail.edit-draft` use OAuth delegation scope `gmail.compose`
- `calendar.view` uses OAuth delegation scope `calendar`
- File `create` commands use OAuth `drive.file` scope

### Added (dependencies)

- `markdown>=3.0` for markdown-to-HTML conversion in gmail commands

## [0.5.3] - 2026-02-12

### Changed

- Bump extradoc dependency to `>=0.2.2` (inline comment-ref support)
- Wire pull/diff/push with comment-ref flow for Google Docs comments

## [0.5.0] - 2026-02-11

### Breaking Changes

- Removed `login`/`logout` commands. Authentication is now stateless via per-command flags.

### Added

- Unified CLI with `extrasuite sheet/slide/form/doc/script pull/diff/push` subcommands.
- `--gateway` and `--service-account` flags on pull/push/create commands for per-command auth.
- Rich help text with folder layouts per module.
- `extrasuite` console script entry point.
- Now depends on all 5 modules (extrasheet, extraslide, extraform, extrascript, extradoc) at `>=0.2.0`.

## [0.4.0] - 2026-02-10

### Breaking Changes

- **Removed older convenience helpers.** Use `CredentialsManager` directly instead:

  ```python
  # Preferred
  from extrasuite.client import CredentialsManager
  manager = CredentialsManager()
  credential = manager.get_credential(
      command={"type": "sheet.pull"},
      reason="User requested spreadsheet access",
  )
  ```

- **Removed CLI entry point** (`extrasuite login`/`extrasuite logout`). The CLI was an
  internal testing tool. Use `CredentialsManager` programmatically instead.

- **Exports narrowed** - `__all__` now contains only `CredentialsManager`, `Token`, and
  `OAuthToken`.

## [0.3.0] - 2026-02-10

### Added

- **Domain-wide delegation support** - New `get_oauth_token()` method on `CredentialsManager`
  for obtaining user-level OAuth tokens via domain-wide delegation. This enables access to
  user-scoped Google APIs like Gmail and Calendar.
- New `OAuthToken` dataclass returned by `get_oauth_token()`, with `access_token`, `scopes`,
  and `expires_at` fields.
- Separate OAuth token cache at `~/.config/extrasuite/oauth_token.json` with scope-aware
  cache invalidation.

## [0.2.0] - 2026-02-05

### Changed

- **Token storage reverted to file-based caching** - Tokens are now stored in
  `~/.config/extrasuite/token.json` instead of the OS keyring.

  The keyring implementation caused repeated authentication prompts on some systems,
  disrupting the user experience. File-based storage is a well-established pattern
  used by major CLI tools:

  - `gcloud` stores credentials in `~/.config/gcloud/`
  - `aws-cli` stores credentials in `~/.aws/credentials`
  - `gh` (GitHub CLI) stores tokens in `~/.config/gh/`

  Additionally, ExtraSuite tokens are short-lived (typically 1 hour), making the
  security trade-off acceptable. Long-lived credentials would warrant more secure
  storage, but short-lived tokens expire before they can be meaningfully exploited.

  Token files are created with secure permissions (0600 - owner read/write only).

### Removed

- `keyring` dependency removed - the library now has zero required dependencies
- `certifi` is now optional (in `[ssl]` extras) for macOS SSL certificate handling

## [0.1.0] - 2026-01-28

### Added

- Initial release
- ExtraSuite protocol authentication via OAuth flow
- Service account file authentication
- Token caching via OS keyring (macOS Keychain, Windows Credential Locker, Linux Secret Service)
- CLI commands: `extrasuite login` and `extrasuite logout`
- Programmatic API: `CredentialsManager`
