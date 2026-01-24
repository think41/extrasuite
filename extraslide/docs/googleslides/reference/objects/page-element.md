# PageElement

A visual element rendered on a page.

## Schema

```json
{
  "objectId": "string",
  "size": Size,
  "transform": AffineTransform,
  "title": "string",
  "description": "string",
  "shape": Shape,
  "image": Image,
  "video": Video,
  "line": Line,
  "table": Table,
  "wordArt": WordArt,
  "sheetsChart": SheetsChart,
  "elementGroup": Group,
  "speakerSpotlight": SpeakerSpotlight
}
```

## Common Properties

| Property | Type | Description |
|----------|------|-------------|
| `objectId` | string | Unique identifier for the element |
| `size` | [Size](./size.md) | Built-in dimensions |
| `transform` | [AffineTransform](./affine-transform.md) | Transformation matrix |
| `title` | string | Accessibility title |
| `description` | string | Accessibility description |

## Element Type Properties

Only one of these is present, indicating the element type:

| Property | Type | Description |
|----------|------|-------------|
| `shape` | [Shape](./shape.md) | Generic shape including text boxes |
| `image` | [Image](./image.md) | Image element |
| `video` | Video | Video element |
| `line` | [Line](./line.md) | Line or connector |
| `table` | [Table](./table.md) | Table element |
| `wordArt` | WordArt | WordArt text |
| `sheetsChart` | SheetsChart | Embedded Google Sheets chart |
| `elementGroup` | Group | Group of elements |
| `speakerSpotlight` | SpeakerSpotlight | Speaker spotlight element |

## Size

```json
{
  "size": {
    "width": {"magnitude": 3000000, "unit": "EMU"},
    "height": {"magnitude": 3000000, "unit": "EMU"}
  }
}
```

See [Size](./size.md) for details.

## Transform

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

See [AffineTransform](./affine-transform.md) for details.

## Visual Size Calculation

The rendered size is calculated from size and transform:

```python
visual_width = (transform.scaleX * size.width) + (transform.shearX * size.height)
visual_height = (transform.scaleY * size.height) + (transform.shearY * size.width)
```

## Examples

### Shape Element

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
    "shearX": 0,
    "shearY": 0,
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
          "paragraphMarker": {...}
        },
        {
          "startIndex": 0,
          "endIndex": 11,
          "textRun": {
            "content": "Hello World",
            "style": {...}
          }
        }
      ]
    },
    "shapeProperties": {...}
  }
}
```

### Image Element

```json
{
  "objectId": "g123_image1",
  "size": {
    "width": {"magnitude": 4000000, "unit": "EMU"},
    "height": {"magnitude": 3000000, "unit": "EMU"}
  },
  "transform": {
    "scaleX": 1,
    "scaleY": 1,
    "translateX": 500000,
    "translateY": 500000,
    "unit": "EMU"
  },
  "image": {
    "contentUrl": "https://...",
    "sourceUrl": "https://example.com/image.png",
    "imageProperties": {
      "transparency": 0,
      "brightness": 0,
      "contrast": 0
    }
  }
}
```

### Table Element

```json
{
  "objectId": "g123_table1",
  "size": {
    "width": {"magnitude": 6000000, "unit": "EMU"},
    "height": {"magnitude": 2000000, "unit": "EMU"}
  },
  "transform": {
    "scaleX": 1,
    "scaleY": 1,
    "translateX": 1500000,
    "translateY": 2000000,
    "unit": "EMU"
  },
  "table": {
    "rows": 3,
    "columns": 4,
    "tableRows": [...],
    "tableColumns": [...]
  }
}
```

## Determining Element Type

```python
def get_element_type(element):
    if 'shape' in element:
        return 'shape'
    elif 'image' in element:
        return 'image'
    elif 'table' in element:
        return 'table'
    elif 'line' in element:
        return 'line'
    elif 'video' in element:
        return 'video'
    elif 'sheetsChart' in element:
        return 'sheetsChart'
    elif 'elementGroup' in element:
        return 'group'
    elif 'wordArt' in element:
        return 'wordArt'
    return 'unknown'
```

## Processing Elements

```python
for slide in presentation.get('slides', []):
    for element in slide.get('pageElements', []):
        element_id = element['objectId']
        element_type = get_element_type(element)

        # Get position
        transform = element.get('transform', {})
        x = transform.get('translateX', 0)
        y = transform.get('translateY', 0)

        # Get size
        size = element.get('size', {})
        width = size.get('width', {}).get('magnitude', 0)
        height = size.get('height', {}).get('magnitude', 0)

        # Process based on type
        if element_type == 'shape':
            shape = element['shape']
            text = shape.get('text', {})
            # Process shape
```

## Related Objects

- [Shape](./shape.md) - Shape element details
- [Image](./image.md) - Image element details
- [Table](./table.md) - Table element details
- [Line](./line.md) - Line element details
- [AffineTransform](./affine-transform.md) - Transform matrix
- [Size](./size.md) - Dimensions

## Related Documentation

- [Page Elements Concept](../../concepts/page-elements.md) - Overview
- [Transforms Concept](../../concepts/transforms.md) - Understanding transforms
