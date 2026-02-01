# Formatting Guide

## format.json Structure

```json
{
  "formatRules": [
    {"range": "A1:J1", "format": {"textFormat": {"bold": true}}}
  ],
  "conditionalFormats": [...],
  "merges": [...],
  "textFormatRuns": {...},
  "notes": {...}
}
```

## Color Formats (Critical!)

**Different sections require different formats:**

| Section | Format | Example |
|---------|--------|---------|
| `formatRules[].format.backgroundColor` | Hex string | `"#E6E6E6"` |
| `formatRules[].format.textFormat.foregroundColor` | Hex string | `"#FF0000"` |
| `conditionalFormats[].*.format.backgroundColor` | RGB dict | `{"red": 0.8, "green": 1.0, "blue": 0.8}` |
| `textFormatRuns[].format.foregroundColor` | RGB dict | `{"red": 0, "green": 0, "blue": 1}` |

Wrong format causes: `'dict' object has no attribute 'lstrip'`

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
- `backgroundColor` - Hex color
- `textFormat.bold`, `textFormat.italic` - Boolean
- `textFormat.fontSize` - Integer (points)
- `textFormat.foregroundColor` - Hex color
- `horizontalAlignment` - `LEFT`, `CENTER`, `RIGHT`
- `verticalAlignment` - `TOP`, `MIDDLE`, `BOTTOM`
- `numberFormat.type` - `NUMBER`, `CURRENCY`, `DATE`, `PERCENT`
- `numberFormat.pattern` - Format string

## Conditional Formatting

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
- `NUMBER_GREATER`, `NUMBER_LESS`, `NUMBER_BETWEEN`
- `TEXT_CONTAINS`, `TEXT_STARTS_WITH`, `TEXT_ENDS_WITH`
- `DATE_BEFORE`, `DATE_AFTER`
- `CUSTOM_FORMULA` - Custom formula returns TRUE

**Gradient rules:**
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

## Cell Notes

```json
{
  "notes": {
    "A1": "This is a comment on cell A1",
    "B5": "Another note"
  }
}
```

## Rich Text (textFormatRuns)

Apply different formatting to parts of a cell's text:

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
