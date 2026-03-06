# Extrasheet On-Disk Format Specification

Version: 2.4.0
Last Updated: 2026-03-06

This document describes the current on-disk format emitted by
`extrasuite sheet pull` / `SheetsClient.pull()`.

It was cross-checked against the implementation in `transformer.py`,
`client.py`, `diff.py`, and a live pull of spreadsheet
`1popsVtwuaYvGK8-ZkLIibesvbfnljjpUiOVWFMBMDkU`.

## Directory Structure

```text
<output_dir>/
  <spreadsheet_id>/
    spreadsheet.json
    theme.json                     # optional, informational
    named_ranges.json              # optional, editable
    developer_metadata.json        # optional, informational
    data_sources.json              # optional, informational
    <sheet_folder>/
      data.tsv
      formula.json
      format.json                  # optional
      dimension.json               # optional
      charts.json                  # optional
      pivot-tables.json            # optional
      tables.json                  # optional
      filters.json                 # optional
      banded-ranges.json           # optional
      data-validation.json         # optional
      slicers.json                 # optional
      data-source-tables.json      # optional
      protection.json              # optional, informational
      comments.json                # optional, replies/resolve only
    .raw/
      metadata.json                # omitted when pull uses --no-raw
      data.json
    .pristine/
      spreadsheet.zip
```

### File Creation Rules

- `spreadsheet.json` is always written.
- `data.tsv` and `formula.json` are always written for empty GRID sheets as stub
  files (`""` and `{}` respectively).
- Non-empty optional files are only written when the source spreadsheet has
  relevant content.
- `comments.json` is written per sheet only when Drive comments for that sheet
  exist.
- `.raw/*` is skipped when `--no-raw` / `save_raw=False` is used.

## Root-Level Files

### `spreadsheet.json`

Entry point for understanding the spreadsheet.

Example:

```json
{
  "spreadsheetId": "1popsVtwuaYvGK8-ZkLIibesvbfnljjpUiOVWFMBMDkU",
  "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/1popsVtwuaYvGK8-ZkLIibesvbfnljjpUiOVWFMBMDkU/edit",
  "properties": {
    "title": "R41 Interview COGS Model",
    "locale": "en_GB",
    "autoRecalc": "ON_CHANGE",
    "timeZone": "Asia/Calcutta"
  },
  "sheets": [
    {
      "sheetId": 177409360,
      "title": "Inputs",
      "index": 0,
      "sheetType": "GRID",
      "folder": "Inputs",
      "gridProperties": {
        "rowCount": 100,
        "columnCount": 10
      },
      "preview": {
        "firstRows": [["RECRUIT41 INTERVIEW COGS MODEL - INPUTS"]],
        "lastRows": [["Chunk Duration", "10", "minutes", ""]]
      }
    },
    {
      "sheetId": 657127928,
      "title": "Documentation",
      "index": 3,
      "sheetType": "GRID",
      "folder": "Documentation",
      "gridProperties": {
        "rowCount": 150,
        "columnCount": 5
      },
      "truncation": {
        "totalRows": 150,
        "fetchedRows": 100,
        "truncated": true
      }
    }
  ],
  "_truncationWarning": "Some sheets have partial data. Check each sheet's 'truncation' field for details."
}
```

Key points:

- `properties` only keeps `title`, `locale`, `autoRecalc`, and `timeZone`.
- `preview` exists only for GRID sheets.
- `hidden`, `rightToLeft`, `tabColor`, and `tabColorStyle` appear only when set.
- `truncation` appears on individual sheets when row limiting cut data short.
- `_truncationWarning` appears at the top level when any sheet was truncated.

Push support from this file:

- spreadsheet `properties.title`
- sheet `title`
- sheet `hidden`
- sheet `rightToLeft`
- sheet `tabColor` / `tabColorStyle`
- sheet `gridProperties.frozenRowCount`
- sheet `gridProperties.frozenColumnCount`
- new/delete sheet detection via the `sheets` list and sheet folders

Informational only today:

- `properties.locale`
- `properties.autoRecalc`
- `properties.timeZone`
- `preview`
- `truncation`
- `_truncationWarning`

### `theme.json`

Spreadsheet default format and theme metadata. Written when the spreadsheet has
`defaultFormat` or `spreadsheetTheme`.

This file is currently informational only. Diff/push does not apply edits to it.

Note: editable files use hex colors for concrete color values, but pull-only
metadata files may still contain API-style wrappers such as
`{"rgbColor": "#FFFFFF"}` or empty objects.

### `named_ranges.json`

Spreadsheet-level named ranges in A1 notation.

```json
{
  "namedRanges": [
    {
      "namedRangeId": "abc123",
      "name": "SalesData",
      "range": "Sheet1!A1:E100",
      "sheetId": 0
    }
  ]
}
```

This file is diffed and pushed.

### `developer_metadata.json`

Spreadsheet-level developer metadata.

Written on pull when present. Informational only today.

### `data_sources.json`

Spreadsheet-level external data source metadata and refresh schedules.

Written on pull when present. Informational only today.

### `.raw/metadata.json` and `.raw/data.json`

Raw API responses saved by default for debugging and golden-file creation.

These files are not part of the canonical editable representation and are not
included in `.pristine/spreadsheet.zip`.

### `.pristine/spreadsheet.zip`

Canonical snapshot of the pulled representation used by `diff` and `push`.

Re-pull after every successful push. The zip is not updated in place.

## Sheet Folder Naming

Sheet folders are based on sanitized sheet titles:

- invalid filesystem characters become `_`
- leading/trailing whitespace and dots are trimmed
- repeated underscores collapse
- if sanitization would collide, `_<sheetId>` is appended

Example:

- `Other Locations / Virtual` -> `Other Locations _ Virtual`

## Sheet-Level Files

### `data.tsv`

Tab-separated cell values.

Rules:

- Each line is one spreadsheet row.
- Each tab-separated field is one spreadsheet cell.
- Trailing empty rows and columns are trimmed.
- Formulas appear here as computed values, not formula text.
- Values are derived from `effectiveValue`.

Escaping:

- tab -> `\t`
- newline -> `\n`
- carriage return -> `\r`
- backslash -> `\\`

Typical value representation:

| Sheet value | TSV value |
|-------------|-----------|
| text | raw text |
| number | raw number like `1234.56` |
| boolean | `TRUE` / `FALSE` |
| date/time | serial number |
| error | API error message text |
| empty | empty string |

There are no explicit row or column numbers inside the file. Line number and
field position imply the grid position.

### `formula.json`

Sparse map of formulas by A1 cell or A1 range.

```json
{
  "B4": "=Inputs!C44/Inputs!B35",
  "B5:D5": "=B4*0.3"
}
```

Rules:

- keys are cell references or ranges
- values are the formula from the first cell in the range
- relative references auto-fill across compressed ranges
- computed results still live in `data.tsv`

Empty GRID sheets get `{}` so the sheet folder still exposes a writable formula
surface.

### `format.json`

Formatting for cells, merges, notes, and rich text.

```json
{
  "formatRules": [
    {
      "range": "A1:J1",
      "format": {
        "backgroundColor": "#CCCCCC",
        "textFormat": {
          "bold": true
        }
      }
    }
  ],
  "conditionalFormats": [
    {
      "ruleIndex": 0,
      "ranges": ["B2:B100"],
      "booleanRule": {
        "condition": {
          "type": "NUMBER_GREATER",
          "values": [{"userEnteredValue": "1000"}]
        },
        "format": {
          "backgroundColor": "#CCFFCC"
        }
      }
    }
  ],
  "merges": [
    {
      "range": "A1:D1"
    }
  ],
  "textFormatRuns": {
    "A1": [
      {"format": {}},
      {"startIndex": 5, "format": {"bold": true}}
    ]
  },
  "notes": {
    "A1": "Cell note text"
  }
}
```

Key points:

- concrete editable colors are normalized to hex strings
- `notes` are cell notes, not Drive comments
- `textFormatRuns` is keyed by cell A1 notation
- existing conditional format rules keep their `ruleIndex`
- new conditional format rules may omit `ruleIndex`; diff assigns one

### `dimension.json`

Row/column size and visibility metadata, plus some informational sections.

```json
{
  "rowMetadata": [
    {"row": 11, "pixelSize": 50, "hidden": true}
  ],
  "columnMetadata": [
    {"column": "A", "pixelSize": 150}
  ],
  "rowGroups": [
    {"range": "6:10", "depth": 1, "collapsed": false}
  ]
}
```

Writable today:

- `rowMetadata[].pixelSize`
- `rowMetadata[].hidden`
- `columnMetadata[].pixelSize`
- `columnMetadata[].hidden`

Informational only today:

- `rowGroups`
- `columnGroups`
- `developerMetadata`
- row/column `developerMetadata`

Conventions:

- row numbers are 1-based
- columns use letters

### `charts.json`

Embedded charts. Diff/push supports add/modify/delete.

### `pivot-tables.json`

Pivot tables keyed by `anchorCell`. Diff/push supports add/modify/delete.

### `tables.json`

Structured tables. Diff/push supports add/modify/delete.

### `filters.json`

Contains:

- `basicFilter`
- `filterViews`

Diff/push supports both.

### `banded-ranges.json`

Alternating row/column color definitions. Diff/push supports add/modify/delete.

### `data-validation.json`

Grouped validation rules.

```json
{
  "dataValidation": [
    {
      "range": "H2... (49 cells)",
      "cells": ["H2", "H3", "H4"],
      "rule": {
        "condition": {
          "type": "ONE_OF_LIST",
          "values": [{"userEnteredValue": "Keep"}]
        },
        "showCustomUi": true
      }
    }
  ]
}
```

Cells with identical rules are grouped together. The `range` field is only a
human-readable summary; `cells` is the canonical per-cell list.

### `slicers.json`

Interactive filter slicers. Diff/push supports add/modify/delete.

### `data-source-tables.json`

Tables backed by external data sources.

Current support is partial:

- modify/refresh-style changes are supported
- creating or deleting data source tables is not

### `protection.json`

Protected ranges and editor metadata.

This file is emitted on pull when present but is informational only today.

### `comments.json`

Drive comments for a single sheet.

```json
{
  "fileId": "spreadsheet_id",
  "comments": [
    {
      "id": "AAABzqZTYuo",
      "author": "Alice <alice@example.com>",
      "time": "2024-01-15T10:30:00.000Z",
      "resolved": false,
      "content": "Please double-check this formula",
      "quotedContent": "=SUM(B2:B10)",
      "replies": [
        {
          "id": "AAABzqZTYus",
          "author": "Bob <bob@example.com>",
          "time": "2024-01-15T11:00:00.000Z",
          "content": "Verified"
        }
      ]
    }
  ]
}
```

Notes:

- this is separate from `format.json.notes`
- it is written per sheet
- push supports adding replies and resolving comments
- push does not support creating new top-level comments

## Special Sheet Types

For non-GRID sheets:

- `spreadsheet.json` still lists the sheet
- no `data.tsv` or `formula.json` is written
- feature files may still be written

## Coordinate Conventions

- Cells and ranges in JSON files use A1 notation.
- `dimension.json` rows are 1-based and columns use letters.
- Internally, diff/request generation converts those references back to the
  Sheets API's 0-based indices.

## Practical Gotchas

- Start with `spreadsheet.json`; it usually tells you whether you need to open
  `data.tsv` at all.
- If a sheet is truncated, use `--no-limit` or a higher `--max-rows` before
  making decisions based on missing rows.
- Re-pull after push.
- Treat `theme.json`, `developer_metadata.json`, `data_sources.json`,
  `protection.json`, and grouping metadata as pull-only unless the code changes.
