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
| `textFormat.strikethrough` | `true` / `false` |
| `textFormat.underline` | `true` / `false` |
| `wrapStrategy` | `OVERFLOW_CELL` (default), `WRAP`, `CLIP` |
| `padding` | `{"top": 5, "bottom": 5, "left": 10, "right": 10}` (pixels) |
| `textDirection` | `LEFT_TO_RIGHT`, `RIGHT_TO_LEFT` |
| `textRotation` | `{"angle": 45}` (-90 to 90) or `{"vertical": true}` |

---

## Borders

Add borders to cells via the `borders` property inside a format rule:

```json
{
  "formatRules": [
    {
      "range": "A1:D10",
      "format": {
        "borders": {
          "top": {"style": "SOLID", "color": "#000000"},
          "bottom": {"style": "SOLID", "color": "#000000"},
          "left": {"style": "SOLID"},
          "right": {"style": "SOLID"}
        }
      }
    }
  ]
}
```

**Border sides:** `top`, `bottom`, `left`, `right`

**Each side has:**
- `style` — required: `SOLID`, `DASHED`, `DOTTED`, `DOUBLE`, `SOLID_MEDIUM`, `SOLID_THICK`
- `color` — optional hex color (defaults to black)
- `width` — optional integer (pixels)

Borders can be combined with other format properties in the same rule. Removing a format rule that had borders will clear the borders too.

---

## Deleting Formatting

Remove a format rule entry from `formatRules` to reset that range to default formatting. The push will clear all formatting properties and borders on the range.

---

## Conditional Formatting

Highlight cells based on conditions. Uses **hex colors** (same as formatRules).

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
      "range": "A1:D1"
    }
  ]
}
```

Merges use A1 notation for the range. The diff engine automatically converts this to 0-based indices when generating API requests.

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

---

## Dimension Sizing

Row heights and column widths in `dimension.json`:

```json
{
  "rowMetadata": [
    {"row": 1, "pixelSize": 30},
    {"row": 11, "pixelSize": 50, "hidden": true}
  ],
  "columnMetadata": [
    {"column": "A", "pixelSize": 150},
    {"column": "F", "pixelSize": 200}
  ]
}
```

- **rowMetadata**: Uses 1-based row numbers (`"row": 1` = first row)
- **columnMetadata**: Uses column letters (`"column": "A"`)
- **hidden**: Add `"hidden": true` to hide a row or column without deleting its data
- **Reset to default**: Remove an entry from the array to reset that row/column to default size (21px rows, 100px columns) and make it visible again

Only non-default sizes are stored.
