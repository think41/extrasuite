# Changelog

All notable changes to the extrasuite client library will be documented in this file.

## [0.4.0] - 2026-02-10

### Breaking Changes

- **Removed `authenticate()` and `get_oauth_token()` convenience functions.** Use
  `CredentialsManager` directly instead:

  ```python
  # Before (0.3.x)
  from extrasuite.client import authenticate
  token = authenticate()

  # After (0.4.0)
  from extrasuite.client import CredentialsManager
  manager = CredentialsManager()
  token = manager.get_token()
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
- Programmatic API: `authenticate()` and `CredentialsManager`
