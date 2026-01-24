# Adding Shapes and Text

> **Source**: [Google Slides API - Add Shape](https://developers.google.com/workspace/slides/api/guides/add-shape)

## Overview

The Google Slides API enables developers to programmatically add shapes to slides and insert text into those shapes.

## Shape Elements

A Shape represents various geometric objects like rectangles, arcs, arrows, and text boxes.

### CreateShapeRequest

```json
{
  "createShape": {
    "objectId": "my_shape_id",
    "shapeType": "TEXT_BOX",
    "elementProperties": {
      "pageObjectId": "slide_id",
      "size": {
        "width": {"magnitude": 3000000, "unit": "EMU"},
        "height": {"magnitude": 3000000, "unit": "EMU"}
      },
      "transform": {
        "scaleX": 1,
        "scaleY": 1,
        "translateX": 100000,
        "translateY": 100000,
        "unit": "EMU"
      }
    }
  }
}
```

## Shape Types

| Category | Types |
|----------|-------|
| **Basic** | `RECTANGLE`, `ROUND_RECTANGLE`, `ELLIPSE`, `TRIANGLE`, `DIAMOND` |
| **Text** | `TEXT_BOX` |
| **Arrows** | `ARROW_NORTH`, `ARROW_SOUTH`, `ARROW_EAST`, `ARROW_WEST`, `BENT_ARROW`, `U_TURN_ARROW` |
| **Callouts** | `CALLOUT`, `WEDGE_ELLIPSE_CALLOUT`, `WEDGE_RECTANGLE_CALLOUT` |
| **Stars** | `STAR_4`, `STAR_5`, `STAR_6`, `STAR_8`, `STAR_10`, `STAR_12`, `STAR_16`, `STAR_24`, `STAR_32` |
| **Math** | `PLUS`, `MINUS`, `MULTIPLY`, `DIVIDE`, `NOT_EQUAL` |
| **Flowchart** | `FLOWCHART_PROCESS`, `FLOWCHART_DECISION`, `FLOWCHART_TERMINATOR`, etc. |
| **Other** | `CLOUD`, `HEART`, `LIGHTNING_BOLT`, `SUN`, `MOON`, `SMILEY_FACE`, `DONUT` |

## Adding Text to Shapes

Text can appear in two contexts:
1. Within a shape
2. Within a table cell

### InsertTextRequest

```json
{
  "insertText": {
    "objectId": "my_shape_id",
    "insertionIndex": 0,
    "text": "Hello, World!"
  }
}
```

**Important**: Any Autofit settings on shapes are automatically deactivated by requests that affect text fitting.

## Complete Example: Shape with Text

```json
{
  "requests": [
    {
      "createShape": {
        "objectId": "my_text_box",
        "shapeType": "TEXT_BOX",
        "elementProperties": {
          "pageObjectId": "slide_id",
          "size": {
            "width": {"magnitude": 4445850, "unit": "EMU"},
            "height": {"magnitude": 4445850, "unit": "EMU"}
          },
          "transform": {
            "scaleX": 1,
            "scaleY": 1,
            "translateX": 1270000,
            "translateY": 1270000,
            "unit": "EMU"
          }
        }
      }
    },
    {
      "insertText": {
        "objectId": "my_text_box",
        "text": "My new text box!"
      }
    }
  ]
}
```

## ElementProperties

| Property | Description |
|----------|-------------|
| `pageObjectId` | ID of the slide to add the shape to |
| `size` | Dimensions (width and height) |
| `transform` | Position and scaling |

### Size

```json
{
  "size": {
    "width": {"magnitude": 3000000, "unit": "EMU"},
    "height": {"magnitude": 1500000, "unit": "EMU"}
  }
}
```

### Transform

```json
{
  "transform": {
    "scaleX": 1,
    "scaleY": 1,
    "shearX": 0,
    "shearY": 0,
    "translateX": 100000,
    "translateY": 100000,
    "unit": "EMU"
  }
}
```

## Response

```json
{
  "replies": [
    {
      "createShape": {
        "objectId": "my_text_box"
      }
    },
    {}
  ]
}
```

## Common Patterns

### Creating a Centered Text Box

```json
{
  "createShape": {
    "objectId": "centered_text",
    "shapeType": "TEXT_BOX",
    "elementProperties": {
      "pageObjectId": "slide_id",
      "size": {
        "width": {"magnitude": 6000000, "unit": "EMU"},
        "height": {"magnitude": 1000000, "unit": "EMU"}
      },
      "transform": {
        "scaleX": 1,
        "scaleY": 1,
        "translateX": 1572000,
        "translateY": 2071750,
        "unit": "EMU"
      }
    }
  }
}
```

### Creating a Colored Rectangle

```json
{
  "requests": [
    {
      "createShape": {
        "objectId": "colored_rect",
        "shapeType": "RECTANGLE",
        "elementProperties": {
          "pageObjectId": "slide_id",
          "size": {
            "width": {"magnitude": 2000000, "unit": "EMU"},
            "height": {"magnitude": 2000000, "unit": "EMU"}
          },
          "transform": {
            "scaleX": 1,
            "scaleY": 1,
            "translateX": 500000,
            "translateY": 500000,
            "unit": "EMU"
          }
        }
      }
    },
    {
      "updateShapeProperties": {
        "objectId": "colored_rect",
        "shapeProperties": {
          "shapeBackgroundFill": {
            "solidFill": {
              "color": {
                "rgbColor": {"red": 0.2, "green": 0.5, "blue": 0.8}
              }
            }
          }
        },
        "fields": "shapeBackgroundFill.solidFill.color"
      }
    }
  ]
}
```

## Related Documentation

- [Create Slide](./create-slide.md) - Adding slides
- [Transform Guide](./transform.md) - Positioning shapes
- [Styling](./styling.md) - Formatting shapes
- [Text Structure](../concepts/text.md) - Working with text
- [Transforms](../concepts/transforms.md) - Understanding transforms
