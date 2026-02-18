# format.json Reference

Formatting rules for cells: colors, fonts, number formats, conditional formats, merges, notes, rich text.

## Structure

```json
{
  "formatRules": [...],
  "conditionalFormats": [...],
  "merges": [...],
  "notes": {...},
  "textFormatRuns": {...}
}
```

All colors use hex strings: "#RRGGBB"

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

Common format properties:

  backgroundColor             Hex color ("#FF0000")
  textFormat.bold             true / false
  textFormat.italic           true / false
  textFormat.fontSize         Integer (points)
  textFormat.foregroundColor  Hex color
  textFormat.strikethrough    true / false
  textFormat.underline        true / false
  horizontalAlignment         LEFT, CENTER, RIGHT
  verticalAlignment           TOP, MIDDLE, BOTTOM
  numberFormat.type           NUMBER, CURRENCY, DATE, PERCENT, TEXT
  numberFormat.pattern        Format string (e.g. "$#,##0.00", "MMM d, yyyy")
  wrapStrategy               OVERFLOW_CELL (default), WRAP, CLIP
  padding                     {"top": 5, "bottom": 5, "left": 10, "right": 10} (pixels)
  textDirection               LEFT_TO_RIGHT, RIGHT_TO_LEFT
  textRotation                {"angle": 45} (-90 to 90) or {"vertical": true}

Note: formatRules uses "range" (singular string). conditionalFormats uses "ranges"
(plural array) because one rule can apply to multiple disjoint ranges.

---

## Borders

```json
{
  "formatRules": [{
    "range": "A1:D10",
    "format": {
      "borders": {
        "top":    {"style": "SOLID", "color": "#000000"},
        "bottom": {"style": "SOLID", "color": "#000000"},
        "left":   {"style": "SOLID"},
        "right":  {"style": "SOLID"}
      }
    }
  }]
}
```

Border sides: top, bottom, left, right
Each side: style (required), color (optional hex), width (optional integer pixels)
Styles: SOLID, DASHED, DOTTED, DOUBLE, SOLID_MEDIUM, SOLID_THICK

To clear borders: remove the format rule that contained them.

---

## Conditional Formatting

### Boolean Rules

```json
{
  "conditionalFormats": [{
    "ruleIndex": 0,
    "ranges": ["B2:B100"],
    "booleanRule": {
      "condition": {
        "type": "NUMBER_GREATER",
        "values": [{"userEnteredValue": "1000"}]
      },
      "format": {"backgroundColor": "#CCFFCC"}
    }
  }]
}
```

Condition types: NUMBER_GREATER, NUMBER_LESS, NUMBER_BETWEEN, NUMBER_EQUAL,
TEXT_CONTAINS, TEXT_STARTS_WITH, TEXT_ENDS_WITH, TEXT_EQ,
DATE_BEFORE, DATE_AFTER, BLANK, NOT_BLANK, CUSTOM_FORMULA

Custom formula: {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": "=A2>B2"}]}

### Gradient Rules

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

Point types: MIN, MAX, NUMBER, PERCENT, PERCENTILE

---

## Cell Merges

```json
{
  "merges": [{"range": "A1:D1"}]
}
```

Uses A1 notation. The diff engine converts to 0-based indices automatically.

---

## Cell Notes

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

Apply different formatting to parts of a cell's text:

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

startIndex is 0-based character position. Each run applies from startIndex to
the next run's startIndex (or end of cell).

---

## Banded Ranges (Alternating Colors)

```json
{
  "bandedRanges": [{
    "bandedRangeId": 123,
    "range": "A1:J100",
    "rowProperties": {
      "headerColor": "#336699",
      "firstBandColor": "#FFFFFF",
      "secondBandColor": "#F2F2F2"
    }
  }]
}
```

---

## Dimension Sizing (dimension.json)

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

rowMetadata: 1-based row numbers. columnMetadata: column letters.
hidden: true hides the row/column. Remove entry to reset to default size.
