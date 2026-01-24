# InsertTextRequest

Inserts text into a shape or table cell.

## Schema

```json
{
  "insertText": {
    "objectId": "string",
    "cellLocation": TableCellLocation,
    "text": "string",
    "insertionIndex": integer
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | Yes | ID of shape or table |
| `cellLocation` | TableCellLocation | No | Cell location (for tables) |
| `text` | string | Yes | Text to insert |
| `insertionIndex` | integer | No | Character index for insertion (default: 0) |

## TableCellLocation

For inserting into table cells:

```json
{
  "cellLocation": {
    "rowIndex": 0,
    "columnIndex": 0
  }
}
```

## Examples

### Insert at Beginning

```json
{
  "insertText": {
    "objectId": "my_shape",
    "text": "Hello, World!"
  }
}
```

### Insert at Specific Index

```json
{
  "insertText": {
    "objectId": "my_shape",
    "text": " inserted",
    "insertionIndex": 5
  }
}
```

If shape contains "Hello World", result is "Hello inserted World".

### Insert with Newlines

```json
{
  "insertText": {
    "objectId": "my_shape",
    "text": "Line 1\nLine 2\nLine 3"
  }
}
```

Each `\n` creates a new paragraph.

### Insert into Table Cell

```json
{
  "insertText": {
    "objectId": "my_table",
    "cellLocation": {
      "rowIndex": 0,
      "columnIndex": 0
    },
    "text": "Header Text"
  }
}
```

### Combined: Create Shape and Add Text

```json
{
  "requests": [
    {
      "createShape": {
        "objectId": "title_box",
        "shapeType": "TEXT_BOX",
        "elementProperties": {
          "pageObjectId": "slide_1",
          "size": {
            "width": {"magnitude": 7000000, "unit": "EMU"},
            "height": {"magnitude": 1000000, "unit": "EMU"}
          },
          "transform": {
            "scaleX": 1,
            "scaleY": 1,
            "translateX": 1000000,
            "translateY": 500000,
            "unit": "EMU"
          }
        }
      }
    },
    {
      "insertText": {
        "objectId": "title_box",
        "text": "Presentation Title"
      }
    }
  ]
}
```

## Behavior

### Newline Handling
- Inserting `\n` creates a new `ParagraphMarker`
- Paragraph style copies from current paragraph
- Text runs split at newlines

### Style Inheritance
- Inserted text inherits style from surrounding text
- At beginning: inherits from first character's style
- At end: inherits from last character's style
- In middle: inherits from character at insertion point

### Autofit
- **Important**: Inserting text deactivates autofit settings on the shape

## Response

Empty response: `{}`

## Common Patterns

### Replace All Text

```json
{
  "requests": [
    {
      "deleteText": {
        "objectId": "my_shape",
        "textRange": {"type": "ALL"}
      }
    },
    {
      "insertText": {
        "objectId": "my_shape",
        "text": "New content"
      }
    }
  ]
}
```

### Append Text

First, get the current text length, then:

```json
{
  "insertText": {
    "objectId": "my_shape",
    "text": " appended text",
    "insertionIndex": 50
  }
}
```

### Insert and Style

```json
{
  "requests": [
    {
      "insertText": {
        "objectId": "my_shape",
        "text": "Bold Text"
      }
    },
    {
      "updateTextStyle": {
        "objectId": "my_shape",
        "textRange": {
          "type": "FIXED_RANGE",
          "startIndex": 0,
          "endIndex": 9
        },
        "style": {"bold": true},
        "fields": "bold"
      }
    }
  ]
}
```

## Notes

- Text must be inserted into shapes that support text (TEXT_BOX, RECTANGLE, etc.)
- Cannot insert into images, lines, or videos
- Index is character-based, not byte-based
- Inserting at index beyond text length appends to end

## Related Requests

- [DeleteTextRequest](./delete-text.md) - Remove text
- [UpdateTextStyleRequest](./update-text-style.md) - Style text
- [ReplaceAllTextRequest](./replace-all-text.md) - Global replace
- [CreateShapeRequest](./create-shape.md) - Create shape first

## Related Documentation

- [Text Concept](../../concepts/text.md) - Text structure
- [Styling Guide](../../guides/styling.md) - Text formatting
