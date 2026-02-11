# Changelog

All notable changes to the extraform library will be documented in this file.

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
