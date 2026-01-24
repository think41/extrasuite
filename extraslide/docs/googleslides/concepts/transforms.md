# Transforms

> **Source**: [Google Slides API - Transforms](https://developers.google.com/workspace/slides/api/concepts/transforms)

## Core Concepts

The visual appearance of page elements in Google Slides is controlled by two properties:
- **Size**: The built-in dimensions of the element
- **Transform**: A 2D affine transform matrix that specifies how an element at its built-in size is transformed to result in its final visual appearance

## Affine Transform Matrix

Page elements use a 3×3 affine transformation matrix:

```
A = | scaleX    shearX    translateX |
    | shearY    scaleY    translateY |
    | 0         0         1          |
```

### Matrix Parameters

| Parameter | Description |
|-----------|-------------|
| `translateX` | X position of upper-left corner relative to page origin (in EMU) |
| `translateY` | Y position of upper-left corner relative to page origin (in EMU) |
| `scaleX` | Horizontal scaling factor (unitless, e.g., 1.5 = 50% enlargement) |
| `scaleY` | Vertical scaling factor (unitless) |
| `shearX` | Horizontal tilt factor (unitless) |
| `shearY` | Vertical tilt factor (unitless) |

### JSON Representation

```json
{
  "transform": {
    "scaleX": 1.5,
    "scaleY": 1.5,
    "shearX": 0,
    "shearY": 0,
    "translateX": 100000,
    "translateY": 200000,
    "unit": "EMU"
  }
}
```

## Point Mapping Calculation

To map a point (x, y) through the transform matrix:

```
x' = (scaleX × x) + (shearX × y) + translateX
y' = (scaleY × y) + (shearY × x) + translateY
```

## Visual Size Calculation

Rendered dimensions accounting for transforms:

```
width'  = (scaleX × width) + (shearX × height)
height' = (scaleY × height) + (shearY × width)
```

### Example

For an element with:
- Built-in size: 100 × 50 EMU
- Transform: scaleX=2, scaleY=1.5, shearX=0, shearY=0

Visual size:
- width' = (2 × 100) + (0 × 50) = 200 EMU
- height' = (1.5 × 50) + (0 × 100) = 75 EMU

## Units

The Google Slides API uses **EMU (English Metric Units)**:
- 1 inch = 914400 EMU
- 1 point = 12700 EMU
- 1 pixel (at 96 DPI) ≈ 9525 EMU

## Practical Approach

The documentation recommends:

> Create page elements using the Slides UI. Position and scale these page elements as desired, still using the Slides UI. Read the size and transform of those elements using the get method.

This helps understand how transforms work in practice.

## Transform Compatibility

| Operation | Shapes | Video | Tables |
|-----------|--------|-------|--------|
| Translation | ✓ | ✓ | ✓ |
| Scale | ✓ | ✓ | ✗* |
| Shear | ✓ | ✗ | ✗ |

*For tables, use `UpdateTableRowPropertiesRequest` and `UpdateTableColumnPropertiesRequest` instead.

## Key Principles

1. **Relative to container**: The transform matrix is relative to the containing group or page—rotating a group doesn't modify child elements' transform values, only the group's own matrix.

2. **Upper-left corner**: Translation parameters specify the position of the element's upper-left corner, not its center.

3. **Order matters**: Matrix multiplication is not commutative—the order of operations affects the result.

## Common Transform Matrices

### Identity (No Transform)
```json
{
  "scaleX": 1, "scaleY": 1,
  "shearX": 0, "shearY": 0,
  "translateX": 0, "translateY": 0
}
```

### Translation Only
```json
{
  "scaleX": 1, "scaleY": 1,
  "shearX": 0, "shearY": 0,
  "translateX": 1000000, "translateY": 500000
}
```

### Scale 2x
```json
{
  "scaleX": 2, "scaleY": 2,
  "shearX": 0, "shearY": 0,
  "translateX": 0, "translateY": 0
}
```

### 45-Degree Rotation
For rotation by angle θ:
- scaleX = cos(θ)
- scaleY = cos(θ)
- shearX = sin(θ)
- shearY = -sin(θ)

```json
{
  "scaleX": 0.707,
  "scaleY": 0.707,
  "shearX": 0.707,
  "shearY": -0.707,
  "translateX": 0,
  "translateY": 0
}
```

## Related Documentation

- [Page Elements](./page-elements.md) - Understanding element types
- [Transform Guide](../guides/transform.md) - Practical transform operations
- [Add Shape Guide](../guides/add-shape.md) - Creating positioned shapes
