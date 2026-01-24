# UpdateTextStyleRequest

Updates the styling of text within a shape or table cell.

## Schema

```json
{
  "updateTextStyle": {
    "objectId": "string",
    "cellLocation": TableCellLocation,
    "textRange": Range,
    "style": TextStyle,
    "fields": "string"
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | Yes | ID of shape or table |
| `cellLocation` | TableCellLocation | No | Cell location (for tables) |
| `textRange` | Range | No | Range to style (default: all text) |
| `style` | TextStyle | Yes | Style properties to apply |
| `fields` | string | Yes | Field mask specifying which properties to update |

## TextRange

```json
{
  "textRange": {
    "type": "FIXED_RANGE",
    "startIndex": 0,
    "endIndex": 10
  }
}
```

| Type | Description |
|------|-------------|
| `FIXED_RANGE` | Explicit start and end indices |
| `FROM_START_INDEX` | From startIndex to end |
| `ALL` | Entire text content |

## TextStyle Properties

| Property | Type | Field Mask |
|----------|------|------------|
| `bold` | boolean | `bold` |
| `italic` | boolean | `italic` |
| `underline` | boolean | `underline` |
| `strikethrough` | boolean | `strikethrough` |
| `smallCaps` | boolean | `smallCaps` |
| `fontFamily` | string | `fontFamily` |
| `fontSize` | Dimension | `fontSize` |
| `foregroundColor` | OptionalColor | `foregroundColor` |
| `backgroundColor` | OptionalColor | `backgroundColor` |
| `link` | Link | `link` |
| `baselineOffset` | enum | `baselineOffset` |
| `weightedFontFamily` | WeightedFontFamily | `weightedFontFamily` |

## Examples

### Make Text Bold

```json
{
  "updateTextStyle": {
    "objectId": "my_shape",
    "textRange": {"type": "ALL"},
    "style": {
      "bold": true
    },
    "fields": "bold"
  }
}
```

### Multiple Style Properties

```json
{
  "updateTextStyle": {
    "objectId": "my_shape",
    "textRange": {"type": "ALL"},
    "style": {
      "bold": true,
      "italic": true,
      "fontSize": {"magnitude": 24, "unit": "PT"}
    },
    "fields": "bold,italic,fontSize"
  }
}
```

### Change Font and Color

```json
{
  "updateTextStyle": {
    "objectId": "my_shape",
    "textRange": {"type": "ALL"},
    "style": {
      "fontFamily": "Roboto",
      "foregroundColor": {
        "opaqueColor": {
          "rgbColor": {
            "red": 0.2,
            "green": 0.4,
            "blue": 0.8
          }
        }
      }
    },
    "fields": "fontFamily,foregroundColor"
  }
}
```

### Style Specific Range

```json
{
  "updateTextStyle": {
    "objectId": "my_shape",
    "textRange": {
      "type": "FIXED_RANGE",
      "startIndex": 0,
      "endIndex": 5
    },
    "style": {
      "bold": true,
      "foregroundColor": {
        "opaqueColor": {
          "rgbColor": {"red": 1, "green": 0, "blue": 0}
        }
      }
    },
    "fields": "bold,foregroundColor"
  }
}
```

### Add Hyperlink

```json
{
  "updateTextStyle": {
    "objectId": "my_shape",
    "textRange": {
      "type": "FIXED_RANGE",
      "startIndex": 10,
      "endIndex": 20
    },
    "style": {
      "link": {
        "url": "https://example.com"
      }
    },
    "fields": "link"
  }
}
```

### Remove Link

```json
{
  "updateTextStyle": {
    "objectId": "my_shape",
    "textRange": {
      "type": "FIXED_RANGE",
      "startIndex": 10,
      "endIndex": 20
    },
    "style": {},
    "fields": "link"
  }
}
```

Setting a field in the mask without a value clears it.

### Superscript/Subscript

```json
{
  "updateTextStyle": {
    "objectId": "my_shape",
    "textRange": {
      "type": "FIXED_RANGE",
      "startIndex": 5,
      "endIndex": 6
    },
    "style": {
      "baselineOffset": "SUPERSCRIPT"
    },
    "fields": "baselineOffset"
  }
}
```

Values: `NONE`, `SUPERSCRIPT`, `SUBSCRIPT`

### Background Highlight

```json
{
  "updateTextStyle": {
    "objectId": "my_shape",
    "textRange": {"type": "ALL"},
    "style": {
      "backgroundColor": {
        "opaqueColor": {
          "rgbColor": {"red": 1, "green": 1, "blue": 0}
        }
      }
    },
    "fields": "backgroundColor"
  }
}
```

### Table Cell Styling

```json
{
  "updateTextStyle": {
    "objectId": "my_table",
    "cellLocation": {
      "rowIndex": 0,
      "columnIndex": 0
    },
    "textRange": {"type": "ALL"},
    "style": {
      "bold": true,
      "fontSize": {"magnitude": 14, "unit": "PT"}
    },
    "fields": "bold,fontSize"
  }
}
```

## Response

Empty response: `{}`

## Field Mask Behavior

| In Mask | Has Value | Result |
|---------|-----------|--------|
| Yes | Yes | Property updated |
| Yes | No | Property cleared/reset |
| No | - | Property unchanged |

## Notes

- Always specify `fields` to avoid unintended changes
- Avoid using `*` wildcard in production
- Link changes may affect text color and underline
- Font sizes are typically in PT (points)

## Related Requests

- [UpdateParagraphStyleRequest](./update-paragraph-style.md) - Paragraph formatting
- [InsertTextRequest](./insert-text.md) - Add text
- [CreateParagraphBulletsRequest](./create-paragraph-bullets.md) - Add bullets

## Related Documentation

- [TextStyle Object](../objects/text-style.md) - Full property list
- [Styling Guide](../../guides/styling.md) - Usage examples
- [Field Masks Guide](../../guides/field-masks.md) - Field mask patterns
