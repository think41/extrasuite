# Text Structure and Styling

> **Source**: [Google Slides API - Text](https://developers.google.com/workspace/slides/api/concepts/text)

## Text Representation

Text in Google Slides is organized as sequences of `TextElement` structures within shapes or table cells. Each element contains start/end indices and one of three types.

## Text Element Types

### ParagraphMarker

Represents paragraph starts, spanning from the paragraph beginning through its newline character.

```json
{
  "startIndex": 0,
  "endIndex": 15,
  "paragraphMarker": {
    "style": {
      "alignment": "START",
      "indentStart": {"magnitude": 0, "unit": "PT"},
      "indentEnd": {"magnitude": 0, "unit": "PT"}
    },
    "bullet": {
      "listId": "list_id",
      "glyph": "•"
    }
  }
}
```

**Key points**:
- Includes styling for indentation, alignment, and bullet properties
- Paragraphs never overlap
- Always end with newlines

### TextRun

A contiguous string with uniform text styling (bold, italic, etc.).

```json
{
  "startIndex": 0,
  "endIndex": 14,
  "textRun": {
    "content": "Hello, World!",
    "style": {
      "bold": true,
      "italic": false,
      "fontSize": {"magnitude": 18, "unit": "PT"},
      "foregroundColor": {
        "opaqueColor": {
          "rgbColor": {"red": 0, "green": 0, "blue": 0}
        }
      }
    }
  }
}
```

**Key points**:
- Never cross paragraph boundaries
- Even identically styled text splits at newlines into separate runs

### AutoText

Dynamically changing content like slide numbers.

```json
{
  "startIndex": 0,
  "endIndex": 1,
  "autoText": {
    "type": "SLIDE_NUMBER",
    "content": "1"
  }
}
```

## Text Content Structure

The complete text content of a shape:

```json
{
  "shape": {
    "text": {
      "textElements": [
        {
          "startIndex": 0,
          "endIndex": 14,
          "paragraphMarker": { ... }
        },
        {
          "startIndex": 0,
          "endIndex": 13,
          "textRun": {
            "content": "Hello World!\n",
            "style": { ... }
          }
        }
      ]
    }
  }
}
```

## Text Modification Operations

### Inserting Text

Use `InsertTextRequest` with an `insertionIndex` parameter:

```json
{
  "insertText": {
    "objectId": "shape_id",
    "insertionIndex": 0,
    "text": "New text here"
  }
}
```

**Behavior**:
- Inserting newlines automatically creates `ParagraphMarker` elements
- Paragraph styles copy from the current paragraph
- Character styling matches the existing style at insertion point

### Deleting Text

`DeleteTextRequest` removes specified ranges:

```json
{
  "deleteText": {
    "objectId": "shape_id",
    "textRange": {
      "type": "FIXED_RANGE",
      "startIndex": 0,
      "endIndex": 10
    }
  }
}
```

**Behavior**:
- Deletions crossing paragraph boundaries merge paragraphs
- Deletes separating markers
- Ranges encompassing entire text runs remove both content and the run

### Text Range Types

| Type | Description |
|------|-------------|
| `FIXED_RANGE` | Explicit start and end indices |
| `FROM_START_INDEX` | From start index to end of text |
| `ALL` | All text in the shape |

## Style Updates

### Character Styles

Update via `UpdateTextStyleRequest`:

```json
{
  "updateTextStyle": {
    "objectId": "shape_id",
    "textRange": {
      "type": "FIXED_RANGE",
      "startIndex": 0,
      "endIndex": 5
    },
    "style": {
      "bold": true,
      "fontSize": {"magnitude": 24, "unit": "PT"}
    },
    "fields": "bold,fontSize"
  }
}
```

Available character style properties:
- `bold`, `italic`, `underline`, `strikethrough`
- `fontFamily`, `fontSize`
- `foregroundColor`, `backgroundColor`
- `link` (hyperlinks)
- `smallCaps`, `baselineOffset`

### Paragraph Styles

Update via `UpdateParagraphStyleRequest`:

```json
{
  "updateParagraphStyle": {
    "objectId": "shape_id",
    "textRange": {"type": "ALL"},
    "style": {
      "alignment": "CENTER",
      "lineSpacing": 150
    },
    "fields": "alignment,lineSpacing"
  }
}
```

Available paragraph style properties:
- `alignment`: START, CENTER, END, JUSTIFIED
- `indentStart`, `indentEnd`, `indentFirstLine`
- `lineSpacing`, `spaceAbove`, `spaceBelow`
- `direction`: LEFT_TO_RIGHT, RIGHT_TO_LEFT

### Bullets

Create bullets with `CreateParagraphBulletsRequest`:

```json
{
  "createParagraphBullets": {
    "objectId": "shape_id",
    "textRange": {"type": "ALL"},
    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"
  }
}
```

Remove with `DeleteParagraphBulletsRequest`:

```json
{
  "deleteParagraphBullets": {
    "objectId": "shape_id",
    "textRange": {"type": "ALL"}
  }
}
```

## Style Inheritance in Placeholders

Child placeholder shapes inherit text styles from parent shapes through a structured model:

### Inheritance Hierarchy

1. Parent shapes contain eight `ParagraphMarker`/`TextRun` pairs supporting eight nesting levels
2. The first pair controls level-0 and non-list paragraph styling
3. Remaining pairs handle nested list levels 1-7

### Override Behavior

- Child shapes can override inherited styles by specifying local properties
- Removing explicit properties allows inheritance to resume
- Setting child styles matching inherited values implicitly unsets them, enabling future parent updates to propagate

### Bullet Glyph Styling

Bullet glyphs follow a distinct inheritance hierarchy:
1. First inheriting from `NestingLevel.bullet_style` in the bullet's `List` object
2. Then from the parent placeholder's corresponding level
3. Finally from remaining parent placeholders

## Related Documentation

- [Page Elements](./page-elements.md) - Understanding element types
- [Styling Guide](../guides/styling.md) - Text formatting examples
- [Add Shape Guide](../guides/add-shape.md) - Creating shapes with text
- [Field Masks](../guides/field-masks.md) - Efficient style updates
