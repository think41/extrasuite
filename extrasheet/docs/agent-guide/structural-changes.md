# Structural Changes Guide

## Declarative vs Imperative

Most structural changes can be done declaratively (edit files, then push). Use imperative (batchUpdate) only when needed.

| Operation | Method | How |
|-----------|--------|-----|
| Insert rows/columns | Declarative | Edit data.tsv |
| Delete rows/columns | Declarative | Edit data.tsv |
| Create sheet | Declarative | Add folder + spreadsheet.json entry |
| Delete sheet | Declarative | Remove folder |
| Move rows/columns | Imperative | batchUpdate |
| Sort data | Imperative | batchUpdate |

## Insert Rows/Columns (Declarative)

Edit `data.tsv` directly - add new rows or columns where needed.

**With formulas:** Update `formula.json` to reflect POST-insert positions.
- If inserting at row 5, a formula at D14 should be at D15 in formula.json

## Delete Rows/Columns (Declarative)

Remove rows/columns from `data.tsv`.

**With formulas:** Update `formula.json` to reflect POST-delete positions.
- If deleting row 8, a formula at D14 should be at D13 in formula.json

**Validation:**
- BLOCKED if formula edits conflict with structural changes
- WARNING if delete breaks existing formula references (use `--force`)

## Create New Sheet (Declarative)

1. Create folder: `<spreadsheet_id>/NewSheet/`
2. Add `data.tsv` with cell values
3. Optionally add `formula.json`, `format.json`, etc.
4. Add entry to `spreadsheet.json` → `sheets[]`:
```json
{
  "title": "NewSheet",
  "folder": "NewSheet",
  "sheetType": "GRID",
  "gridProperties": {"rowCount": 100, "columnCount": 26}
}
```
5. Run `extrasheet push`
6. **Re-pull to get server-assigned sheetId**

## Delete Sheet (Declarative)

Remove the sheet's folder, then push.

**Warning:** May break cross-sheet references. Check formulas for `'SheetName'!` references.

## Move Rows/Columns (Imperative)

Create `move.json`:
```json
{
  "requests": [{
    "moveDimension": {
      "source": {"sheetId": 0, "dimension": "ROWS", "startIndex": 10, "endIndex": 15},
      "destinationIndex": 2
    }
  }]
}
```

```bash
extrasheet batchUpdate <url> move.json
extrasheet pull <url>  # Always re-pull after batchUpdate
```

## Sort Data (Imperative)

Create `sort.json`:
```json
{
  "requests": [{
    "sortRange": {
      "range": {"sheetId": 0, "startRowIndex": 1, "endRowIndex": 100, "startColumnIndex": 0, "endColumnIndex": 5},
      "sortSpecs": [{"dimensionIndex": 2, "sortOrder": "DESCENDING"}]
    }
  }]
}
```

```bash
extrasheet batchUpdate <url> sort.json
extrasheet pull <url>
```

## Insert at Specific Position (Imperative)

If you need precise control over insertion:

```json
{
  "requests": [{
    "insertDimension": {
      "range": {"sheetId": 0, "dimension": "ROWS", "startIndex": 5, "endIndex": 8},
      "inheritFromBefore": true
    }
  }]
}
```

## Index Numbering

| Context | Convention |
|---------|------------|
| data.tsv lines | 1-based (line 5 = row 5) |
| A1 notation | 1-based |
| GridRange JSON | 0-based (`startRowIndex: 0` = row 1) |
| GridRange end | Exclusive (`endRowIndex: 10` = rows 0-9) |

**Example:** Rows 1-10 in GridRange:
```json
{"startRowIndex": 0, "endRowIndex": 10}
```

## Workflow for Complex Changes

```bash
# 1. Structural change via batchUpdate
extrasheet batchUpdate <url> structural.json

# 2. Re-pull to get updated state
extrasheet pull <url>

# 3. Make content changes declaratively
# ... edit files ...

# 4. Push content changes
extrasheet push <folder>
```
