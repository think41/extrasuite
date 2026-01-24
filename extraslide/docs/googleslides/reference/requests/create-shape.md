# CreateShapeRequest

Creates a new shape on a slide.

## Schema

```json
{
  "createShape": {
    "objectId": "string",
    "elementProperties": PageElementProperties,
    "shapeType": "ShapeType"
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | Unique ID for the shape (auto-generated if not provided) |
| `elementProperties` | PageElementProperties | Yes | Size, position, and parent page |
| `shapeType` | enum | Yes | Type of shape to create |

## PageElementProperties

```json
{
  "elementProperties": {
    "pageObjectId": "slide_id",
    "size": {
      "width": {"magnitude": 3000000, "unit": "EMU"},
      "height": {"magnitude": 1000000, "unit": "EMU"}
    },
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
}
```

## Common Shape Types

| Type | Description |
|------|-------------|
| `TEXT_BOX` | Text box |
| `RECTANGLE` | Rectangle |
| `ROUND_RECTANGLE` | Rounded rectangle |
| `ELLIPSE` | Ellipse/Circle |
| `TRIANGLE` | Triangle |
| `DIAMOND` | Diamond |
| `STAR_5` | 5-pointed star |
| `ARROW_EAST` | Right arrow |
| `CLOUD` | Cloud shape |
| `HEART` | Heart shape |

See [Shape](../objects/shape.md) for complete list.

## Examples

### Create Text Box

```json
{
  "createShape": {
    "objectId": "my_textbox",
    "shapeType": "TEXT_BOX",
    "elementProperties": {
      "pageObjectId": "slide_1",
      "size": {
        "width": {"magnitude": 5000000, "unit": "EMU"},
        "height": {"magnitude": 1000000, "unit": "EMU"}
      },
      "transform": {
        "scaleX": 1,
        "scaleY": 1,
        "translateX": 2000000,
        "translateY": 2000000,
        "unit": "EMU"
      }
    }
  }
}
```

### Create Rectangle

```json
{
  "createShape": {
    "objectId": "my_rect",
    "shapeType": "RECTANGLE",
    "elementProperties": {
      "pageObjectId": "slide_1",
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
}
```

### Create with Text (Combined Batch)

```json
{
  "requests": [
    {
      "createShape": {
        "objectId": "shape_with_text",
        "shapeType": "TEXT_BOX",
        "elementProperties": {
          "pageObjectId": "slide_1",
          "size": {
            "width": {"magnitude": 4000000, "unit": "EMU"},
            "height": {"magnitude": 1500000, "unit": "EMU"}
          },
          "transform": {
            "scaleX": 1,
            "scaleY": 1,
            "translateX": 2500000,
            "translateY": 2000000,
            "unit": "EMU"
          }
        }
      }
    },
    {
      "insertText": {
        "objectId": "shape_with_text",
        "text": "Hello, World!"
      }
    },
    {
      "updateTextStyle": {
        "objectId": "shape_with_text",
        "textRange": {"type": "ALL"},
        "style": {
          "bold": true,
          "fontSize": {"magnitude": 24, "unit": "PT"}
        },
        "fields": "bold,fontSize"
      }
    }
  ]
}
```

## Response

```json
{
  "createShape": {
    "objectId": "my_textbox"
  }
}
```

## Size Reference

Common sizes in EMU (914,400 EMU = 1 inch):

| Size | EMU Value |
|------|-----------|
| 1 inch | 914,400 |
| 2 inches | 1,828,800 |
| 3 inches | 2,743,200 |
| 100 points | 1,270,000 |
| 200 points | 2,540,000 |

## Notes

- The shape is created with default styling
- Use `updateShapeProperties` to change fill, outline, etc.
- Use `insertText` to add text content
- Transform's `translateX`/`translateY` position the upper-left corner

## Related Requests

- [InsertTextRequest](./insert-text.md) - Add text to shape
- [UpdateShapePropertiesRequest](./update-shape-properties.md) - Style shape
- [UpdatePageElementTransformRequest](./update-transform.md) - Move/resize
- [DeleteObjectRequest](./delete-object.md) - Delete shape

## Related Documentation

- [Add Shape Guide](../../guides/add-shape.md) - Complete guide
- [Shape Object](../objects/shape.md) - Shape structure
