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

---

## Color Format

All colors use **hex strings**: `"#RRGGBB"`

Examples: `"#FF0000"` (red), `"#00FF00"` (green), `"#0000FF"` (blue), `"#FFFFFF"` (white)

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
          "backgroundColor": "#CCFFCC"
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
    "minpoint": {"color": "#FFCCCC", "type": "MIN"},
    "maxpoint": {"color": "#CCFFCC", "type": "MAX"}
  }
}
```

**Point types:** `MIN`, `MAX`, `NUMBER`, `PERCENT`, `PERCENTILE`

**Note:** `ruleIndex` determines rule order. If omitted, it will be auto-assigned.

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

Apply different formatting to parts of a cell's text.

```json
{
  "textFormatRuns": {
    "A1": [
      {"format": {}},
      {"startIndex": 5, "format": {"bold": true}},
      {"startIndex": 10, "format": {"foregroundColor": "#0000FF"}}
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

Alternating row/column colors.

```json
{
  "bandedRanges": [
    {
      "bandedRangeId": 123,
      "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 100},
      "rowProperties": {
        "headerColor": "#336699",
        "firstBandColor": "#FFFFFF",
        "secondBandColor": "#F2F2F2"
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
