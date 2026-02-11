---
name: extrasheet
description: Read, write, and manipulate Google Sheets. Use when user asks to work with Google Sheets, spreadsheets, or shares a docs.google.com/spreadsheets URL.
---

# ExtraSheet Agent Guide

Edit Google Sheets via local files using the pull-edit-diff-push workflow.

## Workflow

```bash
uvx extrasuite sheet pull <url> [output_dir]              # Download spreadsheet to <output_dir>/<spreadsheet_id>/
# ... edit files in <output_dir>/<spreadsheet_id>/
uvx extrasuite sheet diff <output_dir>/<spreadsheet_id>   # Preview changes (dry run)
uvx extrasuite sheet push <output_dir>/<spreadsheet_id>   # Apply changes to Google Sheets
```

**After push, always re-pull before making more changes** — the pristine state is not auto-updated.

## Directory Structure

```
<spreadsheet_id>/
  spreadsheet.json          # START HERE - metadata + data previews from all worksheets
  theme.json                # Default formatting and theme colors (auto-generated, rarely edited)
  named_ranges.json         # Named ranges (optional, spreadsheet-level)
  <sheet_name>/             # One folder per sheet, named after the sheet title
    data.tsv                # Raw, unformatted cell values, truncated to 100 rows. Formula cells show last computed value.
    formula.json            # Formulas. A column or row with a consistent formula pattern is represented as a single entry
    format.json             # How the spreadsheet is styled - number/currency formats, colours, fonts, conditional formats, merges, etc.
    dimension.json          # Column widths and row heights
    ...                     # Optional files for charts, data validation, filters, pivot tables, banded ranges, slicers, etc. See features.md for details.
  .raw/                     # Raw API responses (internal use only)
  .pristine/                # Original state for diff comparison (internal use only)
```

## Reading Strategy

1. **Start with `spreadsheet.json`** — contains sheet list and data previews (first 5 + last 3 rows per sheet)
2. **Read specific sheet files only when needed** — don't read all data.tsv files upfront
3. **Skip `.pristine/` and `.raw/`** — internal use only

---

## spreadsheet.json

Central metadata file. Contains:
- Spreadsheet title and properties
- List of sheets with preview and folder name for each sheet
- Data preview for each sheet (first 5 + last 3 rows, split into `firstRows` and `lastRows`)

```json
{
  "spreadsheetId": "abc123...",
  "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/abc123.../edit",
  "properties": {
    "title": "My Spreadsheet",
    "locale": "en_US",
    "timeZone": "America/New_York"
  },
  "sheets": [
    {
      "sheetId": 0,
      "title": "Sheet1",
      "folder": "Sheet1",
      "sheetType": "GRID",
      "gridProperties": {"rowCount": 100, "columnCount": 26, "frozenRowCount": 1},
      "preview": {
        "firstRows": [
          ["Name", "Value", "Date"],
          ["Alice", "100", "2024-01-15"],
          ...
        ],
        "lastRows": [
          ["Zara", "200", "2024-12-01"]
        ]
      }
    }
  ]
}
```

**Editable properties:**
- `properties.title` — spreadsheet title
- `sheets[].title` — sheet title
- `sheets[].hidden` — hide a sheet
- `sheets[].gridProperties.frozenRowCount` — frozen header rows
- `sheets[].gridProperties.frozenColumnCount` — frozen columns
- `sheets[].tabColor` — hex color for the sheet tab (e.g., `"#FF0000"`), remove to clear
- `sheets[].rightToLeft` — `true` for right-to-left layout (Arabic, Hebrew, etc.)

**Large sheets:** When a sheet has more than 100 rows, data.tsv is truncated. A `truncation` field appears:
```json
"truncation": {"totalRows": 5000, "fetchedRows": 100, "truncated": true}
```

---

## data.tsv

Tab-separated cell values. Each sheet folder has one.

> **No headers:** Line 1 = Row 1 in Google Sheets, first value in data.tsv corresponds to A1 in google sheets.

> **Raw values only:** data.tsv contains raw values, not formatted display strings. Write `8000` not `$8,000`. Write `0.72` not `72%`. The display format is controlled by `format.json` (e.g., `numberFormat.type: "CURRENCY"`). Formulas are defined separately in `formula.json`.

> **Formula errors:** After push, if a formula has an error (e.g., referencing text instead of numbers), the error message appears in data.tsv when you re-pull. For example: `Evaluation of function AVERAGE caused a divide by zero error.`

**Editing:**
- Edit the file in place to change cell values, add or delete rows/columns
- Formula cells should be left blank — the formula goes in `formula.json`.

---

## formula.json

Formulas as a **flat dictionary** mapping cell addresses to formulas.

```json
{
  "C2": "=A2+B2",
  "D2:D100": "=B2*C2",
  "E1": "=SUM(B:B)"
}
```

**Range compression:** `"D2:D100": "=B2*C2"` means:
- D2: `=B2*C2`
- D3: `=B3*C3`
- D4: `=B4*C4`
- ...and so on (relative references auto-increment)

**Absolute references:** Use `$` to fix references: `"D2:D100": "=C2*$B$1"` keeps B1 fixed.

**Deleting formulas:** Remove the key. The cell keeps its last computed value in data.tsv unless you also edit data.tsv to change it.

**Cross-sheet references:** `"A1": "='Other Sheet'!B5"`

---

## Basic Formatting

For simple formatting, edit `format.json`:

```json
{
  "formatRules": [
    {
      "range": "A1:J1",
      "format": {
        "backgroundColor": "#CCCCCC",
        "textFormat": {"bold": true, "fontSize": 12},
        "horizontalAlignment": "CENTER"
      }
    }
  ]
}
```

**Common properties:**
- `backgroundColor` — hex color (`"#FF0000"`)
- `textFormat.bold`, `textFormat.italic`, `textFormat.strikethrough`, `textFormat.underline` — boolean
- `textFormat.fontSize` — integer (points)
- `textFormat.foregroundColor` — hex color for text
- `horizontalAlignment` — `LEFT`, `CENTER`, `RIGHT`
- `verticalAlignment` — `TOP`, `MIDDLE`, `BOTTOM`
- `numberFormat.type` — `NUMBER`, `CURRENCY`, `DATE`, `PERCENT`
- `numberFormat.pattern` — format string (e.g., `"$#,##0.00"`, `"MMM d, yyyy"`)
- `wrapStrategy` — `OVERFLOW_CELL` (default), `WRAP`, `CLIP`
- `padding` — `{"top": 5, "bottom": 5, "left": 10, "right": 10}` (pixels)
- `textDirection` — `LEFT_TO_RIGHT`, `RIGHT_TO_LEFT`
- `textRotation` — `{"angle": 45}` (-90 to 90) or `{"vertical": true}`
- `borders` — see [formatting.md](formatting.md) for border syntax

For advanced formatting (conditional formats, merges, rich text), see [formatting.md](formatting.md).

> **Note:** `formatRules` uses `range` (singular string), but `conditionalFormats` uses `ranges` (plural array) because a single rule can apply to multiple disjoint ranges.

---

## Creating a New Sheet

All of these can be done in a single push:

1. Create folder: `<spreadsheet_id>/<NewSheet>/`
2. Add `data.tsv` with content
3. Optionally add `formula.json`, `format.json`, etc.
4. Add entry to `spreadsheet.json` → `sheets[]`:
   ```json
   {"title": "New Sheet Title", "folder": "<NewSheet>", "sheetType": "GRID"}
   ```
5. Run `uvx extrasuite sheet push <folder>`

The diff engine automatically generates `addSheet` before any content updates, so everything works in one push. No need to create the sheet first and re-pull.

## Deleting a Sheet

1. Remove the sheet's entry from `spreadsheet.json` → `sheets[]`
2. Remove the sheet's folder from disk
3. Run `uvx extrasuite sheet push <folder>`

Both steps (1 and 2) are required. The diff detects deletion by comparing the sheet list in `spreadsheet.json` against the pristine copy.

**Warning:** Check for cross-sheet references (`'SheetName'!`) in formulas first.

---

## Key Gotchas

| Issue | Solution |
|-------|----------|
| Changes not applied after push | Re-pull before making more changes |
| "Sheet already exists" error | Re-pull — pristine state is stale |
| Formula errors in data.tsv | data.tsv has formatted text (`$8,000`) instead of raw numbers (`8000`) |
| Conditional format not working | Use `ranges` (array) not `range` (string) for `conditionalFormats` |

---

## File Reference

| File | Format | When to Edit |
|------|--------|--------------|
| `spreadsheet.json` | JSON | Change titles, frozen rows/cols, add/delete sheets |
| `data.tsv` | TSV | Change cell values, insert/delete rows/cols |
| `formula.json` | Flat dict | Add/modify formulas |
| `format.json` | JSON | Colors, fonts, number formats, conditional formats, merges, notes, rich text |
| `dimension.json` | JSON | Row heights, column widths |
| `charts.json` | JSON | Add/modify charts |
| `data-validation.json` | JSON | Dropdowns, checkboxes |
| `filters.json` | JSON | Basic filters, filter views |
| `banded-ranges.json` | JSON | Alternating row/column colors |
| `pivot-tables.json` | JSON | Pivot tables |
| `tables.json` | JSON | Structured tables |
| `slicers.json` | JSON | Slicers for filtering (rare) |
| `named_ranges.json` | JSON | Named ranges (spreadsheet-level, not per-sheet) |

---

## Specialized Guides

- **[formatting.md](formatting.md)** — Conditional formats, merges, notes, rich text, banded ranges, dimension sizing
- **[features.md](features.md)** — Charts, pivot tables, data validation, filters, named ranges
- **[batchupdate.md](batchupdate.md)** — Sort, move rows/columns, direct API operations
