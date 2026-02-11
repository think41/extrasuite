# Changelog

All notable changes to the extrasheet library will be documented in this file.

## [0.2.0] - 2026-02-11

### Breaking Changes

- Removed CLI entry point (`python -m extrasheet`). Use `extrasuite sheet pull/diff/push` instead.
- Removed dependency on `extrasuite` (client) package.

## [0.1.0] - 2026-02-11

### Added

- Initial release
- **Pull**: Download Google Sheets to a local folder structure optimized for LLM agents
  - `data.tsv` - Cell values in tab-separated format
  - `formula.json` - Compressed formula definitions
  - `format.json` - Compressed cell formatting
  - Per-sheet feature files: charts, pivot tables, tables, filters, banded ranges, data validation, slicers, named ranges, dimensions
  - `spreadsheet.json` with metadata and data previews (first 5 / last 3 rows) for progressive disclosure
  - `theme.json` for default formatting and theme colors
  - `.pristine/` snapshot for diff comparison
  - `--max-rows` option (default 100) to prevent timeout on large spreadsheets
- **Diff**: Compare edited files against pristine state and generate `batchUpdate` JSON
- **Push**: Apply changes to Google Sheets via the API
- **batchUpdate**: Execute raw batchUpdate requests directly for structural operations
- **Supported change types**:
  - Cell value and formula changes (single cells and ranges with autoFill)
  - New sheet creation and sheet deletion (with cross-sheet reference validation)
  - Insert/delete rows and columns (with formula conflict validation)
  - All formatting: background color, number format, text format, alignment, borders
  - Column/row dimensions (width/height)
  - Sheet and spreadsheet properties (title, frozen rows/columns, hidden)
  - Conditional formatting (add, update, delete rules)
  - Data validation (dropdowns, checkboxes, etc.)
  - Rich text formatting (textFormatRuns) and cell notes
  - Cell merges
  - Basic filters and filter views
  - Banded ranges (alternating row/column colors)
  - Charts (add, update spec, update position, delete)
  - Pivot tables (add, modify, delete)
  - Tables (add, update, delete)
  - Named ranges (add, update, delete)
  - Slicers (add, update spec, update position, delete)
- **Structural change validation**: Detects conflicts between formula edits and row/column insertions/deletions
- **Two-phase push**: New sheets are created first, then all other changes are applied
- Async transport-based architecture with `GoogleSheetsTransport` and `LocalFileTransport` for testing
- Golden file testing infrastructure
- A1 notation used consistently across all on-disk formats
- Hex color format (`#FF0000`) used consistently across all files
