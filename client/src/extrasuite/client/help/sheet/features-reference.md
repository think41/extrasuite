# Sheet Features Reference

Advanced sheet and spreadsheet features are stored in separate JSON files so an
agent can load only what it needs.

Most range-like fields use A1 notation. Sheet folder paths are per-sheet unless
noted otherwise.

## charts.json

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
          "domains": [{"domain": {"sourceRange": {"sources": [{"range": "A2:A10"}]}}}],
          "series": [{"series": {"sourceRange": {"sources": [{"range": "B2:B10"}]}}}]
        }
      }
    }
  ]
}
```

## pivot-tables.json

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

Pivot tables are matched by `anchorCell`.

## tables.json

```json
{
  "tables": [
    {
      "tableId": "1778223018",
      "name": "Table1",
      "range": "A1:J47",
      "columnProperties": [
        {"column": "A", "columnName": "Category"},
        {"column": "B", "columnName": "Resource Type"}
      ]
    }
  ]
}
```

## filters.json

```json
{
  "basicFilter": {
    "range": "A1:E100",
    "filterSpecs": [
      {
        "column": "C",
        "filterCriteria": {
          "condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "Active"}]}
        }
      }
    ]
  },
  "filterViews": [
    {
      "filterViewId": 789,
      "title": "Active Only",
      "range": "A1:E100",
      "filterSpecs": []
    }
  ]
}
```

## banded-ranges.json

```json
{
  "bandedRanges": [
    {
      "bandedRangeId": 123,
      "range": "A1:J100",
      "rowProperties": {
        "headerColor": "#336699",
        "firstBandColor": "#FFFFFF",
        "secondBandColor": "#F2F2F2"
      }
    }
  ]
}
```

## data-validation.json

```json
{
  "dataValidation": [
    {
      "range": "H2... (49 cells)",
      "cells": ["H2", "H3", "H4"],
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

The `range` field is a summary string; `cells` is the canonical list.

## slicers.json

```json
{
  "slicers": [
    {
      "slicerId": 456,
      "position": {
        "overlayPosition": {
          "anchorCell": "M1",
          "widthPixels": 200,
          "heightPixels": 300
        }
      },
      "spec": {
        "dataRange": "A1:E100",
        "title": "Region Filter",
        "column": "C"
      }
    }
  ]
}
```

## data-source-tables.json

```json
{
  "dataSourceTables": [
    {
      "anchorCell": "M1",
      "dataSourceId": "datasource_abc",
      "columns": []
    }
  ]
}
```

Current support is limited. Modify/refresh-style changes work better than
creating or deleting these tables.

## named_ranges.json

Spreadsheet-level, not per-sheet:

```json
{
  "namedRanges": [
    {
      "namedRangeId": "abc123",
      "name": "SalesData",
      "range": "Sheet1!A1:E100"
    }
  ]
}
```

## Informational Pull-Only Files

These may appear in a pull but are not currently applied by push:

  theme.json
  developer_metadata.json
  data_sources.json
  protection.json

## Related

  extrasuite sheet help format-reference     cell formatting, notes, rich text
  extrasuite sheet help comments-reference   Drive comments
