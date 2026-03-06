# format.json Reference

`format.json` stores cell formatting, conditional formats, merges, cell notes,
and rich text runs.

This file does not contain:

  banded-ranges.json    Alternating colors
  dimension.json        Row/column sizing and hidden state
  comments.json         Drive comments

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

Concrete editable color values use hex strings such as `"#RRGGBB"`.

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

Common properties:

  backgroundColor               Hex color
  textFormat.bold               true / false
  textFormat.italic             true / false
  textFormat.fontSize           Integer points
  textFormat.foregroundColor    Hex color
  textFormat.strikethrough      true / false
  textFormat.underline          true / false
  textFormat.link               {"uri": "https://..."}
  horizontalAlignment           LEFT, CENTER, RIGHT
  verticalAlignment             TOP, MIDDLE, BOTTOM
  numberFormat.type             NUMBER, CURRENCY, DATE, PERCENT, TEXT
  numberFormat.pattern          Format string
  wrapStrategy                  OVERFLOW_CELL, WRAP, CLIP
  padding                       {"top": 5, "bottom": 5, "left": 10, "right": 10}
  textDirection                 LEFT_TO_RIGHT, RIGHT_TO_LEFT
  textRotation                  {"angle": 45} or {"vertical": true}

## Borders

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

Styles: SOLID, DASHED, DOTTED, DOUBLE, SOLID_MEDIUM, SOLID_THICK

## Conditional Formatting

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
        "format": {"backgroundColor": "#CCFFCC"}
      }
    }
  ]
}
```

### Gradient Rules

```json
{
  "conditionalFormats": [
    {
      "ranges": ["C2:C100"],
      "gradientRule": {
        "minpoint": {"color": "#FFCCCC", "type": "MIN"},
        "maxpoint": {"color": "#CCFFCC", "type": "MAX"}
      }
    }
  ]
}
```

Notes:

  Existing rules should keep their ruleIndex
  New rules may omit ruleIndex; diff will assign one after the last existing rule

## Merges

```json
{
  "merges": [{"range": "A1:D1"}]
}
```

## Cell Notes

```json
{
  "notes": {
    "A1": "This is a note on cell A1",
    "B5": "Another note"
  }
}
```

These are cell notes, not Drive comments. Drive comments live in `comments.json`.

## Rich Text

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

`startIndex` is a 0-based character offset within the cell text.

## Related Files

  extrasuite sheet help features-reference   charts, filters, pivot tables, tables, banded ranges
  dimension.json                             row/column size and hidden state
  comments.json                              Drive comments
