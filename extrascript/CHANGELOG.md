# Changelog

All notable changes to the extrascript library will be documented in this file.

## [0.2.0] - 2026-02-11

### Breaking Changes

- Removed CLI entry point (`python -m extrascript`). Use `extrasuite script pull/push/lint` instead.
- Removed dependency on `extrasuite` (client) package.

### Changed

- Added `Transport` abstraction (`Transport` ABC, `GoogleAppsScriptTransport`, `LocalFileTransport`).
- Refactored `ScriptClient` to use Transport instead of direct HTTP.
- Moved `parse_script_id`/`parse_file_id` to `client.py`.
- Simplified test fixtures using `LocalFileTransport`.

## [0.1.0] - 2026-02-11

### Added

- Initial release
- **Pull**: Download Google Apps Script projects to a local folder
- **Push**: Upload local changes back to Google Apps Script
- **Lint**: Validate Apps Script files locally
- Async transport-based architecture
