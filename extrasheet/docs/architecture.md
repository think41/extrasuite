# ExtraSheet Architecture

Technical overview of the current `extrasheet` implementation.

## Overview

`extrasheet` sits between Google Sheets APIs and a local file representation used
by `extrasuite sheet`. The design goal is progressive disclosure: agents should
be able to start with `spreadsheet.json`, then load only the files needed for a
task.

```text
SheetsClient
  -> Transport (metadata, grid data, Drive comments, batchUpdate)
  -> SpreadsheetTransformer
  -> FileWriter
  -> .pristine snapshot for diff/push
```

## Pull Flow

`SheetsClient.pull()` does the following:

1. Fetch spreadsheet metadata without grid data.
2. Fetch grid data with the configured row limit.
3. Transform the API payload into `spreadsheet.json`, sheet files, and optional
   root-level files.
4. Write `.raw/metadata.json` and `.raw/data.json` unless `save_raw=False`.
5. Fetch Drive comments and write per-sheet `comments.json` files when present.
6. Zip the canonical pulled files into `.pristine/spreadsheet.zip`.

Important details:

- `spreadsheet.json` includes sheet previews and truncation metadata.
- Empty GRID sheets still produce an empty `data.tsv` and `{}` `formula.json`.
- Non-GRID sheets do not get `data.tsv` or `formula.json`; they may still emit
  feature files.

## On-Disk Model

Editable files in the declarative workflow:

- `spreadsheet.json`
- `data.tsv`
- `formula.json`
- `format.json`
- `dimension.json` for row/column size and hidden state
- `charts.json`
- `pivot-tables.json`
- `tables.json`
- `filters.json`
- `banded-ranges.json`
- `data-validation.json`
- `slicers.json`
- `data-source-tables.json` with limited support
- `named_ranges.json`
- `comments.json` with limited support

Pulled but currently informational:

- `theme.json`
- `developer_metadata.json`
- `data_sources.json`
- `protection.json`
- `rowGroups`, `columnGroups`, and `developerMetadata` inside `dimension.json`
- Spreadsheet-level `locale`, `autoRecalc`, and `timeZone`

## Diff/Push Flow

`SheetsClient.diff()` and `SheetsClient.push()` use the pulled zip as the source
of truth for the original state.

1. Read `.pristine/spreadsheet.zip`.
2. Read the current working files from disk.
3. Validate structural edits such as row/column insertions or deletions.
4. Diff spreadsheet metadata, sheet properties, cell data, formulas, formats,
   notes, rich text runs, dimensions, split feature files, and named ranges.
5. Generate Google Sheets `batchUpdate` requests.
6. Diff `comments.json` separately and apply comment replies/resolution through
   the Drive API after the Sheets requests succeed.

Actual spreadsheet-level push support is intentionally narrower than pull:

- Spreadsheet: title only
- Sheet properties: title, hidden, right-to-left, tab color, frozen rows, frozen
  columns
- Structure: new/delete sheet, insert/delete rows, insert/delete columns

## Why The Format Is Split

- `spreadsheet.json` stays small enough to inspect first.
- `data.tsv` is compact and easy to diff.
- `formula.json` keeps formulas separate from displayed values.
- `format.json` avoids forcing every task to load formatting data.
- Split feature files avoid the old monolithic `feature.json` while still
  remaining backward-compatible in the diff engine.

## Current Boundaries

- Theme/default format changes are not pushed.
- Protection and developer metadata are not pushed.
- Data source metadata is not pushed; data source tables only support refresh-
  style updates.
- Comments cannot be created from scratch because Sheets comments do not expose a
  stable A1-based anchor model through the public APIs used here.

See [on-disk-format.md](on-disk-format.md) for the file reference and
[diff-push-spec.md](diff-push-spec.md) for the exact editable surface.
