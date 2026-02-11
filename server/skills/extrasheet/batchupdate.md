# batchUpdate Reference

Direct API operations for tasks that can't be done declaratively (by editing files).

## When to Use batchUpdate

Most operations work declaratively (edit files → push). Use `batchUpdate` only for:

| Operation | Why batchUpdate? |
|-----------|------------------|
| Sort data | Order matters, can't be expressed in files |
| Move rows/columns | Position changes require API coordination |
| Insert at specific position | Need precise control over insertion point |
| Complex multi-step changes | Multiple structural changes in sequence |

## Usage

```bash
extrasheet batchUpdate <spreadsheet_url_or_id> requests.json
extrasheet pull <url>  # Always re-pull after batchUpdate
```

**Always re-pull after batchUpdate** — the local state is now stale.

---

## Request Format

```json
{
  "requests": [
    {"requestType": {...}},
    {"anotherRequest": {...}}
  ]
}
```

Requests execute in order. Later requests can depend on earlier ones.

---

## Common Operations

### Sort Data

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

**Sort options:**
- `sortOrder`: `ASCENDING` or `DESCENDING`
- `dimensionIndex`: 0-based column index within the range
- Multiple `sortSpecs` for multi-column sort

### Move Rows/Columns

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

Moves rows 11-15 (0-based: 10-14) to position 2 (before row 3).

### Insert at Specific Position

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

Inserts 3 blank rows starting at row 6 (0-based index 5).

### Delete Rows/Columns

```json
{
  "requests": [{
    "deleteDimension": {
      "range": {"sheetId": 0, "dimension": "ROWS", "startIndex": 10, "endIndex": 15}
    }
  }]
}
```

### Update Cell Values

```json
{
  "requests": [{
    "updateCells": {
      "rows": [{"values": [{"userEnteredValue": {"stringValue": "New Value"}}]}],
      "fields": "userEnteredValue",
      "start": {"sheetId": 0, "rowIndex": 4, "columnIndex": 2}
    }
  }]
}
```

**Value types:**
```json
{"stringValue": "Hello"}
{"numberValue": 42.5}
{"boolValue": true}
{"formulaValue": "=SUM(A1:A10)"}
```

### Apply Formatting

```json
{
  "requests": [{
    "repeatCell": {
      "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 10},
      "cell": {
        "userEnteredFormat": {
          "textFormat": {"bold": true},
          "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}
        }
      },
      "fields": "userEnteredFormat(textFormat,backgroundColor)"
    }
  }]
}
```

### Add Chart

```json
{
  "requests": [{
    "addChart": {
      "chart": {
        "spec": {
          "title": "My Chart",
          "basicChart": {
            "chartType": "COLUMN",
            "domains": [{"domain": {"sourceRange": {"sources": [{"sheetId": 0, "startRowIndex": 1, "endRowIndex": 10, "startColumnIndex": 0, "endColumnIndex": 1}]}}}],
            "series": [{"series": {"sourceRange": {"sources": [{"sheetId": 0, "startRowIndex": 1, "endRowIndex": 10, "startColumnIndex": 1, "endColumnIndex": 2}]}}}]
          }
        },
        "position": {"overlayPosition": {"anchorCell": {"sheetId": 0, "rowIndex": 0, "columnIndex": 5}, "widthPixels": 600, "heightPixels": 400}}
      }
    }
  }]
}
```

### Add Conditional Format

```json
{
  "requests": [{
    "addConditionalFormatRule": {
      "rule": {
        "ranges": [{"sheetId": 0, "startRowIndex": 1, "endRowIndex": 100, "startColumnIndex": 2, "endColumnIndex": 3}],
        "booleanRule": {
          "condition": {"type": "NUMBER_GREATER", "values": [{"userEnteredValue": "1000"}]},
          "format": {"backgroundColor": {"red": 0.8, "green": 1.0, "blue": 0.8}}
        }
      },
      "index": 0
    }
  }]
}
```

### Set Data Validation

```json
{
  "requests": [{
    "setDataValidation": {
      "range": {"sheetId": 0, "startRowIndex": 1, "endRowIndex": 100, "startColumnIndex": 3, "endColumnIndex": 4},
      "rule": {
        "condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": "A"}, {"userEnteredValue": "B"}]},
        "showCustomUi": true
      }
    }
  }]
}
```

### Merge Cells

```json
{
  "requests": [{
    "mergeCells": {
      "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 4},
      "mergeType": "MERGE_ALL"
    }
  }]
}
```

### Add/Delete Sheet

```json
{"addSheet": {"properties": {"title": "New Sheet"}}}
{"deleteSheet": {"sheetId": 123456}}
```

---

## All Request Types

**Cells:** `updateCells`, `repeatCell`, `appendCells`

**Dimensions:** `insertDimension`, `deleteDimension`, `moveDimension`, `appendDimension`, `updateDimensionProperties`, `autoResizeDimensions`

**Ranges:** `insertRange`, `deleteRange`, `copyPaste`, `cutPaste`, `sortRange`, `findReplace`, `trimWhitespace`, `deleteDuplicates`

**Formatting:** `updateBorders`, `mergeCells`, `unmergeCells`, `addConditionalFormatRule`, `updateConditionalFormatRule`, `deleteConditionalFormatRule`, `addBanding`, `updateBanding`, `deleteBanding`

**Features:** `addChart`, `updateChartSpec`, `deleteEmbeddedObject`, `updateEmbeddedObjectPosition`, `addFilterView`, `updateFilterView`, `deleteFilterView`, `setBasicFilter`, `clearBasicFilter`, `addSlicer`, `updateSlicerSpec`, `setDataValidation`, `addTable`, `updateTable`, `deleteTable`

**Named Ranges:** `addNamedRange`, `updateNamedRange`, `deleteNamedRange`

**Protection:** `addProtectedRange`, `updateProtectedRange`, `deleteProtectedRange`

**Sheets:** `addSheet`, `deleteSheet`, `duplicateSheet`, `updateSheetProperties`

**Groups:** `addDimensionGroup`, `updateDimensionGroup`, `deleteDimensionGroup`

**Metadata:** `createDeveloperMetadata`, `updateDeveloperMetadata`, `deleteDeveloperMetadata`

---

## GridRange Format

```json
{
  "sheetId": 0,
  "startRowIndex": 0,      // 0-based, inclusive
  "endRowIndex": 10,       // 0-based, exclusive
  "startColumnIndex": 0,
  "endColumnIndex": 5
}
```

**A1 to GridRange conversion:**
- `A1:E10` = `{startRowIndex: 0, endRowIndex: 10, startColumnIndex: 0, endColumnIndex: 5}`
- Row 5 = `startRowIndex: 4` (0-based)
- "10 rows" = `endRowIndex - startRowIndex = 10`

---

## Workflow for Complex Changes

When combining structural and content changes:

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

---

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| `INVALID_ARGUMENT` | Malformed request | Check field names/types |
| `NOT_FOUND` | Invalid ID | Verify sheetId/chartId from pulled files |
| `OUT_OF_RANGE` | Bad coordinates | Check gridProperties for bounds |
| `PERMISSION_DENIED` | Protected range | Check protection.json |
