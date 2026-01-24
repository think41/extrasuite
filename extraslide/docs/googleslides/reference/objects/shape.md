# Shape

A PageElement kind representing a generic shape including text boxes.

## Schema

```json
{
  "shapeType": "ShapeType",
  "text": TextContent,
  "shapeProperties": ShapeProperties,
  "placeholder": Placeholder
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `shapeType` | enum | The type of shape |
| `text` | [TextContent](./text-content.md) | Text content within the shape |
| `shapeProperties` | [ShapeProperties](./shape-properties.md) | Visual properties |
| `placeholder` | Placeholder | Placeholder information if applicable |

## Shape Types

### Basic Shapes

| Type | Description |
|------|-------------|
| `TEXT_BOX` | Text box |
| `RECTANGLE` | Rectangle |
| `ROUND_RECTANGLE` | Rounded rectangle |
| `ELLIPSE` | Ellipse/Circle |
| `TRIANGLE` | Triangle |
| `DIAMOND` | Diamond |

### Arrows

| Type | Description |
|------|-------------|
| `LEFT_ARROW` | Left arrow |
| `RIGHT_ARROW` | Right arrow |
| `UP_ARROW` | Up arrow |
| `DOWN_ARROW` | Down arrow |
| `LEFT_RIGHT_ARROW` | Bidirectional horizontal arrow |
| `UP_DOWN_ARROW` | Bidirectional vertical arrow |
| `BENT_ARROW` | Bent arrow |
| `CURVED_LEFT_ARROW` | Curved left arrow |
| `CURVED_RIGHT_ARROW` | Curved right arrow |

### Stars

| Type | Description |
|------|-------------|
| `STAR_4` | 4-pointed star |
| `STAR_5` | 5-pointed star |
| `STAR_6` | 6-pointed star |
| `STAR_8` | 8-pointed star |
| `STAR_10` | 10-pointed star |
| `STAR_12` | 12-pointed star |
| `STAR_16` | 16-pointed star |
| `STAR_24` | 24-pointed star |
| `STAR_32` | 32-pointed star |

### Callouts

| Type | Description |
|------|-------------|
| `WEDGE_ELLIPSE_CALLOUT` | Ellipse callout |
| `WEDGE_RECTANGLE_CALLOUT` | Rectangle callout |
| `WEDGE_ROUND_RECTANGLE_CALLOUT` | Rounded rectangle callout |
| `CLOUD_CALLOUT` | Cloud callout |

### Flowchart Shapes

| Type | Description |
|------|-------------|
| `FLOW_CHART_PROCESS` | Process |
| `FLOW_CHART_DECISION` | Decision |
| `FLOW_CHART_TERMINATOR` | Terminator |
| `FLOW_CHART_INPUT_OUTPUT` | Input/Output |
| `FLOW_CHART_DOCUMENT` | Document |
| `FLOW_CHART_CONNECTOR` | Connector |
| `FLOW_CHART_PREDEFINED_PROCESS` | Predefined process |

### Math Symbols

| Type | Description |
|------|-------------|
| `MATH_PLUS` | Plus sign |
| `MATH_MINUS` | Minus sign |
| `MATH_MULTIPLY` | Multiply sign |
| `MATH_DIVIDE` | Divide sign |
| `MATH_EQUAL` | Equal sign |
| `MATH_NOT_EQUAL` | Not equal sign |

### Other Shapes

| Type | Description |
|------|-------------|
| `CLOUD` | Cloud |
| `HEART` | Heart |
| `LIGHTNING_BOLT` | Lightning bolt |
| `SUN` | Sun |
| `MOON` | Moon |
| `SMILEY_FACE` | Smiley face |
| `DONUT` | Donut |
| `HEXAGON` | Hexagon |
| `OCTAGON` | Octagon |
| `PENTAGON` | Pentagon |

## ShapeProperties

```json
{
  "shapeBackgroundFill": {
    "solidFill": {
      "color": {
        "rgbColor": {"red": 0.8, "green": 0.2, "blue": 0.2}
      },
      "alpha": 1
    }
  },
  "outline": {
    "outlineFill": {
      "solidFill": {
        "color": {"rgbColor": {"red": 0, "green": 0, "blue": 0}}
      }
    },
    "weight": {"magnitude": 1, "unit": "PT"},
    "dashStyle": "SOLID"
  },
  "shadow": {...},
  "link": {
    "url": "https://example.com"
  },
  "contentAlignment": "MIDDLE"
}
```

## Placeholder

If the shape is a placeholder:

```json
{
  "placeholder": {
    "type": "TITLE | SUBTITLE | BODY | SLIDE_NUMBER | ...",
    "index": 0,
    "parentObjectId": "parent_placeholder_id"
  }
}
```

### Placeholder Types

| Type | Description |
|------|-------------|
| `TITLE` | Slide title |
| `SUBTITLE` | Subtitle |
| `BODY` | Body content |
| `HEADER` | Header |
| `FOOTER` | Footer |
| `SLIDE_NUMBER` | Slide number |
| `DATE_AND_TIME` | Date/time |
| `CENTERED_TITLE` | Centered title |
| `SLIDE_IMAGE` | Slide image (in notes) |

## Example

```json
{
  "objectId": "g123_shape1",
  "size": {
    "width": {"magnitude": 3000000, "unit": "EMU"},
    "height": {"magnitude": 566350, "unit": "EMU"}
  },
  "transform": {
    "scaleX": 2.4384,
    "scaleY": 1.2,
    "translateX": 311700,
    "translateY": 744575,
    "unit": "EMU"
  },
  "shape": {
    "shapeType": "TEXT_BOX",
    "text": {
      "textElements": [
        {
          "startIndex": 0,
          "endIndex": 12,
          "paragraphMarker": {
            "style": {
              "alignment": "START"
            }
          }
        },
        {
          "startIndex": 0,
          "endIndex": 11,
          "textRun": {
            "content": "Hello World",
            "style": {
              "bold": false,
              "fontSize": {"magnitude": 18, "unit": "PT"}
            }
          }
        }
      ]
    },
    "shapeProperties": {
      "shapeBackgroundFill": {
        "propertyState": "NOT_RENDERED"
      },
      "outline": {
        "propertyState": "NOT_RENDERED"
      }
    }
  }
}
```

## Creating a Shape

```json
{
  "createShape": {
    "objectId": "my_shape",
    "shapeType": "TEXT_BOX",
    "elementProperties": {
      "pageObjectId": "slide_id",
      "size": {
        "width": {"magnitude": 3000000, "unit": "EMU"},
        "height": {"magnitude": 1000000, "unit": "EMU"}
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

## Updating Shape Properties

```json
{
  "updateShapeProperties": {
    "objectId": "my_shape",
    "shapeProperties": {
      "shapeBackgroundFill": {
        "solidFill": {
          "color": {"rgbColor": {"red": 1, "green": 0.8, "blue": 0}}
        }
      }
    },
    "fields": "shapeBackgroundFill.solidFill.color"
  }
}
```

## Related Objects

- [TextContent](./text-content.md) - Text within shapes
- [ShapeProperties](./shape-properties.md) - Visual properties
- [PageElement](./page-element.md) - Parent container

## Related Documentation

- [Add Shape Guide](../../guides/add-shape.md) - Creating shapes
- [Styling Guide](../../guides/styling.md) - Text and shape styling
