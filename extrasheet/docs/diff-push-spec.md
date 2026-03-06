# Extrasheet Diff/Push Specification

Version: 2.0
Last Updated: 2026-03-06

This document describes what the current `extrasheet` diff/push path actually
reads, diffs, and sends back to Google.

## High-Level Flow

```text
.pristine/spreadsheet.zip + current files
  -> structural validation
  -> diff
  -> batchUpdate request generation
  -> Sheets API
  -> Drive comment operations (replies/resolution only)
```

`push` does not update `.pristine`. Re-pull after every successful push.

## Files Read By The Diff Engine

Root level:

- `spreadsheet.json`
- `theme.json` read from disk but currently ignored for diff/push
- `named_ranges.json`

Per sheet:

- `data.tsv`
- `formula.json`
- `format.json`
- `dimension.json`
- `feature.json` for backward compatibility only
- `charts.json`
- `pivot-tables.json`
- `tables.json`
- `filters.json`
- `banded-ranges.json`
- `data-validation.json`
- `slicers.json`
- `data-source-tables.json`

Handled outside the main diff engine:

- `comments.json`

Not currently read for push:

- `developer_metadata.json`
- `data_sources.json`
- `protection.json`

## Spreadsheet-Level Support

Supported from `spreadsheet.json`:

- `properties.title`

Pulled but informational only:

- `properties.locale`
- `properties.autoRecalc`
- `properties.timeZone`
- `_truncationWarning`
- `sheets[].preview`
- `sheets[].truncation`

## Sheet-Level Support

Supported from each entry in `spreadsheet.json`:

- `title`
- `hidden`
- `rightToLeft`
- `tabColor`
- `tabColorStyle`
- `gridProperties.frozenRowCount`
- `gridProperties.frozenColumnCount`

Also supported structurally:

- Add a new sheet by adding an entry/folder
- Delete a sheet by removing an entry/folder
- Insert/delete rows by editing `data.tsv`
- Insert/delete columns by editing `data.tsv`

## Per-File Behavior

### `data.tsv`

Supported:

- Cell value add/update/delete
- Row insertion/deletion inferred from grid shape changes
- Column insertion/deletion inferred from grid shape changes

Notes:

- Formula cells should stay blank in `data.tsv`; formulas belong in
  `formula.json`.
- Validation may block structural edits that would silently conflict with
  formula edits.

### `formula.json`

Supported:

- Add/update/delete formulas
- Compressed range formulas

### `format.json`

Supported:

- `formatRules`
- `conditionalFormats`
- `merges`
- `notes`
- `textFormatRuns`

Notes:

- Existing conditional formats keep their `ruleIndex`.
- New conditional format rules may omit `ruleIndex`; diff auto-assigns one after
  the highest existing index.

### `dimension.json`

Supported:

- `rowMetadata[].pixelSize`
- `rowMetadata[].hidden`
- `columnMetadata[].pixelSize`
- `columnMetadata[].hidden`

Pulled but ignored today:

- `rowGroups`
- `columnGroups`
- `developerMetadata`
- dimension-level `developerMetadata` entries inside row/column metadata

### Feature Files

Supported:

- `charts.json`
- `pivot-tables.json`
- `tables.json`
- `filters.json`
- `banded-ranges.json`
- `data-validation.json`
- `slicers.json`
- `named_ranges.json`

Partially supported:

- `data-source-tables.json`
  - refresh/modify-style operations are supported
  - creating or deleting data source tables is not

### `comments.json`

Supported:

- Add a reply by appending a reply object without an `id`
- Resolve a comment by setting `"resolved": true`

Not supported:

- Creating new top-level comments
- Moving comments to a different cell
- Editing historical author/time fields

## Request Ordering

The generated Sheets API requests are ordered like this:

1. Spreadsheet property changes
2. `addSheet`
3. Row/column grid changes
4. Sheet property changes
5. Cell/formula/format/dimension/feature changes
6. Named range changes
7. `deleteSheet`

Comment replies/resolution are executed after the Sheets API requests because
they go through Drive comments APIs, not `batchUpdate`.

## When To Use `batchUpdate` Directly

Use `extrasuite sheet batchUpdate` for operations that are not represented by
the declarative file model or are not yet wired into diff/push, for example:

- `sortRange`
- `moveDimension`
- `findReplace`
- `autoResizeDimensions`
- protection edits
- developer metadata edits
- spreadsheet locale/timezone/default-theme changes

## Validation Rules

Structural validation runs before push:

- `BLOCK`: structurally unsafe changes combined with formula edits
- `WARN`: changes likely to break existing formulas; push requires `--force`

Warnings do not stop `diff`; they do stop `push` unless forced.
