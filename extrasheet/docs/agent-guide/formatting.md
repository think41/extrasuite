# Formatting Guide

Advanced formatting operations for cells, conditional formats, merges, and rich text.

## format.json Structure

```json
{
  "formatRules": [...],
  "conditionalFormats": [...],
  "merges": [...],
  "notes": {...},
  "textFormatRuns": {...}
}
```

### Gotcha: Use formatRules array, not cells dict

**Wrong:**
```json
{
  "cells": {
    "A1": {"textFormat": {"bold": true}}
  }
}
```

**Correct:**
```json
{
  "formatRules": [
    {"range": "A1", "format": {"textFormat": {"bold": true}}}
  ]
}
```

---

## Color Formats (Critical!)

**Different sections require different formats:**

| Section | Format | Example |
|---------|--------|---------|
| `formatRules[].format.backgroundColor` | Hex string | `"#E6E6E6"` |
| `formatRules[].format.textFormat.foregroundColor` | Hex string | `"#FF0000"` |
| `conditionalFormats[].*.format.backgroundColor` | RGB dict | `{"red": 0.8, "green": 1.0, "blue": 0.8}` |
| `conditionalFormats[].gradientRule.*.color` | RGB dict | `{"red": 0.96, "green": 0.8, "blue": 0.8}` |
| `textFormatRuns[].format.foregroundColor` | RGB dict | `{"red": 0, "green": 0, "blue": 1}` |
| `bandedRanges[].rowProperties.*Color` | RGB dict | `{"red": 0.2, "green": 0.4, "blue": 0.6}` |

**Wrong format causes:** `'dict' object has no attribute 'lstrip'`

**Rule of thumb:**
- `formatRules` → hex strings
- Everything else → RGB dicts

---

## Format Rules

Apply formatting to cell ranges:

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
    },
    {
      "range": "B2:B100",
      "format": {
        "numberFormat": {"type": "CURRENCY", "pattern": "$#,##0.00"}
      }
    }
  ]
}
```

**Common format properties:**

| Property | Values |
|----------|--------|
| `backgroundColor` | Hex color (`"#FF0000"`) |
| `textFormat.bold` | `true` / `false` |
| `textFormat.italic` | `true` / `false` |
| `textFormat.fontSize` | Integer (points) |
| `textFormat.foregroundColor` | Hex color |
| `horizontalAlignment` | `LEFT`, `CENTER`, `RIGHT` |
| `verticalAlignment` | `TOP`, `MIDDLE`, `BOTTOM` |
| `numberFormat.type` | `NUMBER`, `CURRENCY`, `DATE`, `PERCENT`, `TEXT` |
| `numberFormat.pattern` | Format string (e.g., `"$#,##0.00"`) |
| `wrapStrategy` | `OVERFLOW_CELL`, `WRAP`, `CLIP` |

---

## Conditional Formatting

Highlight cells based on conditions. Uses **RGB dicts** for colors.

### Boolean Rules

```json
{
  "conditionalFormats": [
    {
      "ruleIndex": 0,
      "ranges": ["B2:B100"],
      "booleanRule": {
        "condition": {
          "type": "NUMBER_GREATER",
          "values": [{"userEnteredValue": "1000"}]
        },
        "format": {
          "backgroundColor": {"red": 0.8, "green": 1.0, "blue": 0.8}
        }
      }
    }
  ]
}
```

**Condition types:**
- `NUMBER_GREATER`, `NUMBER_LESS`, `NUMBER_BETWEEN`, `NUMBER_EQUAL`
- `TEXT_CONTAINS`, `TEXT_STARTS_WITH`, `TEXT_ENDS_WITH`, `TEXT_EQ`
- `DATE_BEFORE`, `DATE_AFTER`
- `BLANK`, `NOT_BLANK`
- `CUSTOM_FORMULA` — custom formula returns TRUE

**Custom formula example:**
```json
{
  "condition": {
    "type": "CUSTOM_FORMULA",
    "values": [{"userEnteredValue": "=A2>B2"}]
  }
}
```

### Gradient Rules

Color scale based on values:

```json
{
  "ruleIndex": 1,
  "ranges": ["C2:C100"],
  "gradientRule": {
    "minpoint": {"color": {"red": 1, "green": 0.8, "blue": 0.8}, "type": "MIN"},
    "maxpoint": {"color": {"red": 0.8, "green": 1, "blue": 0.8}, "type": "MAX"}
  }
}
```

**Point types:** `MIN`, `MAX`, `NUMBER`, `PERCENT`, `PERCENTILE`

### Gotcha: ruleIndex is required

Each conditional format must have a `ruleIndex` field (0, 1, 2...) that determines the order rules are applied.

---

## Cell Merges

```json
{
  "merges": [
    {
      "range": "A1:D1",
      "startRow": 0,
      "endRow": 1,
      "startColumn": 0,
      "endColumn": 4
    }
  ]
}
```

**Note:** Both `range` (A1 notation) and coordinates (0-based) are included for clarity.

---

## Cell Notes

Simple key-value mapping:

```json
{
  "notes": {
    "A1": "This is a comment on cell A1",
    "B5": "Another note"
  }
}
```

---

## Rich Text (textFormatRuns)

Apply different formatting to parts of a cell's text. Uses **RGB dicts** for colors.

```json
{
  "textFormatRuns": {
    "A1": [
      {"format": {}},
      {"startIndex": 5, "format": {"bold": true}},
      {"startIndex": 10, "format": {"foregroundColor": {"red": 0, "green": 0, "blue": 1}}}
    ]
  }
}
```

This formats "Hello **World** <blue>Blue</blue>" where:
- Characters 0-4: default
- Characters 5-9: bold
- Characters 10+: blue

---

## Banded Ranges

Alternating row/column colors. Uses **RGB dicts** for colors.

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

---

## Dimension Sizing

Row heights and column widths in `dimension.json`:

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
