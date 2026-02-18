# Sheet Features Reference

Advanced spreadsheet features: charts, data validation, filters, pivot tables, named ranges.

All on-disk formats use A1 notation consistently. The diff engine converts to
0-based indices when generating API requests.

---

## Charts (charts.json)

```json
{
  "charts": [{
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
        "domains": [{"domain": {"sourceRange": {"sources": [{"range": "A2:A10"}]}}}],
        "series": [{"series": {"sourceRange": {"sources": [{"range": "B2:B10"}]}},
                    "targetAxis": "LEFT_AXIS"}]
      }
    }
  }]
}
```

Chart types: BAR, COLUMN, LINE, PIE, SCATTER, AREA, COMBO

Pie charts use a different structure (singular domain/series, not arrays):
  "pieChart": {"domain": {...}, "series": {...}}

Basic charts (bar, column, line, scatter, area) use plural arrays:
  "basicChart": {"domains": [...], "series": [...]}

---

## Data Validation (data-validation.json)

```json
{
  "dataValidation": [{
    "range": "H2:H100",
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
  }]
}
```

Condition types:
  ONE_OF_LIST     Dropdown with fixed values
  ONE_OF_RANGE    Dropdown from cell range: {"userEnteredValue": "='Lookup'!A:A"}
  BOOLEAN         Checkbox
  NUMBER_BETWEEN  Number range constraint
  CUSTOM_FORMULA  Custom validation formula

Note: TEXT_IS_VALID_EMAIL and TEXT_IS_VALID_URL are not supported - use CUSTOM_FORMULA.

---

## Filters (filters.json)

Basic filter (applies to entire sheet):
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

Named filter views (users can switch between):
```json
{
  "filterViews": [{
    "filterViewId": 789,
    "title": "Active Only",
    "range": "A1:E100",
    "filterSpecs": [...]
  }]
}
```

---

## Pivot Tables (pivot-tables.json)

```json
{
  "pivotTables": [{
    "anchorCell": "G1",
    "source": "A1:E100",
    "rows": [{"sourceColumnOffset": 0, "showTotals": true}],
    "columns": [{"sourceColumnOffset": 1}],
    "values": [{"sourceColumnOffset": 2, "summarizeFunction": "SUM"}]
  }]
}
```

sourceColumnOffset is 0-based into the source range columns.
Summarize functions: SUM, COUNT, AVERAGE, MIN, MAX, COUNTA, COUNTUNIQUE

---

## Named Ranges (named_ranges.json)

Spreadsheet-level (not per-sheet):

```json
{
  "namedRanges": [{
    "namedRangeId": "abc123",
    "name": "SalesData",
    "range": "Sheet1!A1:E100"
  }]
}
```

Use in formulas: =SUM(SalesData), =AVERAGE(SalesData)
