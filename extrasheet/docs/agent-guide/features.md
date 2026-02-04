# Features Guide

Advanced spreadsheet features: charts, data validation, filters, pivot tables, and named ranges.

---

## Charts (charts.json)

```json
{
  "charts": [
    {
      "chartId": 123456,
      "position": {
        "overlayPosition": {
          "anchorCell": {"sheetId": 0, "rowIndex": 0, "columnIndex": 5},
          "widthPixels": 600,
          "heightPixels": 400
        }
      },
      "spec": {
        "title": "Sales by Region",
        "basicChart": {
          "chartType": "COLUMN",
          "legendPosition": "BOTTOM_LEGEND",
          "domains": [{
            "domain": {
              "sourceRange": {
                "sources": [{"sheetId": 0, "startRowIndex": 1, "endRowIndex": 10, "startColumnIndex": 0, "endColumnIndex": 1}]
              }
            }
          }],
          "series": [{
            "series": {
              "sourceRange": {
                "sources": [{"sheetId": 0, "startRowIndex": 1, "endRowIndex": 10, "startColumnIndex": 1, "endColumnIndex": 2}]
              }
            },
            "targetAxis": "LEFT_AXIS"
          }]
        }
      }
    }
  ]
}
```

**Chart types:** `BAR`, `COLUMN`, `LINE`, `PIE`, `SCATTER`, `AREA`, `COMBO`

### Gotcha: Pie charts have different structure

**Basic charts (bar, column, line, scatter, area):**
```json
{
  "spec": {
    "basicChart": {
      "chartType": "COLUMN",
      "domains": [...],     // plural, array
      "series": [...]       // plural, array
    }
  }
}
```

**Pie charts:**
```json
{
  "spec": {
    "pieChart": {
      "domain": {...},     // singular, object
      "series": {...}      // singular, object
    }
  }
}
```

---

## Data Validation (data-validation.json)

Create dropdowns, checkboxes, and input constraints.

```json
{
  "dataValidation": [
    {
      "range": "H2:H100",
      "cells": ["H2", "H3", "H4"],
      "rule": {
        "condition": {
          "type": "ONE_OF_LIST",
          "values": [
            {"userEnteredValue": "Option A"},
            {"userEnteredValue": "Option B"},
            {"userEnteredValue": "Option C"}
          ]
        },
        "showCustomUi": true,
        "strict": true
      }
    }
  ]
}
```

### Condition Types

| Type | Use Case |
|------|----------|
| `ONE_OF_LIST` | Dropdown with fixed values |
| `ONE_OF_RANGE` | Dropdown from cell range |
| `BOOLEAN` | Checkbox |
| `NUMBER_BETWEEN` | Number in range |
| `NUMBER_GREATER`, `NUMBER_LESS` | Number constraints |
| `DATE_BEFORE`, `DATE_AFTER` | Date constraints |
| `CUSTOM_FORMULA` | Custom validation |

### Gotcha: Unsupported validation types

These types will cause API errors:
- `TEXT_IS_VALID_EMAIL`
- `TEXT_IS_VALID_URL`

**Workaround:** Use `CUSTOM_FORMULA` with a regex pattern instead.

### Checkbox Example

```json
{
  "range": "A2:A100",
  "rule": {
    "condition": {"type": "BOOLEAN"},
    "showCustomUi": true
  }
}
```

### Dropdown from Range

```json
{
  "range": "B2:B100",
  "rule": {
    "condition": {
      "type": "ONE_OF_RANGE",
      "values": [{"userEnteredValue": "='Lookup'!A:A"}]
    },
    "showCustomUi": true
  }
}
```

---

## Filters (filters.json)

### Basic Filter

Applies to the entire sheet:

```json
{
  "basicFilter": {
    "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 100, "startColumnIndex": 0, "endColumnIndex": 5},
    "filterSpecs": [{
      "columnIndex": 2,
      "filterCriteria": {
        "condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "Active"}]}
      }
    }]
  }
}
```

### Filter Views

Named filter configurations users can switch between:

```json
{
  "filterViews": [
    {
      "filterViewId": 789,
      "title": "Active Only",
      "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 100, "startColumnIndex": 0, "endColumnIndex": 5},
      "filterSpecs": [{
        "columnIndex": 2,
        "filterCriteria": {
          "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Active"}]}
        }
      }]
    }
  ]
}
```

---

## Pivot Tables (pivot-tables.json)

```json
{
  "pivotTables": [
    {
      "anchorCell": "G1",
      "source": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 100, "startColumnIndex": 0, "endColumnIndex": 5},
      "rows": [{"sourceColumnOffset": 0, "showTotals": true}],
      "columns": [{"sourceColumnOffset": 1}],
      "values": [{"sourceColumnOffset": 2, "summarizeFunction": "SUM"}]
    }
  ]
}
```

**Summarize functions:** `SUM`, `COUNT`, `AVERAGE`, `MIN`, `MAX`, `COUNTA`, `COUNTUNIQUE`

**sourceColumnOffset:** 0-based index into the source range columns.

---

## Named Ranges (named_ranges.json)

**At spreadsheet level, not per-sheet.**

```json
{
  "namedRanges": [
    {
      "namedRangeId": "abc123",
      "name": "SalesData",
      "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 100, "startColumnIndex": 0, "endColumnIndex": 5}
    },
    {
      "namedRangeId": "def456",
      "name": "Expenses",
      "range": {"sheetId": 1, "startRowIndex": 0, "endRowIndex": 50, "startColumnIndex": 0, "endColumnIndex": 3}
    }
  ]
}
```

Use in formulas: `=SUM(SalesData)`, `=AVERAGE(Expenses)`

---

## Index Numbering Reference

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
