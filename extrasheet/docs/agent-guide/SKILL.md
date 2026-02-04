# ExtraSheet Agent Guide

Edit Google Sheets via local files using the pull-edit-diff-push workflow.

## Workflow

```bash
extrasheet pull <url>      # Download spreadsheet to local folder
# ... edit files ...
extrasheet diff <folder>   # Preview changes (dry run)
extrasheet push <folder>   # Apply changes to Google Sheets
```

**After push, always re-pull before making more changes** — the pristine state is not auto-updated.

## Directory Structure

```
<spreadsheet_id>/
  spreadsheet.json          # START HERE - metadata + data previews
  <sheet_name>/
    data.tsv                # Cell values (tab-separated)
    formula.json            # Formulas
    format.json             # Formatting (optional)
    ...                     # Other feature files
  .pristine/                # DO NOT TOUCH - used by diff
```

## Reading Strategy

1. **Start with `spreadsheet.json`** — contains sheet list and data previews (first 5 + last 3 rows per sheet)
2. **Read specific sheet files only when needed** — don't read all data.tsv files upfront
3. **Skip `.pristine/` and `.raw/`** — internal use only

---

## spreadsheet.json

Central metadata file. Contains:
- Spreadsheet title
- List of sheets with properties
- Data preview for each sheet (first 5 + last 3 rows)

```json
{
  "title": "My Spreadsheet",
  "sheets": [
    {
      "sheetId": 0,
      "title": "Sheet1",
      "folder": "Sheet1",
      "sheetType": "GRID",
      "gridProperties": {"rowCount": 100, "columnCount": 26, "frozenRowCount": 1},
      "preview": [
        ["Name", "Value", "Date"],
        ["Alice", "100", "2024-01-15"],
        ...
      ]
    }
  ]
}
```

**Editable properties:**
- `title` — spreadsheet or sheet title
- `gridProperties.frozenRowCount`, `frozenColumnCount`
- `hidden` — hide a sheet

---

## data.tsv

Tab-separated cell values. Each sheet folder has one.

```tsv
Name	Value	Date
Alice	100	2024-01-15
Bob	200	2024-01-16
```

**Editing:**
- Change cell values directly
- Add rows by adding lines
- Add columns by adding tab-separated values
- Delete rows by removing lines
- Delete columns by removing values from each line

**Special characters:** Escaped as `\t` (tab), `\n` (newline), `\\` (backslash).

**Formulas:** Show computed values here. Actual formulas are in `formula.json`.

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

**Common patterns:**
```json
{
  "B10": "=SUM(B2:B9)",
  "C10": "=AVERAGE(C2:C9)",
  "D2:D100": "=IFERROR(B2/C2, 0)",
  "E2:E100": "=IF(D2>0.5, \"High\", \"Low\")",
  "F2:F100": "=VLOOKUP(A2, 'Lookup'!A:B, 2, FALSE)"
}
```

**Deleting formulas:** Remove the key. The cell keeps its last computed value in data.tsv.

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
- `textFormat.bold`, `textFormat.italic` — boolean
- `textFormat.fontSize` — integer (points)
- `horizontalAlignment` — `LEFT`, `CENTER`, `RIGHT`
- `numberFormat.type` — `NUMBER`, `CURRENCY`, `DATE`, `PERCENT`

For advanced formatting (conditional formats, merges, rich text), see [formatting.md](formatting.md).

---

## Creating a New Sheet

1. Create folder: `<spreadsheet_id>/NewSheet/`
2. Add `data.tsv` with content
3. Add entry to `spreadsheet.json` → `sheets[]`:
   ```json
   {"title": "NewSheet", "folder": "NewSheet", "sheetType": "GRID"}
   ```
4. Run `extrasheet push`
5. **Re-pull to get server-assigned sheetId**

## Deleting a Sheet

Remove the sheet's folder from disk, then push.

**Warning:** Check for cross-sheet references (`'SheetName'!`) in formulas first.

---

## Key Gotchas

| Issue | Solution |
|-------|----------|
| Changes not applied after push | Re-pull before making more changes |
| "Sheet already exists" error | Re-pull — pristine state is stale |
| Sheet IDs changed | Google reassigns IDs — re-pull to get actual IDs |

---

## File Reference

| File | Format | When to Edit |
|------|--------|--------------|
| `spreadsheet.json` | JSON | Change titles, frozen rows/cols, add sheets |
| `data.tsv` | TSV | Change cell values, insert/delete rows/cols |
| `formula.json` | Flat dict | Add/modify formulas |
| `format.json` | JSON | Colors, fonts, number formats |
| `charts.json` | JSON | Add/modify charts |
| `data-validation.json` | JSON | Dropdowns, checkboxes |
| `dimension.json` | JSON | Row heights, column widths |

---

## Specialized Guides

- **[formatting.md](formatting.md)** — Conditional formats, merges, notes, rich text, banded ranges
- **[features.md](features.md)** — Charts, pivot tables, data validation, filters, named ranges
- **[batchupdate.md](batchupdate.md)** — Sort, move rows/columns, direct API operations
