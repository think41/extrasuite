# AffineTransform

A 2D affine transformation matrix for positioning, scaling, and rotating elements.

## Schema

```json
{
  "scaleX": number,
  "scaleY": number,
  "shearX": number,
  "shearY": number,
  "translateX": number,
  "translateY": number,
  "unit": "EMU | PT"
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `scaleX` | double | X coordinate scaling factor |
| `scaleY` | double | Y coordinate scaling factor |
| `shearX` | double | X coordinate shearing factor |
| `shearY` | double | Y coordinate shearing factor |
| `translateX` | double | X coordinate translation |
| `translateY` | double | Y coordinate translation |
| `unit` | enum | Unit for translation values |

## Units

| Unit | Description | Per Inch |
|------|-------------|----------|
| `EMU` | English Metric Units | 914,400 |
| `PT` | Points | 72 |

### Conversion Formulas

```python
# EMU to inches
inches = emu / 914400

# Inches to EMU
emu = inches * 914400

# Points to EMU
emu = points * 12700

# EMU to points
points = emu / 12700

# Pixels (96 DPI) to EMU
emu = pixels * 9525
```

## Matrix Representation

The transform is a 3x3 matrix:

```
| scaleX    shearX    translateX |
| shearY    scaleY    translateY |
| 0         0         1          |
```

## Point Transformation

To transform point (x, y):

```
x' = scaleX * x + shearX * y + translateX
y' = shearY * x + scaleY * y + translateY
```

## Common Transforms

### Identity (No Transform)

```json
{
  "scaleX": 1,
  "scaleY": 1,
  "shearX": 0,
  "shearY": 0,
  "translateX": 0,
  "translateY": 0,
  "unit": "EMU"
}
```

### Translation Only

Move to position (1 inch, 2 inches):

```json
{
  "scaleX": 1,
  "scaleY": 1,
  "shearX": 0,
  "shearY": 0,
  "translateX": 914400,
  "translateY": 1828800,
  "unit": "EMU"
}
```

### Scale 2x

```json
{
  "scaleX": 2,
  "scaleY": 2,
  "shearX": 0,
  "shearY": 0,
  "translateX": 0,
  "translateY": 0,
  "unit": "EMU"
}
```

### Rotation

Rotate by angle θ (radians):

```json
{
  "scaleX": cos(θ),
  "scaleY": cos(θ),
  "shearX": sin(θ),
  "shearY": -sin(θ),
  "translateX": 0,
  "translateY": 0,
  "unit": "EMU"
}
```

Common rotations:

| Angle | cos(θ) | sin(θ) |
|-------|--------|--------|
| 45° | 0.7071 | 0.7071 |
| 90° | 0 | 1 |
| 180° | -1 | 0 |
| 270° | 0 | -1 |

### Horizontal Flip

```json
{
  "scaleX": -1,
  "scaleY": 1,
  "shearX": 0,
  "shearY": 0,
  "translateX": 0,
  "translateY": 0,
  "unit": "EMU"
}
```

### Vertical Flip

```json
{
  "scaleX": 1,
  "scaleY": -1,
  "shearX": 0,
  "shearY": 0,
  "translateX": 0,
  "translateY": 0,
  "unit": "EMU"
}
```

## Visual Size Calculation

Given element size and transform:

```python
def calculate_visual_size(size, transform):
    width = size['width']['magnitude']
    height = size['height']['magnitude']

    visual_width = abs(transform['scaleX'] * width + transform['shearX'] * height)
    visual_height = abs(transform['scaleY'] * height + transform['shearY'] * width)

    return visual_width, visual_height
```

## Position Calculation

The transform's translate values represent the upper-left corner position:

```python
def get_position(transform):
    return {
        'x': transform['translateX'],
        'y': transform['translateY']
    }

def get_center(size, transform):
    visual_width, visual_height = calculate_visual_size(size, transform)
    return {
        'x': transform['translateX'] + visual_width / 2,
        'y': transform['translateY'] + visual_height / 2
    }
```

## Updating Transform

### Absolute Mode

Replaces the entire transform:

```json
{
  "updatePageElementTransform": {
    "objectId": "element_id",
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

### Relative Mode

Multiplies with existing transform:

```json
{
  "updatePageElementTransform": {
    "objectId": "element_id",
    "transform": {
      "scaleX": 1.5,
      "scaleY": 1.5,
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

## Matrix Multiplication

For combining transforms (relative mode):

```python
def multiply_transforms(a, b):
    return {
        'scaleX': a['scaleX'] * b['scaleX'] + a['shearX'] * b['shearY'],
        'shearX': a['scaleX'] * b['shearX'] + a['shearX'] * b['scaleY'],
        'translateX': a['scaleX'] * b['translateX'] + a['shearX'] * b['translateY'] + a['translateX'],
        'shearY': a['shearY'] * b['scaleX'] + a['scaleY'] * b['shearY'],
        'scaleY': a['shearY'] * b['shearX'] + a['scaleY'] * b['scaleY'],
        'translateY': a['shearY'] * b['translateX'] + a['scaleY'] * b['translateY'] + a['translateY'],
        'unit': 'EMU'
    }
```

## Related Objects

- [Size](./size.md) - Element dimensions
- [PageElement](./page-element.md) - Elements using transforms

## Related Documentation

- [Transforms Concept](../../concepts/transforms.md) - Conceptual overview
- [Transform Guide](../../guides/transform.md) - Practical usage
