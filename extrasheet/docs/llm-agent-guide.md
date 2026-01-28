# LLM Agent Guide: Modifying Google Sheets via batchUpdate

This guide explains how an LLM agent can use extrasheet output files to construct Google Sheets API `batchUpdate` requests without re-fetching the spreadsheet.

## Overview

The extrasheet format provides all information needed for "fly-blind" editing:
1. Read the on-disk files to understand current spreadsheet state
2. Construct `batchUpdate` requests based on user instructions
3. Execute requests via `POST /v4/spreadsheets/{spreadsheetId}:batchUpdate`

**Important:** After structural changes (insert/delete rows/columns, new sheets), recommend re-pulling the spreadsheet as references may have shifted.

---

## Special Directories

The pulled folder contains two special directories that should be handled carefully:

| Directory | Purpose | Action |
|-----------|---------|--------|
| `.pristine/` | Contains a zip of the original pulled state. Used internally by `diff` and `push` commands. | **Ignore completely.** Never read, modify, or delete. |
| `.raw/` | Contains raw JSON responses from the Google Sheets API (`metadata.json`, `data.json`). Useful for debugging. | **Read-only reference.** Do not modify. |

Only read and modify the main files (`spreadsheet.json`, `data.tsv`, `formula.json`, etc.) in the sheet folders.

---

## Essential IDs Reference

Every update operation requires the correct ID. Extract these from the output files:

| Object | ID Field | File Location |
|--------|----------|---------------|
| Sheet | `sheetId` | `spreadsheet.json` → `sheets[].sheetId` |
| Chart | `chartId` | `feature.json` → `charts[].chartId` |
| Named Range | `namedRangeId` | `named_ranges.json` → `namedRanges[].namedRangeId` |
| Protected Range | `protectedRangeId` | `protection.json` → `protectedRanges[].protectedRangeId` |
| Filter View | `filterViewId` | `feature.json` → `filterViews[].filterViewId` |
| Slicer | `slicerId` | `feature.json` → `slicers[].slicerId` |
| Banded Range | `bandedRangeId` | `feature.json` → `bandedRanges[].bandedRangeId` |
| Table | `tableId` | `feature.json` → `tables[].tableId` |
| Conditional Format | `ruleIndex` | `format.json` → `conditionalFormats[].ruleIndex` |
| Data Source | `dataSourceId` | `data_sources.json` → `dataSources[].dataSourceId` |

---

## Common Operations

### 1. Update Cell Values

**Files to read:** `spreadsheet.json` (for sheetId), `data.tsv` (current values)

**Request:**
```json
{
  "requests": [
    {
      "updateCells": {
        "rows": [
          {
            "values": [
              { "userEnteredValue": { "stringValue": "New Value" } }
            ]
          }
        ],
        "fields": "userEnteredValue",
        "start": {
          "sheetId": 0,
          "rowIndex": 4,
          "columnIndex": 2
        }
      }
    }
  ]
}
```

**Value Types:**
```json
// String
{ "userEnteredValue": { "stringValue": "Hello" } }

// Number
{ "userEnteredValue": { "numberValue": 42.5 } }

// Boolean
{ "userEnteredValue": { "boolValue": true } }

// Formula
{ "userEnteredValue": { "formulaValue": "=SUM(A1:A10)" } }
```

### 2. Add/Update Formulas

**Files to read:** `spreadsheet.json`, `formula.json` (existing formulas), `named_ranges.json` (for validation)

**Understanding formula.json:**

Formulas are stored as a flat dictionary where keys are cell references or ranges:

```json
{
  "B2:K2": "='Operating Model'!B37",
  "B3:K3": "=B2*operating_expense_ratio",
  "A1": "=NOW()",
  "Z1": "=UNIQUE(Sheet2!A:A)"
}
```

- **Single cell keys** (e.g., `"A1"`): The formula applies to that cell only
- **Range keys** (e.g., `"B2:K2"`): The formula auto-fills across the range using standard spreadsheet behavior (relative references increment, absolute references stay fixed)

**Example:** `"C2:C10": "=A2+B2"` means:
- C2: `=A2+B2`
- C3: `=A3+B3`
- C4: `=A4+B4`
- ... and so on to C10

**Request:**
```json
{
  "requests": [
    {
      "updateCells": {
        "rows": [
          {
            "values": [
              { "userEnteredValue": { "formulaValue": "=SUM(B2:B9)" } }
            ]
          }
        ],
        "fields": "userEnteredValue",
        "start": { "sheetId": 0, "rowIndex": 9, "columnIndex": 1 }
      }
    }
  ]
}
```

**Tip:** Check `named_ranges.json` to validate any named ranges used in formulas.

### 3. Format Cells

**Files to read:** `spreadsheet.json`, `format.json` (current formatting)

**Apply formatting to a range:**
```json
{
  "requests": [
    {
      "repeatCell": {
        "range": {
          "sheetId": 0,
          "startRowIndex": 0,
          "endRowIndex": 1,
          "startColumnIndex": 0,
          "endColumnIndex": 10
        },
        "cell": {
          "userEnteredFormat": {
            "textFormat": { "bold": true, "fontSize": 12 },
            "backgroundColor": { "red": 0.9, "green": 0.9, "blue": 0.9 }
          }
        },
        "fields": "userEnteredFormat(textFormat,backgroundColor)"
      }
    }
  ]
}
```

**Common Format Properties:**

| Property | Values |
|----------|--------|
| `horizontalAlignment` | `LEFT`, `CENTER`, `RIGHT` |
| `verticalAlignment` | `TOP`, `MIDDLE`, `BOTTOM` |
| `wrapStrategy` | `OVERFLOW_CELL`, `CLIP`, `WRAP` |
| `textFormat.bold` | `true`, `false` |
| `textFormat.italic` | `true`, `false` |
| `textFormat.fontSize` | Integer (points) |
| `numberFormat.type` | `NUMBER`, `CURRENCY`, `DATE`, `PERCENT`, etc. |
| `numberFormat.pattern` | Format string (e.g., `$#,##0.00`) |

### 4. Insert Rows/Columns

**Files to read:** `spreadsheet.json` (grid dimensions), `formula.json` (to warn about reference shifts)

**Insert rows:**
```json
{
  "requests": [
    {
      "insertDimension": {
        "range": {
          "sheetId": 0,
          "dimension": "ROWS",
          "startIndex": 5,
          "endIndex": 8
        },
        "inheritFromBefore": true
      }
    }
  ]
}
```

**Insert columns:**
```json
{
  "requests": [
    {
      "insertDimension": {
        "range": {
          "sheetId": 0,
          "dimension": "COLUMNS",
          "startIndex": 2,
          "endIndex": 4
        },
        "inheritFromBefore": false
      }
    }
  ]
}
```

**Warning:** Inserting/deleting dimensions shifts formula references. After this operation, existing formulas in `formula.json` may have outdated cell references. Recommend re-pulling the spreadsheet.

### 5. Delete Rows/Columns

**Files to read:** `spreadsheet.json`, `formula.json`, `feature.json` (charts/pivots that may be affected)

```json
{
  "requests": [
    {
      "deleteDimension": {
        "range": {
          "sheetId": 0,
          "dimension": "ROWS",
          "startIndex": 10,
          "endIndex": 15
        }
      }
    }
  ]
}
```

### 6. Add Conditional Formatting

**Files to read:** `spreadsheet.json`, `format.json` (existing rules)

```json
{
  "requests": [
    {
      "addConditionalFormatRule": {
        "rule": {
          "ranges": [
            {
              "sheetId": 0,
              "startColumnIndex": 2,
              "endColumnIndex": 3,
              "startRowIndex": 1,
              "endRowIndex": 100
            }
          ],
          "booleanRule": {
            "condition": {
              "type": "NUMBER_GREATER",
              "values": [{ "userEnteredValue": "1000" }]
            },
            "format": {
              "backgroundColor": { "red": 0.8, "green": 1.0, "blue": 0.8 }
            }
          }
        },
        "index": 0
      }
    }
  ]
}
```

**Condition Types:**

| Type | Description |
|------|-------------|
| `NUMBER_GREATER` | Value > threshold |
| `NUMBER_LESS` | Value < threshold |
| `NUMBER_BETWEEN` | Value between two numbers |
| `TEXT_CONTAINS` | Text contains substring |
| `TEXT_STARTS_WITH` | Text starts with prefix |
| `DATE_BEFORE` | Date before threshold |
| `CUSTOM_FORMULA` | Custom formula returns TRUE |

### 7. Update/Delete Conditional Format Rules

**Files to read:** `format.json` → `conditionalFormats[].ruleIndex`

**Update rule:**
```json
{
  "requests": [
    {
      "updateConditionalFormatRule": {
        "index": 0,
        "sheetId": 0,
        "rule": {
          "ranges": [...],
          "booleanRule": {...}
        }
      }
    }
  ]
}
```

**Delete rule:**
```json
{
  "requests": [
    {
      "deleteConditionalFormatRule": {
        "index": 0,
        "sheetId": 0
      }
    }
  ]
}
```

**Important:** Use the `ruleIndex` from `format.json`. After adding/deleting rules, indices shift.

### 8. Merge Cells

**Files to read:** `spreadsheet.json`, `format.json` → `merges` (existing merges)

**Merge:**
```json
{
  "requests": [
    {
      "mergeCells": {
        "range": {
          "sheetId": 0,
          "startRowIndex": 0,
          "endRowIndex": 1,
          "startColumnIndex": 0,
          "endColumnIndex": 4
        },
        "mergeType": "MERGE_ALL"
      }
    }
  ]
}
```

**Unmerge:**
```json
{
  "requests": [
    {
      "unmergeCells": {
        "range": {
          "sheetId": 0,
          "startRowIndex": 0,
          "endRowIndex": 1,
          "startColumnIndex": 0,
          "endColumnIndex": 4
        }
      }
    }
  ]
}
```

### 9. Set Data Validation

**Files to read:** `feature.json` → `dataValidation` (existing rules)

**Dropdown list:**
```json
{
  "requests": [
    {
      "setDataValidation": {
        "range": {
          "sheetId": 0,
          "startRowIndex": 1,
          "endRowIndex": 100,
          "startColumnIndex": 3,
          "endColumnIndex": 4
        },
        "rule": {
          "condition": {
            "type": "ONE_OF_LIST",
            "values": [
              { "userEnteredValue": "Option A" },
              { "userEnteredValue": "Option B" },
              { "userEnteredValue": "Option C" }
            ]
          },
          "showCustomUi": true,
          "strict": true
        }
      }
    }
  ]
}
```

**Number validation:**
```json
{
  "requests": [
    {
      "setDataValidation": {
        "range": {...},
        "rule": {
          "condition": {
            "type": "NUMBER_BETWEEN",
            "values": [
              { "userEnteredValue": "0" },
              { "userEnteredValue": "100" }
            ]
          },
          "inputMessage": "Enter a number between 0 and 100",
          "strict": true
        }
      }
    }
  ]
}
```

### 10. Add/Update Charts

**Files to read:** `spreadsheet.json`, `feature.json` → `charts` (existing charts)

**Add chart:**
```json
{
  "requests": [
    {
      "addChart": {
        "chart": {
          "spec": {
            "title": "Sales by Region",
            "basicChart": {
              "chartType": "COLUMN",
              "legendPosition": "BOTTOM_LEGEND",
              "domains": [
                {
                  "domain": {
                    "sourceRange": {
                      "sources": [{
                        "sheetId": 0,
                        "startRowIndex": 1,
                        "endRowIndex": 10,
                        "startColumnIndex": 0,
                        "endColumnIndex": 1
                      }]
                    }
                  }
                }
              ],
              "series": [
                {
                  "series": {
                    "sourceRange": {
                      "sources": [{
                        "sheetId": 0,
                        "startRowIndex": 1,
                        "endRowIndex": 10,
                        "startColumnIndex": 1,
                        "endColumnIndex": 2
                      }]
                    }
                  },
                  "targetAxis": "LEFT_AXIS"
                }
              ]
            }
          },
          "position": {
            "overlayPosition": {
              "anchorCell": { "sheetId": 0, "rowIndex": 0, "columnIndex": 5 },
              "widthPixels": 600,
              "heightPixels": 400
            }
          }
        }
      }
    }
  ]
}
```

**Update chart:**
```json
{
  "requests": [
    {
      "updateChartSpec": {
        "chartId": 123456,
        "spec": {
          "title": "Updated Title",
          "basicChart": {...}
        }
      }
    }
  ]
}
```

**Chart Types:** `BAR`, `COLUMN`, `LINE`, `PIE`, `SCATTER`, `AREA`, `COMBO`

### 11. Add/Update Named Ranges

**Files to read:** `named_ranges.json`

**Add:**
```json
{
  "requests": [
    {
      "addNamedRange": {
        "namedRange": {
          "name": "SalesData",
          "range": {
            "sheetId": 0,
            "startRowIndex": 0,
            "endRowIndex": 100,
            "startColumnIndex": 0,
            "endColumnIndex": 5
          }
        }
      }
    }
  ]
}
```

**Update:**
```json
{
  "requests": [
    {
      "updateNamedRange": {
        "namedRange": {
          "namedRangeId": "abc123",
          "name": "UpdatedName",
          "range": {...}
        },
        "fields": "name,range"
      }
    }
  ]
}
```

### 12. Add/Update Protection

**Files to read:** `protection.json`

**Add protected range:**
```json
{
  "requests": [
    {
      "addProtectedRange": {
        "protectedRange": {
          "range": {
            "sheetId": 0,
            "startRowIndex": 0,
            "endRowIndex": 1
          },
          "description": "Header row",
          "warningOnly": false,
          "editors": {
            "users": ["admin@example.com"]
          }
        }
      }
    }
  ]
}
```

### 13. Resize Rows/Columns

**Files to read:** `dimension.json`

```json
{
  "requests": [
    {
      "updateDimensionProperties": {
        "range": {
          "sheetId": 0,
          "dimension": "COLUMNS",
          "startIndex": 0,
          "endIndex": 1
        },
        "properties": {
          "pixelSize": 200
        },
        "fields": "pixelSize"
      }
    }
  ]
}
```

**Hide rows/columns:**
```json
{
  "requests": [
    {
      "updateDimensionProperties": {
        "range": {
          "sheetId": 0,
          "dimension": "ROWS",
          "startIndex": 10,
          "endIndex": 20
        },
        "properties": {
          "hiddenByUser": true
        },
        "fields": "hiddenByUser"
      }
    }
  ]
}
```

### 14. Add/Delete Sheets

**Add sheet:**
```json
{
  "requests": [
    {
      "addSheet": {
        "properties": {
          "title": "New Sheet",
          "gridProperties": {
            "rowCount": 1000,
            "columnCount": 26
          }
        }
      }
    }
  ]
}
```

**Delete sheet:**
```json
{
  "requests": [
    {
      "deleteSheet": {
        "sheetId": 123456
      }
    }
  ]
}
```

**Warning:** Deleting a sheet breaks cross-sheet references. Check formulas for `SheetName!` references first.

### 15. Sort Data

**Files to read:** `spreadsheet.json`, `data.tsv`

```json
{
  "requests": [
    {
      "sortRange": {
        "range": {
          "sheetId": 0,
          "startRowIndex": 1,
          "endRowIndex": 100,
          "startColumnIndex": 0,
          "endColumnIndex": 5
        },
        "sortSpecs": [
          {
            "dimensionIndex": 2,
            "sortOrder": "DESCENDING"
          }
        ]
      }
    }
  ]
}
```

### 16. Find and Replace

```json
{
  "requests": [
    {
      "findReplace": {
        "find": "old text",
        "replacement": "new text",
        "allSheets": true,
        "matchCase": false,
        "matchEntireCell": false
      }
    }
  ]
}
```

### 17. Set Basic Filter

**Files to read:** `feature.json` → `basicFilter`

**Set filter:**
```json
{
  "requests": [
    {
      "setBasicFilter": {
        "filter": {
          "range": {
            "sheetId": 0,
            "startRowIndex": 0,
            "endRowIndex": 100,
            "startColumnIndex": 0,
            "endColumnIndex": 5
          },
          "filterSpecs": [
            {
              "columnIndex": 2,
              "filterCriteria": {
                "condition": {
                  "type": "TEXT_CONTAINS",
                  "values": [{ "userEnteredValue": "Active" }]
                }
              }
            }
          ]
        }
      }
    }
  ]
}
```

**Clear filter:**
```json
{
  "requests": [
    {
      "clearBasicFilter": {
        "sheetId": 0
      }
    }
  ]
}
```

---

## Batch Multiple Operations

Multiple requests can be combined in a single batchUpdate call. They execute atomically - all succeed or all fail.

```json
{
  "requests": [
    { "updateCells": {...} },
    { "repeatCell": {...} },
    { "addConditionalFormatRule": {...} }
  ]
}
```

**Tip:** Order matters. Later requests in the batch see the effects of earlier ones.

---

## Converting A1 Notation to GridRange

When the extrasheet output shows A1 notation (e.g., in `format.json` → `conditionalFormats[].ranges`), convert to GridRange for API calls:

| A1 | GridRange |
|----|-----------|
| `A1` | `startRowIndex: 0, endRowIndex: 1, startColumnIndex: 0, endColumnIndex: 1` |
| `A1:D10` | `startRowIndex: 0, endRowIndex: 10, startColumnIndex: 0, endColumnIndex: 4` |
| `B:B` | `startColumnIndex: 1, endColumnIndex: 2` (rows unbounded) |
| `2:2` | `startRowIndex: 1, endRowIndex: 2` (columns unbounded) |

**Column conversion:** A=0, B=1, ..., Z=25, AA=26, AB=27, ...

---

## Fields Parameter

The `fields` parameter in update requests specifies which properties to update. Use field mask syntax:

```json
// Update only bold and fontSize
"fields": "userEnteredFormat(textFormat(bold,fontSize))"

// Update entire format
"fields": "userEnteredFormat"

// Update value only
"fields": "userEnteredValue"

// Update everything
"fields": "*"
```

---

## Safety Recommendations

### Before Structural Changes
1. Note which formulas reference the affected area (`formula.json`)
2. Check for charts/pivots with data in the area (`feature.json`)
3. Warn user that references will shift

### After Creating New Objects
- Charts, named ranges, sheets get server-assigned IDs
- If you need to reference them immediately, recommend re-pulling

### Avoid These Without User Confirmation
- Deleting sheets (may break references)
- Deleting protected ranges
- Clearing large data ranges
- Overwriting formulas with static values

### Validate Before Executing
- Check sheetId exists in `spreadsheet.json`
- Check chartId/namedRangeId exists before update/delete
- Verify range is within grid bounds (`gridProperties.rowCount`, `columnCount`)

---

## Complete Request Types Reference

The Google Sheets API supports these request types in batchUpdate:

**Cell Operations:**
- `updateCells` - Update multiple cells
- `repeatCell` - Apply same value/format to range
- `appendCells` - Append rows at end of data

**Dimension Operations:**
- `insertDimension` - Insert rows/columns
- `deleteDimension` - Delete rows/columns
- `moveDimension` - Move rows/columns
- `appendDimension` - Add rows/columns at end
- `updateDimensionProperties` - Resize, hide, show
- `autoResizeDimensions` - Auto-fit to content

**Range Operations:**
- `insertRange` - Insert cells (shift others)
- `deleteRange` - Delete cells (shift others)
- `copyPaste` - Copy range to another location
- `cutPaste` - Move range
- `sortRange` - Sort data
- `findReplace` - Find and replace text
- `trimWhitespace` - Remove whitespace
- `deleteDuplicates` - Remove duplicate rows
- `randomizeRange` - Shuffle rows

**Formatting:**
- `repeatCell` - Apply format to range
- `updateCells` - Update cell formats
- `updateBorders` - Set borders
- `mergeCells` - Merge cells
- `unmergeCells` - Unmerge cells
- `addConditionalFormatRule` - Add conditional format
- `updateConditionalFormatRule` - Update conditional format
- `deleteConditionalFormatRule` - Delete conditional format
- `addBanding` - Add banded range
- `updateBanding` - Update banded range
- `deleteBanding` - Delete banded range

**Features:**
- `addChart` - Add chart
- `updateChartSpec` - Update chart
- `deleteEmbeddedObject` - Delete chart/image
- `updateEmbeddedObjectPosition` - Move chart
- `addFilterView` - Add filter view
- `updateFilterView` - Update filter view
- `deleteFilterView` - Delete filter view
- `duplicateFilterView` - Copy filter view
- `setBasicFilter` - Set active filter
- `clearBasicFilter` - Remove active filter
- `addSlicer` - Add slicer
- `updateSlicerSpec` - Update slicer
- `setDataValidation` - Set validation rules
- `addTable` - Add structured table
- `updateTable` - Update table
- `deleteTable` - Delete table

**Named Ranges:**
- `addNamedRange` - Create named range
- `updateNamedRange` - Update named range
- `deleteNamedRange` - Delete named range

**Protection:**
- `addProtectedRange` - Add protection
- `updateProtectedRange` - Update protection
- `deleteProtectedRange` - Remove protection

**Sheets:**
- `addSheet` - Create new sheet
- `deleteSheet` - Delete sheet
- `duplicateSheet` - Copy sheet
- `updateSheetProperties` - Rename, reorder, etc.

**Dimension Groups:**
- `addDimensionGroup` - Create row/column group
- `updateDimensionGroup` - Collapse/expand group
- `deleteDimensionGroup` - Remove group

**Spreadsheet Properties:**
- `updateSpreadsheetProperties` - Title, locale, etc.

**Developer Metadata:**
- `createDeveloperMetadata` - Add metadata
- `updateDeveloperMetadata` - Update metadata
- `deleteDeveloperMetadata` - Remove metadata

**Data Sources:**
- `addDataSource` - Connect external data
- `updateDataSource` - Update connection
- `deleteDataSource` - Remove connection
- `refreshDataSource` - Refresh data

---

## Error Handling

Common API errors and remediation:

| Error | Cause | Solution |
|-------|-------|----------|
| `INVALID_ARGUMENT` | Malformed request | Check field names and types |
| `NOT_FOUND` | Invalid ID | Verify ID from extrasheet files |
| `OUT_OF_RANGE` | Invalid coordinates | Check grid dimensions |
| `PERMISSION_DENIED` | Protected range | Check `protection.json` |
| `FAILED_PRECONDITION` | Conflicting operation | Re-pull and retry |

---

## API Endpoint

```
POST https://sheets.googleapis.com/v4/spreadsheets/{spreadsheetId}:batchUpdate

Headers:
  Authorization: Bearer {access_token}
  Content-Type: application/json

Body:
{
  "requests": [...]
}
```

The response includes details of each operation, including IDs assigned to newly created objects.
