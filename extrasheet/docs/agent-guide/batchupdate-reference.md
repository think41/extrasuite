# batchUpdate Reference

Use `extrasheet batchUpdate <url> requests.json` for imperative operations.

**Always re-pull after batchUpdate** to get updated state.

## Request Format

```json
{
  "requests": [
    {"requestType": {...}},
    {"anotherRequest": {...}}
  ]
}
```

## Common Requests

### Update Cell Values

```json
{
  "updateCells": {
    "rows": [{"values": [{"userEnteredValue": {"stringValue": "New Value"}}]}],
    "fields": "userEnteredValue",
    "start": {"sheetId": 0, "rowIndex": 4, "columnIndex": 2}
  }
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
}
```

### Insert Rows/Columns

```json
{
  "insertDimension": {
    "range": {"sheetId": 0, "dimension": "ROWS", "startIndex": 5, "endIndex": 8},
    "inheritFromBefore": true
  }
}
```

### Delete Rows/Columns

```json
{
  "deleteDimension": {
    "range": {"sheetId": 0, "dimension": "ROWS", "startIndex": 10, "endIndex": 15}
  }
}
```

### Move Rows/Columns

```json
{
  "moveDimension": {
    "source": {"sheetId": 0, "dimension": "ROWS", "startIndex": 10, "endIndex": 15},
    "destinationIndex": 2
  }
}
```

### Sort Range

```json
{
  "sortRange": {
    "range": {"sheetId": 0, "startRowIndex": 1, "endRowIndex": 100, "startColumnIndex": 0, "endColumnIndex": 5},
    "sortSpecs": [{"dimensionIndex": 2, "sortOrder": "DESCENDING"}]
  }
}
```

### Add Chart

```json
{
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
}
```

### Add Conditional Format

```json
{
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
}
```

### Set Data Validation

```json
{
  "setDataValidation": {
    "range": {"sheetId": 0, "startRowIndex": 1, "endRowIndex": 100, "startColumnIndex": 3, "endColumnIndex": 4},
    "rule": {
      "condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": "A"}, {"userEnteredValue": "B"}]},
      "showCustomUi": true
    }
  }
}
```

### Merge Cells

```json
{
  "mergeCells": {
    "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 4},
    "mergeType": "MERGE_ALL"
  }
}
```

### Add/Delete Sheet

```json
{"addSheet": {"properties": {"title": "New Sheet"}}}
{"deleteSheet": {"sheetId": 123456}}
```

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

A1 `A1:E10` = `{startRowIndex: 0, endRowIndex: 10, startColumnIndex: 0, endColumnIndex: 5}`

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| `INVALID_ARGUMENT` | Malformed request | Check field names/types |
| `NOT_FOUND` | Invalid ID | Verify sheetId/chartId from pulled files |
| `OUT_OF_RANGE` | Bad coordinates | Check gridProperties for bounds |
| `PERMISSION_DENIED` | Protected range | Check protection.json |
