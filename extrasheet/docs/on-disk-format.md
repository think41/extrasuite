# Extrasheet On-Disk Format Specification

Version: 2.0.0
Last Updated: 2026-01-27

## Overview

Extrasheet transforms Google Sheets spreadsheets into a file-based representation. The format separates data, formulas, formatting, and features into distinct files to enable token-efficient loading by LLM agents.

This document describes the current implementation's output format.

## Directory Structure

```
<output_dir>/
└── <spreadsheet_id>/
    ├── spreadsheet.json           # Spreadsheet metadata and sheet index
    ├── named_ranges.json          # Named ranges (if any exist)
    ├── developer_metadata.json    # Developer metadata (if any exist)
    ├── data_sources.json          # External data sources (if any exist)
    └── <sheet_folder>/            # One folder per sheet
        ├── data.tsv               # Cell values as tab-separated values
        ├── formula.json           # Formulas (sparse representation)
        ├── format.json            # Cell formatting
        ├── feature.json           # Charts, pivots, filters, validation, etc.
        ├── dimension.json         # Row/column sizing and groups
        └── protection.json        # Protected ranges (if any exist)
```

### Sheet Folder Naming

Sheet folders are named using the sanitized sheet title:
- Invalid filesystem characters (`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`) are replaced with `_`
- Leading/trailing whitespace and dots are trimmed
- Multiple consecutive underscores are collapsed to one
- If duplicate folder names exist after sanitization, `_<sheetId>` is appended

Example: Sheet "Other Locations / Virtual" becomes folder `Other Locations _ Virtual`

### File Creation Rules

Files are only created when they contain meaningful data:
- `formula.json` - Only if sheet has formulas
- `format.json` - Only if sheet has non-default formatting, conditional formats, merges, text runs, or notes
- `feature.json` - Only if sheet has charts, pivots, filters, tables, slicers, banded ranges, or data validation
- `dimension.json` - Only if sheet has non-default row/column sizes, groups, or dimension metadata
- `protection.json` - Only if sheet has protected ranges
- `named_ranges.json` - Only if spreadsheet has named ranges
- `developer_metadata.json` - Only if spreadsheet has developer metadata
- `data_sources.json` - Only if spreadsheet has external data sources

---

## Spreadsheet-Level Files

### spreadsheet.json

Contains spreadsheet metadata and an index of all sheets.

```json
{
  "spreadsheetId": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
  "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/.../edit",
  "properties": {
    "title": "My Spreadsheet",
    "locale": "en_US",
    "autoRecalc": "ON_CHANGE",
    "timeZone": "America/New_York",
    "defaultFormat": { /* CellFormat */ },
    "spreadsheetTheme": { /* SpreadsheetTheme */ }
  },
  "sheets": [
    {
      "sheetId": 0,
      "title": "Sheet1",
      "index": 0,
      "sheetType": "GRID",
      "folder": "Sheet1",
      "gridProperties": {
        "rowCount": 1000,
        "columnCount": 26,
        "frozenRowCount": 1,
        "frozenColumnCount": 0
      },
      "hidden": false,
      "tabColorStyle": { "rgbColor": { "red": 1.0, "green": 0, "blue": 0 } }
    }
  ]
}
```

**Key Fields:**

| Field | Description |
|-------|-------------|
| `spreadsheetId` | Unique identifier for the spreadsheet |
| `spreadsheetUrl` | URL to open the spreadsheet in browser |
| `properties.title` | Spreadsheet title |
| `properties.locale` | Locale for formatting (e.g., `en_US`) |
| `properties.timeZone` | Time zone for date calculations |
| `properties.defaultFormat` | Default cell format applied to all cells |
| `sheets[].sheetId` | Unique numeric ID for each sheet (used in API calls) |
| `sheets[].title` | Display title of the sheet |
| `sheets[].folder` | Sanitized folder name on disk |
| `sheets[].sheetType` | `GRID`, `OBJECT`, or `DATA_SOURCE` |
| `sheets[].gridProperties` | Row/column counts and frozen dimensions |

### named_ranges.json

Contains all named ranges defined in the spreadsheet.

```json
{
  "namedRanges": [
    {
      "namedRangeId": "abc123",
      "name": "SalesData",
      "range": {
        "sheetId": 0,
        "startRowIndex": 0,
        "endRowIndex": 100,
        "startColumnIndex": 0,
        "endColumnIndex": 5
      }
    }
  ]
}
```

**Note:** Range indices are zero-based and half-open (`[start, end)`).

### developer_metadata.json

Contains spreadsheet-level developer metadata.

```json
{
  "developerMetadata": [
    {
      "metadataId": 12345,
      "metadataKey": "app-version",
      "metadataValue": "1.0.0",
      "location": {
        "locationType": "SPREADSHEET"
      },
      "visibility": "DOCUMENT"
    }
  ]
}
```

### data_sources.json

Contains external data source connections (BigQuery, Looker).

```json
{
  "dataSources": [
    {
      "dataSourceId": "datasource_abc",
      "spec": {
        "bigQuery": {
          "projectId": "my-project",
          "querySpec": {
            "rawQuery": "SELECT * FROM dataset.table"
          }
        }
      }
    }
  ],
  "refreshSchedules": [
    {
      "enabled": true,
      "refreshScope": "ALL_DATA_SOURCES",
      "dailySchedule": {
        "startTime": { "hours": 6, "minutes": 0 }
      }
    }
  ]
}
```

---

## Sheet-Level Files

### data.tsv

Tab-separated values containing cell data. Formulas display their computed result, not the formula text.

**Format:**
- First row: Column headers (A, B, C, ..., AA, AB, ...)
- Subsequent rows: Cell values
- Trailing empty columns and rows are trimmed

**Escaping:**
- Tab characters: `\t`
- Newline characters: `\n`
- Carriage return: `\r`
- Backslash: `\\`

**Example:**
```
A	B	C	D
Name	Sales	Region	Total
Alice	1000	North	1500
Bob	500	South	1200
```

**Value Representation:**

| Type | Representation |
|------|----------------|
| String | Raw text |
| Number | Formatted per cell's NumberFormat |
| Boolean | `TRUE` or `FALSE` |
| Date/Time | Formatted per cell's NumberFormat |
| Error | Error string (e.g., `#REF!`, `#N/A`, `#DIV/0!`) |
| Empty | Empty string |

**Source:** Values are extracted in priority order:
1. `CellData.formattedValue` (human-readable, respects NumberFormat)
2. `CellData.effectiveValue` (raw value converted to string)

### formula.json

Formulas are stored with range-based compression. When 4+ cells have the same formula pattern (with relative references adjusted per cell), they are compressed into a single entry showing the formula from the first cell and the range.

```json
{
  "formulaRanges": [
    {
      "formula": "=I4&\" - \"&J4",
      "range": "K4:K12"
    },
    {
      "formula": "=A2+B2",
      "range": "C2:C10"
    }
  ],
  "formulas": {
    "A1": "=NOW()",
    "Z1": "=UNIQUE(Sheet2!A:A)",
    "B2": "=A2+B2",
    "B3": "=A3+B3"
  },
  "arrayFormulas": {
    "A10": {
      "formula": "=ARRAYFORMULA(A2:A9*B2:B9)",
      "range": {
        "startRowIndex": 9,
        "endRowIndex": 18,
        "startColumnIndex": 0,
        "endColumnIndex": 1
      }
    }
  },
  "dataSourceFormulas": [
    {
      "cell": "F1",
      "formula": "datasource_abc",
      "dataExecutionStatus": {
        "state": "SUCCEEDED",
        "lastRefreshTime": "2024-01-15T10:30:00Z"
      }
    }
  ]
}
```

**Sections:**

| Section | Description |
|---------|-------------|
| `formulaRanges` | Compressed formula ranges (4+ cells with same pattern) |
| `formulas` | Individual formulas (unique patterns or fewer than 4 cells) |
| `arrayFormulas` | Array formulas with their output range |
| `dataSourceFormulas` | Formulas connected to external data sources |

**Formula Range Compression:**

When 4 or more contiguous cells share the same relative reference pattern, they are compressed into a `formulaRanges` entry:

- **formula**: The actual formula as entered in the first cell of the range
- **range**: The A1-notation range (e.g., `C2:C10`)

This format is intuitive for anyone familiar with spreadsheets: the formula auto-fills across the range using standard Excel/Google Sheets behavior (relative references increment, absolute references stay fixed).

**Example:**
```json
{"formula": "=A2+B2", "range": "C2:C5"}
```
This means:
- C2: `=A2+B2`
- C3: `=A3+B3` (row references increment)
- C4: `=A4+B4`
- C5: `=A5+B5`

**Compression Threshold:**

Only contiguous ranges with **4 or more cells** are compressed. Smaller groups are stored as individual formulas in the `formulas` section since listing them explicitly is clearer.

**Note:** The computed values appear in `data.tsv`. To reconstruct the original formula for a cell, apply standard spreadsheet auto-fill logic from the first cell's formula.

### format.json

Cell formatting is stored with range-based compression. Cells with identical formatting are grouped into rectangular ranges.

```json
{
  "formatRules": [
    {
      "range": "A1:J1",
      "format": {
        "horizontalAlignment": "CENTER",
        "textFormat": { "bold": true }
      }
    },
    {
      "range": "F2:F50",
      "format": {
        "numberFormat": { "type": "NUMBER", "pattern": "$#,##0" }
      }
    },
    {
      "range": "A2:A23",
      "format": {
        "backgroundColor": { "red": 1, "green": 0.85, "blue": 0.85 },
        "backgroundColorStyle": {
          "rgbColor": { "red": 1, "green": 0.85, "blue": 0.85 }
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
          "values": [{ "userEnteredValue": "1000" }]
        },
        "format": {
          "backgroundColor": { "red": 0.8, "green": 1.0, "blue": 0.8 }
        }
      }
    }
  ],
  "merges": [
    {
      "range": "A1:D1",
      "startRow": 0,
      "endRow": 1,
      "startColumn": 0,
      "endColumn": 4
    }
  ],
  "textFormatRuns": {
    "E22": [
      { "format": {} },
      {
        "startIndex": 23,
        "format": {
          "foregroundColor": { "red": 0.07, "green": 0.33, "blue": 0.8 },
          "underline": true,
          "link": { "uri": "https://example.com" }
        }
      }
    ]
  },
  "notes": {
    "A1": "This is a cell note"
  }
}
```

**Format Compression:**

The `formatRules` array contains range-based formatting rules:

1. **Range-based rules**: Cells with identical formatting are grouped into the largest possible rectangular ranges
2. **Cascade model**: Rules are applied in order; later rules override earlier ones for overlapping cells
3. **Delta encoding**: When a dominant format exists, rules for other cells only contain properties that differ
4. **Format optimization**: Deprecated fields are removed (e.g., `backgroundColor` when `backgroundColorStyle` exists)

**Format Rule Fields:**

| Field | Description |
|-------|-------------|
| `range` | A1 notation for the range this rule applies to |
| `format` | CellFormat object with formatting properties |

**Conditional Format Fields:**

| Field | Description |
|-------|-------------|
| `ruleIndex` | Zero-based index for updating/deleting rules |
| `ranges` | Array of A1-notation ranges the rule applies to |
| `booleanRule` | Condition + format for boolean rules |
| `gradientRule` | Min/mid/max colors for gradient rules |

### feature.json

Advanced spreadsheet features including charts, pivot tables, filters, and data validation.

```json
{
  "charts": [
    {
      "chartId": 123456,
      "position": {
        "overlayPosition": {
          "anchorCell": { "sheetId": 0, "rowIndex": 0, "columnIndex": 5 },
          "widthPixels": 400,
          "heightPixels": 300
        }
      },
      "spec": {
        "title": "Sales by Region",
        "basicChart": {
          "chartType": "BAR",
          "axis": [...],
          "domains": [...],
          "series": [...]
        }
      }
    }
  ],
  "pivotTables": [
    {
      "anchorCell": "G1",
      "source": { "sheetId": 0, "startRowIndex": 0, "endRowIndex": 100, ... },
      "rows": [...],
      "columns": [...],
      "values": [...]
    }
  ],
  "tables": [
    {
      "tableId": "1778223018",
      "name": "Table1",
      "range": { "startRowIndex": 0, "endRowIndex": 47, ... },
      "columnProperties": [
        { "columnName": "Category" },
        { "columnIndex": 1, "columnName": "Resource Type" }
      ]
    }
  ],
  "basicFilter": {
    "range": { "sheetId": 0, "startRowIndex": 0, ... },
    "sortSpecs": [...],
    "filterSpecs": [...]
  },
  "filterViews": [
    {
      "filterViewId": 789,
      "title": "Top Performers",
      "range": { ... },
      "filterSpecs": [...]
    }
  ],
  "slicers": [
    {
      "slicerId": 456,
      "position": { ... },
      "spec": {
        "dataRange": { ... },
        "title": "Region Filter"
      }
    }
  ],
  "bandedRanges": [
    {
      "bandedRangeId": 1778223018,
      "range": { ... },
      "rowProperties": {
        "headerColor": { ... },
        "firstBandColor": { ... },
        "secondBandColor": { ... }
      }
    }
  ],
  "dataSourceTables": [
    {
      "anchorCell": "M1",
      "dataSourceId": "datasource_abc",
      "columns": [...]
    }
  ],
  "dataValidation": [
    {
      "range": "H2... (49 cells)",
      "cells": ["H2", "H3", "H4", ...],
      "rule": {
        "condition": {
          "type": "ONE_OF_LIST",
          "values": [
            { "userEnteredValue": "Keep" },
            { "userEnteredValue": "Delete" }
          ]
        },
        "showCustomUi": true
      }
    }
  ]
}
```

**Feature Sections:**

| Section | Source | Description |
|---------|--------|-------------|
| `charts` | `Sheet.charts[]` | Embedded charts with ID, position, and spec |
| `pivotTables` | `CellData.pivotTable` | Pivot tables with anchor cell |
| `tables` | `Sheet.tables[]` | Structured tables with column definitions |
| `basicFilter` | `Sheet.basicFilter` | Active filter on the sheet |
| `filterViews` | `Sheet.filterViews[]` | Saved filter views |
| `slicers` | `Sheet.slicers[]` | Interactive filter slicers |
| `bandedRanges` | `Sheet.bandedRanges[]` | Alternating row/column colors |
| `dataSourceTables` | `CellData.dataSourceTable` | Tables from external data |
| `dataValidation` | `CellData.dataValidation` | Input validation rules grouped by rule |

**Data Validation Grouping:**

Cells with identical validation rules are grouped together. The `cells` array lists all cells with that rule, and `range` provides a summary.

### dimension.json

Row and column metadata including sizes, visibility, and groups.

```json
{
  "rowMetadata": [
    { "index": 0, "pixelSize": 21 },
    { "index": 10, "pixelSize": 50 },
    { "index": 15, "pixelSize": 21, "hidden": true }
  ],
  "columnMetadata": [
    { "index": 0, "pixelSize": 100 },
    { "index": 1, "pixelSize": 80 },
    { "index": 5, "pixelSize": 150 }
  ],
  "rowGroups": [
    {
      "range": { "dimension": "ROWS", "startIndex": 5, "endIndex": 10 },
      "depth": 1,
      "collapsed": false
    }
  ],
  "columnGroups": [
    {
      "range": { "dimension": "COLUMNS", "startIndex": 2, "endIndex": 5 },
      "depth": 1,
      "collapsed": true
    }
  ],
  "developerMetadata": [
    {
      "metadataId": 67890,
      "metadataKey": "row-category",
      "location": {
        "dimensionRange": { "dimension": "ROWS", "startIndex": 0, "endIndex": 1 }
      }
    }
  ]
}
```

**Sparse Representation:**

Only non-default dimensions are included:
- Default row height: 21 pixels
- Default column width: 100 pixels

A dimension is considered non-default if:
- `pixelSize` differs from default by more than 1 pixel
- `hidden` is true
- `developerMetadata` is present

### protection.json

Protected ranges and their permissions.

```json
{
  "protectedRanges": [
    {
      "protectedRangeId": 12345,
      "range": { "sheetId": 0, "startRowIndex": 0, "endRowIndex": 1, ... },
      "description": "Header row - do not modify",
      "warningOnly": false,
      "requestingUserCanEdit": true,
      "editors": {
        "users": ["admin@example.com"],
        "groups": ["admins@example.com"],
        "domainUsersCanEdit": false
      }
    }
  ]
}
```

---

## Coordinate Systems

### A1 Notation

Used for human-readable cell references in formulas and format files.

| Example | Description |
|---------|-------------|
| `A1` | Single cell (column A, row 1) |
| `A1:D4` | Range from A1 to D4 |
| `A:A` | Entire column A |
| `1:1` | Entire row 1 |
| `Sheet2!A1:D4` | Range on another sheet |

### Zero-Based Indices

Used in GridRange objects for API calls.

```json
{
  "sheetId": 0,
  "startRowIndex": 0,
  "endRowIndex": 10,
  "startColumnIndex": 0,
  "endColumnIndex": 5
}
```

- Indices are zero-based
- Ranges are half-open: `[start, end)`
- Missing index means unbounded

### Column Letter Conversion

```
0 -> A, 1 -> B, ..., 25 -> Z
26 -> AA, 27 -> AB, ..., 51 -> AZ
52 -> BA, ..., 701 -> ZZ
702 -> AAA, ...
```

---

## Special Sheet Types

### OBJECT Sheets

Sheets containing only embedded objects (charts, images) without grid data:
- No `data.tsv` file
- No `formula.json` file
- `feature.json` contains the embedded object

### DATA_SOURCE Sheets

Sheets connected to external data sources:
- `data.tsv` contains preview data (read-only)
- `feature.json` contains data source configuration

---

## Encoding

- **Character encoding:** UTF-8
- **Line endings:** LF (`\n`) only
- **JSON formatting:** Pretty-printed with 2-space indentation
- **No BOM:** Byte Order Mark is not included

---

## Gaps and Limitations

### Not Currently Extracted

1. **Chip runs** - Smart chips (people, dates, etc.) are not extracted
2. **Comments** - Google Sheets comments (distinct from cell notes) are not extracted
3. **Version history** - Not accessible via Sheets API
4. **Images** - Embedded images are not extracted

### Compression Limitations

1. **Borders not compressed** - Border formatting is stored per-cell, not as range rules
2. **Complex formulas** - Formulas with non-standard patterns may not compress well

### Data Validation Representation

1. **Non-contiguous ranges** - Cells are listed individually, not as ranges
2. **Rule deduplication** - Uses JSON serialization for comparison, which may miss equivalent rules with different key ordering

### Large Spreadsheet Handling

Splitting large sheets into multiple `data_*.tsv` files is **not currently implemented**. All data goes into a single `data.tsv` regardless of size.

---

## API Type Definitions

For complete TypedDict definitions of all Google Sheets API types, see `src/extrasheet/api_types.py`. This file is auto-generated from the Google Sheets API discovery document using `scripts/generate_types.py`.
