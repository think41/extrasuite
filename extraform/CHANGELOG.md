# Changelog

All notable changes to the extraform library will be documented in this file.

## [0.3.1] - 2026-03-27

### Changed

- Removed stale auth guidance from package docs (auth is handled by `extrasuite` client).

## [0.3.0] - 2026-03-04

### Added

- **DAG-based multi-batch push** — the push engine now resolves cross-dependencies between new items (e.g., a `goToSectionId` referencing a newly created section) by splitting requests into ordered batches. `DeferredItemID` placeholders are resolved after each batch using the API's reply.
- **Post-push sync** — after a successful push, `form.json` and `.pristine/` are automatically rewritten from the API response, so API-assigned IDs are reflected immediately without requiring a re-pull.

## [0.2.0] - 2026-02-11

### Breaking Changes

- Removed CLI entry point (`python -m extraform`). Use `extrasuite form pull/diff/push` instead.
- Removed dependency on `extrasuite` (client) package.
- Removed `[project.scripts]` entry point.

## [0.1.0] - 2026-02-11

### Added

- Initial release
- **Pull**: Download Google Forms to a local folder with a clean JSON representation
  - `form.json` - Complete form structure (questions, sections, settings)
  - `.pristine/` snapshot for diff comparison
- **Diff**: Compare edited form against pristine state and generate `batchUpdate` JSON
- **Push**: Apply changes to Google Forms via the API
- **Supported operations**:
  - Form title and description changes
  - Settings changes (quiz mode, email collection)
  - Add, delete, update, and reorder questions
  - All question types: short answer, long answer, multiple choice, checkboxes, dropdown, linear scale, date, time, rating
  - Section dividers (pageBreakItem) and static text (textItem)
- **Smart move handling**: Simulates sequential move operations to generate correct indices when reordering items
- Async transport-based architecture with `GoogleFormsTransport` and `LocalFileTransport` for testing
- Golden file testing infrastructure
