# Text Editing and Styling

> **Source**: [Google Slides API - Styling](https://developers.google.com/workspace/slides/api/guides/styling)

## Overview

The Google Slides API enables developers to modify text in presentations through insertion, deletion, replacement, and styling of both character and paragraph formatting.

## Global Search and Replace

### ReplaceAllTextRequest

```json
{
  "replaceAllText": {
    "containsText": {
      "text": "old text",
      "matchCase": true
    },
    "replaceText": "new text"
  }
}
```

Performs a global search-and-replace throughout the presentation.

## Targeted Text Modification

### InsertTextRequest

```json
{
  "insertText": {
    "objectId": "shape_id",
    "insertionIndex": 0,
    "text": "New text here"
  }
}
```

### DeleteTextRequest

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

### Replace Specific Text

Combine delete and insert in a single batch:

```json
{
  "requests": [
    {
      "deleteText": {
        "objectId": "shape_id",
        "textRange": {
          "type": "FIXED_RANGE",
          "startIndex": 5,
          "endIndex": 15
        }
      }
    },
    {
      "insertText": {
        "objectId": "shape_id",
        "insertionIndex": 5,
        "text": "replacement"
      }
    }
  ]
}
```

## Character Formatting

### UpdateTextStyleRequest

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
      "italic": true,
      "fontSize": {"magnitude": 18, "unit": "PT"}
    },
    "fields": "bold,italic,fontSize"
  }
}
```

### Available Character Styles

| Property | Type | Description |
|----------|------|-------------|
| `bold` | boolean | Bold text |
| `italic` | boolean | Italic text |
| `underline` | boolean | Underlined text |
| `strikethrough` | boolean | Strikethrough text |
| `smallCaps` | boolean | Small capitals |
| `fontFamily` | string | Font family name |
| `fontSize` | Dimension | Font size |
| `foregroundColor` | OpaqueColor | Text color |
| `backgroundColor` | OpaqueColor | Highlight color |
| `link` | Link | Hyperlink |
| `baselineOffset` | enum | SUPERSCRIPT, SUBSCRIPT, NONE |
| `weightedFontFamily` | object | Font with weight |

### Text Color Example

```json
{
  "updateTextStyle": {
    "objectId": "shape_id",
    "textRange": {"type": "ALL"},
    "style": {
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
    "fields": "foregroundColor"
  }
}
```

### Hyperlink Example

```json
{
  "updateTextStyle": {
    "objectId": "shape_id",
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

## Text Range Types

| Type | Description |
|------|-------------|
| `FIXED_RANGE` | Explicit start and end indices |
| `FROM_START_INDEX` | From start index to end of text |
| `ALL` | Entire shape text |

## Paragraph Formatting

### UpdateParagraphStyleRequest

```json
{
  "updateParagraphStyle": {
    "objectId": "shape_id",
    "textRange": {"type": "ALL"},
    "style": {
      "alignment": "CENTER",
      "lineSpacing": 150,
      "spaceAbove": {"magnitude": 10, "unit": "PT"},
      "spaceBelow": {"magnitude": 10, "unit": "PT"}
    },
    "fields": "alignment,lineSpacing,spaceAbove,spaceBelow"
  }
}
```

### Available Paragraph Styles

| Property | Type | Description |
|----------|------|-------------|
| `alignment` | enum | START, CENTER, END, JUSTIFIED |
| `lineSpacing` | number | Line spacing percentage (100 = single) |
| `indentStart` | Dimension | Left indent |
| `indentEnd` | Dimension | Right indent |
| `indentFirstLine` | Dimension | First line indent |
| `spaceAbove` | Dimension | Space above paragraph |
| `spaceBelow` | Dimension | Space below paragraph |
| `direction` | enum | LEFT_TO_RIGHT, RIGHT_TO_LEFT |

## Bulleted Lists

### CreateParagraphBulletsRequest

```json
{
  "createParagraphBullets": {
    "objectId": "shape_id",
    "textRange": {"type": "ALL"},
    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"
  }
}
```

### Bullet Presets

| Preset | Description |
|--------|-------------|
| `BULLET_DISC_CIRCLE_SQUARE` | Disc, circle, square hierarchy |
| `BULLET_DIAMONDX_ARROW3D_SQUARE` | Diamond, arrow, square |
| `BULLET_CHECKBOX` | Checkbox bullets |
| `BULLET_ARROW_DIAMOND_DISC` | Arrow, diamond, disc |
| `BULLET_STAR_CIRCLE_SQUARE` | Star, circle, square |
| `BULLET_ARROW3D_CIRCLE_SQUARE` | 3D arrow, circle, square |
| `BULLET_LEFTTRIANGLE_DIAMOND_DISC` | Triangle, diamond, disc |
| `NUMBERED_DIGIT_ALPHA_ROMAN` | 1, a, i hierarchy |
| `NUMBERED_DIGIT_ALPHA_ROMAN_PARENS` | 1), a), i) |
| `NUMBERED_DIGIT_NESTED` | 1.1, 1.2, etc. |
| `NUMBERED_UPPERALPHA_ALPHA_ROMAN` | A, a, i |
| `NUMBERED_UPPERROMAN_UPPERALPHA_DIGIT` | I, A, 1 |
| `NUMBERED_ZERODIGIT_ALPHA_ROMAN` | 01, a, i |

### DeleteParagraphBulletsRequest

```json
{
  "deleteParagraphBullets": {
    "objectId": "shape_id",
    "textRange": {"type": "ALL"}
  }
}
```

## Complete Styling Example

```json
{
  "requests": [
    {
      "updateTextStyle": {
        "objectId": "title_shape",
        "textRange": {"type": "ALL"},
        "style": {
          "bold": true,
          "fontSize": {"magnitude": 36, "unit": "PT"},
          "foregroundColor": {
            "opaqueColor": {
              "rgbColor": {"red": 0, "green": 0, "blue": 0.5}
            }
          }
        },
        "fields": "bold,fontSize,foregroundColor"
      }
    },
    {
      "updateParagraphStyle": {
        "objectId": "title_shape",
        "textRange": {"type": "ALL"},
        "style": {
          "alignment": "CENTER"
        },
        "fields": "alignment"
      }
    },
    {
      "createParagraphBullets": {
        "objectId": "body_shape",
        "textRange": {"type": "ALL"},
        "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"
      }
    }
  ]
}
```

## Related Documentation

- [Text Structure](../concepts/text.md) - Text element model
- [Field Masks](./field-masks.md) - Efficient updates
- [Add Shape](./add-shape.md) - Creating text boxes
- [Batch Updates](./batch.md) - Combining requests
