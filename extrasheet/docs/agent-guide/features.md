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
          "anchorCell": "F1",
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
                "sources": [{"range": "A2:A10"}]
              }
            }
          }],
          "series": [{
            "series": {
              "sourceRange": {
                "sources": [{"range": "B2:B10"}]
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
    "range": "A1:E100",
    "filterSpecs": [{
      "column": "C",
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
      "range": "A1:E100",
      "filterSpecs": [{
        "column": "C",
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
      "source": "A1:E100",
      "rows": [{"sourceColumnOffset": 0, "showTotals": true}],
      "columns": [{"sourceColumnOffset": 1}],
      "values": [{"sourceColumnOffset": 2, "summarizeFunction": "SUM"}]
    }
  ]
}
```

**Summarize functions:** `SUM`, `COUNT`, `AVERAGE`, `MIN`, `MAX`, `COUNTA`, `COUNTUNIQUE`

**sourceColumnOffset:** 0-based offset into the source range columns (0 = first column of source range).

---

## Named Ranges (named_ranges.json)

**At spreadsheet level, not per-sheet.**

```json
{
  "namedRanges": [
    {
      "namedRangeId": "abc123",
      "name": "SalesData",
      "range": "Sheet1!A1:E100"
    },
    {
      "namedRangeId": "def456",
      "name": "Expenses",
      "range": "Sheet2!A1:C50"
    }
  ]
}
```

Use in formulas: `=SUM(SalesData)`, `=AVERAGE(Expenses)`

---

## A1 Notation Throughout

All on-disk formats use **A1 notation** consistently:

| File | Example |
|------|---------|
| `data.tsv` | Row 1 = header, row 2 = first data row |
| `format.json` ranges | `"A1:J1"`, `"B2:B100"` |
| `charts.json` anchors | `"anchorCell": "F1"` |
| `charts.json` sources | `"range": "A2:A10"` |
| `filters.json` ranges | `"range": "A1:E100"` |
| `pivot-tables.json` | `"source": "A1:E100"` |
| `named_ranges.json` | `"range": "Sheet1!A1:E100"` |
| `dimension.json` columns | `"column": "A"` |
| `dimension.json` rows | `"row": 5` (1-based) |

The diff engine automatically converts A1 notation to 0-based indices when generating API requests.
