# Features Guide

Advanced spreadsheet features stored in separate JSON files per sheet.

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

**Pie charts have different structure:**
```json
{
  "spec": {
    "pieChart": {
      "domain": {...},     // singular object, not array
      "series": {...}      // singular object, not array
    }
  }
}
```

## Data Validation (data-validation.json)

```json
{
  "dataValidation": [
    {
      "range": "H2:H100",
      "cells": ["H2", "H3", "H4", "..."],
      "rule": {
        "condition": {
          "type": "ONE_OF_LIST",
          "values": [
            {"userEnteredValue": "Option A"},
            {"userEnteredValue": "Option B"}
          ]
        },
        "showCustomUi": true,
        "strict": true
      }
    }
  ]
}
```

**Condition types:**
- `ONE_OF_LIST` - Dropdown
- `ONE_OF_RANGE` - Dropdown from cell range
- `BOOLEAN` - Checkbox
- `NUMBER_BETWEEN`, `NUMBER_GREATER`, `NUMBER_LESS`
- `DATE_BEFORE`, `DATE_AFTER`
- `CUSTOM_FORMULA`

**NOT supported (will error):**
- `TEXT_IS_VALID_EMAIL`
- `TEXT_IS_VALID_URL`

## Filters (filters.json)

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
  },
  "filterViews": [
    {
      "filterViewId": 789,
      "title": "Active Only",
      "range": {...},
      "filterSpecs": [...]
    }
  ]
}
```

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

## Banded Ranges (banded-ranges.json)

Alternating row/column colors:

```json
{
  "bandedRanges": [
    {
      "bandedRangeId": 123,
      "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 100},
      "rowProperties": {
        "headerColor": {"red": 0.2, "green": 0.4, "blue": 0.6},
        "firstBandColor": {"red": 1, "green": 1, "blue": 1},
        "secondBandColor": {"red": 0.95, "green": 0.95, "blue": 0.95}
      }
    }
  ]
}
```

## Dimension Sizing (dimension.json)

```json
{
  "rowMetadata": [
    {"index": 0, "pixelSize": 30},
    {"index": 10, "pixelSize": 50, "hidden": true}
  ],
  "columnMetadata": [
    {"index": 0, "pixelSize": 150},
    {"index": 5, "pixelSize": 200}
  ]
}
```

Only non-default sizes are stored (default: 21px rows, 100px columns).

## Named Ranges (named_ranges.json)

At spreadsheet level, not per-sheet:

```json
{
  "namedRanges": [
    {
      "namedRangeId": "abc123",
      "name": "SalesData",
      "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 100, "startColumnIndex": 0, "endColumnIndex": 5}
    }
  ]
}
```
