# UpdatePageElementTransformRequest

Updates the transform of a page element to change its position, size, or rotation.

## Schema

```json
{
  "updatePageElementTransform": {
    "objectId": "string",
    "transform": AffineTransform,
    "applyMode": "ABSOLUTE | RELATIVE"
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | Yes | ID of the element to transform |
| `transform` | AffineTransform | Yes | The transform to apply |
| `applyMode` | enum | Yes | How to apply the transform |

## Apply Modes

| Mode | Description |
|------|-------------|
| `ABSOLUTE` | Replaces the existing transform |
| `RELATIVE` | Multiplies with existing transform |

## AffineTransform

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

## Examples

### Move to Absolute Position

```json
{
  "updatePageElementTransform": {
    "objectId": "my_shape",
    "transform": {
      "scaleX": 1,
      "scaleY": 1,
      "shearX": 0,
      "shearY": 0,
      "translateX": 914400,
      "translateY": 914400,
      "unit": "EMU"
    },
    "applyMode": "ABSOLUTE"
  }
}
```

Moves element to position (1 inch, 1 inch).

**Note**: With ABSOLUTE mode, you must include scale values or they default to 0.

### Move Relatively

```json
{
  "updatePageElementTransform": {
    "objectId": "my_shape",
    "transform": {
      "scaleX": 1,
      "scaleY": 1,
      "shearX": 0,
      "shearY": 0,
      "translateX": 457200,
      "translateY": 0,
      "unit": "EMU"
    },
    "applyMode": "RELATIVE"
  }
}
```

Moves element 0.5 inches to the right.

### Scale to 2x Size

```json
{
  "updatePageElementTransform": {
    "objectId": "my_shape",
    "transform": {
      "scaleX": 2,
      "scaleY": 2,
      "shearX": 0,
      "shearY": 0,
      "translateX": 0,
      "translateY": 0,
      "unit": "EMU"
    },
    "applyMode": "RELATIVE"
  }
}
```

### Rotate 45 Degrees

```json
{
  "updatePageElementTransform": {
    "objectId": "my_shape",
    "transform": {
      "scaleX": 0.7071067811865476,
      "scaleY": 0.7071067811865476,
      "shearX": 0.7071067811865476,
      "shearY": -0.7071067811865476,
      "translateX": 0,
      "translateY": 0,
      "unit": "EMU"
    },
    "applyMode": "RELATIVE"
  }
}
```

### Horizontal Flip

```json
{
  "updatePageElementTransform": {
    "objectId": "my_shape",
    "transform": {
      "scaleX": -1,
      "scaleY": 1,
      "shearX": 0,
      "shearY": 0,
      "translateX": 0,
      "translateY": 0,
      "unit": "EMU"
    },
    "applyMode": "RELATIVE"
  }
}
```

### Preserve Position While Scaling

To scale from center, first calculate center offset:

```python
import math

def scale_from_center(element, scale_factor):
    size = element['size']
    transform = element['transform']

    # Current center
    width = size['width']['magnitude'] * transform['scaleX']
    height = size['height']['magnitude'] * transform['scaleY']
    center_x = transform['translateX'] + width / 2
    center_y = transform['translateY'] + height / 2

    # New dimensions
    new_width = width * scale_factor
    new_height = height * scale_factor

    # New position (keeping center)
    new_x = center_x - new_width / 2
    new_y = center_y - new_height / 2

    return {
        'scaleX': transform['scaleX'] * scale_factor,
        'scaleY': transform['scaleY'] * scale_factor,
        'shearX': transform.get('shearX', 0),
        'shearY': transform.get('shearY', 0),
        'translateX': new_x,
        'translateY': new_y,
        'unit': 'EMU'
    }
```

## Response

Empty response: `{}`

## Compatibility

| Element Type | Translation | Scale | Shear |
|--------------|-------------|-------|-------|
| Shape | ✓ | ✓ | ✓ |
| Image | ✓ | ✓ | ✓ |
| Video | ✓ | ✓ | ✗ |
| Table | ✓ | ✗ | ✗ |
| Line | ✓ | ✓ | ✓ |
| Group | ✓ | ✓ | ✓ |

For tables, use:
- `UpdateTableRowPropertiesRequest` for row heights
- `UpdateTableColumnPropertiesRequest` for column widths

## Common Issues

### ABSOLUTE Mode Pitfalls

With ABSOLUTE mode, omitted values default to 0:

```json
// WRONG - element disappears (scale = 0)
{
  "transform": {
    "translateX": 500000,
    "translateY": 500000,
    "unit": "EMU"
  },
  "applyMode": "ABSOLUTE"
}

// CORRECT
{
  "transform": {
    "scaleX": 1,
    "scaleY": 1,
    "translateX": 500000,
    "translateY": 500000,
    "unit": "EMU"
  },
  "applyMode": "ABSOLUTE"
}
```

### Rotation Around Page Origin

Direct rotation rotates around page origin (0,0), not element center. Use reference frame transformations for center rotation.

## Related Requests

- [CreateShapeRequest](./create-shape.md) - Initial positioning
- [UpdateShapePropertiesRequest](./update-shape-properties.md) - Visual properties

## Related Documentation

- [AffineTransform Object](../objects/affine-transform.md) - Transform details
- [Transform Guide](../../guides/transform.md) - Practical examples
- [Transforms Concept](../../concepts/transforms.md) - Theory
