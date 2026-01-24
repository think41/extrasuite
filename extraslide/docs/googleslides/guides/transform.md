# Sizing and Positioning Page Elements

> **Source**: [Google Slides API - Transform Guide](https://developers.google.com/workspace/slides/api/guides/transform)

## Overview

The Google Slides API enables developers to reposition and scale page elements using affine transforms through the `UpdatePageElementTransformRequest`.

## UpdatePageElementTransformRequest

```json
{
  "updatePageElementTransform": {
    "objectId": "element_id",
    "transform": {
      "scaleX": 1,
      "scaleY": 1,
      "shearX": 0,
      "shearY": 0,
      "translateX": 100000,
      "translateY": 100000,
      "unit": "EMU"
    },
    "applyMode": "ABSOLUTE"
  }
}
```

## Apply Modes

### ABSOLUTE Mode

Transforms **replace** the element's existing transformation matrix.

```json
{
  "updatePageElementTransform": {
    "objectId": "shape_id",
    "transform": {
      "scaleX": 1,
      "scaleY": 1,
      "translateX": 500000,
      "translateY": 500000,
      "unit": "EMU"
    },
    "applyMode": "ABSOLUTE"
  }
}
```

**Use case**: Moving shapes to specific page locations.

**Note**: Omitted parameters default to zero, so you must include existing scale/shear values to preserve them.

### RELATIVE Mode

Transforms are **multiplied** with the element's existing transformation matrix.

```json
{
  "updatePageElementTransform": {
    "objectId": "shape_id",
    "transform": {
      "scaleX": 1,
      "scaleY": 1,
      "translateX": 100000,
      "translateY": 0,
      "unit": "EMU"
    },
    "applyMode": "RELATIVE"
  }
}
```

**Use case**: Incremental adjustments like "move 100 points left" or "rotate 40 degrees".

## Core Transform Operations

### Translation (Moving)

The translation matrix:
```
T = | 1  0  translateX |
    | 0  1  translateY |
    | 0  0  1          |
```

**Example: Move to position (1 inch, 2 inches)**

```json
{
  "updatePageElementTransform": {
    "objectId": "shape_id",
    "transform": {
      "scaleX": 1,
      "scaleY": 1,
      "translateX": 914400,
      "translateY": 1828800,
      "unit": "EMU"
    },
    "applyMode": "ABSOLUTE"
  }
}
```

**Important**: Translation parameters specify the position of the element's upper-left corner, not its center.

### Scaling (Resizing)

The scale matrix:
```
S = | scaleX  0       0 |
    | 0       scaleY  0 |
    | 0       0       1 |
```

**Example: Double the size**

```json
{
  "updatePageElementTransform": {
    "objectId": "shape_id",
    "transform": {
      "scaleX": 2,
      "scaleY": 2,
      "translateX": 0,
      "translateY": 0,
      "unit": "EMU"
    },
    "applyMode": "RELATIVE"
  }
}
```

### Rotation

The rotation matrix for angle θ (in radians):
```
R = | cos(θ)   sin(θ)  0 |
    | -sin(θ)  cos(θ)  0 |
    | 0        0       1 |
```

**Example: Rotate 45 degrees (π/4 radians)**

```json
{
  "updatePageElementTransform": {
    "objectId": "shape_id",
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

### Reflection (Flipping)

**Flip horizontally** (across Y-axis):
```json
{
  "scaleX": -1,
  "scaleY": 1
}
```

**Flip vertically** (across X-axis):
```json
{
  "scaleX": 1,
  "scaleY": -1
}
```

## Element Reference Frames

For operations requiring centering behavior (rotation around center, scaling from center), use reference frame translations:

```
A' = T₂ × B × T₁ × A
```

Where:
- **T₁**: Moves element center to page origin
- **B**: Applies the transformation
- **T₂**: Repositions the element

### Example: Rotate Around Center

1. Calculate element center from size and current transform
2. Create T₁ to translate center to origin
3. Apply rotation B
4. Create T₂ to move back
5. Multiply matrices: `result = T₂ × B × T₁`

## Compatibility Limitations

| Operation | Shapes | Video | Tables |
|-----------|--------|-------|--------|
| Translation | ✓ | ✓ | ✓ |
| Scale | ✓ | ✓ | ✗ |
| Shear | ✓ | ✗ | ✗ |

**For tables**: Use `UpdateTableRowPropertiesRequest` and `UpdateTableColumnPropertiesRequest` instead.

## Optimization

Precalculating transforms—combining multiple transformations using matrix multiplication—can reduce API overhead compared to sequential requests.

## Common Calculations

### Get Visual Position

```python
x = transform.translateX
y = transform.translateY
```

### Get Visual Size

```python
visual_width = (transform.scaleX * size.width) + (transform.shearX * size.height)
visual_height = (transform.scaleY * size.height) + (transform.shearY * size.width)
```

### Get Center Point

```python
center_x = transform.translateX + visual_width / 2
center_y = transform.translateY + visual_height / 2
```

## Important Notes

1. **Order matters**: Transform operations are not commutative
2. **Retrieve before update**: Use `presentations.pages.get()` to get current transforms
3. **Size may change**: You're not guaranteed the same size values after creation—the API may refactor values while maintaining visual appearance

## Related Documentation

- [Transforms Concept](../concepts/transforms.md) - Understanding transforms
- [Page Elements](../concepts/page-elements.md) - Element types
- [Add Shape](./add-shape.md) - Creating shapes
