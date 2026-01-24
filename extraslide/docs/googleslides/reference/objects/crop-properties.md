# CropProperties

The crop properties of an object enclosed in a container. For example, an Image. The crop properties is represented by the offsets of four edges which define a crop rectangle. The offsets are measured in percentage from the corresponding edges of the object's original bounding rectangle towards inside, relative to the object's original dimensions. - If the offset is in the interval (0, 1), the corresponding edge of crop rectangle is positioned inside of the object's original bounding rectangle. - If the offset is negative or greater than 1, the corresponding edge of crop rectangle is positioned outside of the object's original bounding rectangle. - If the left edge of the crop rectangle is on the right side of its right edge, the object will be flipped horizontally. - If the top edge of the crop rectangle is below its bottom edge, the object will be flipped vertically. - If all offsets and rotation angle is 0, the object is not cropped. After cropping, the content in the crop rectangle will be stretched to fit its container.

## Schema

```json
{
  "leftOffset": number,
  "rightOffset": number,
  "topOffset": number,
  "bottomOffset": number,
  "angle": number
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `leftOffset` | number | The offset specifies the left edge of the crop rectangle that is located to the right of the orig... |
| `rightOffset` | number | The offset specifies the right edge of the crop rectangle that is located to the left of the orig... |
| `topOffset` | number | The offset specifies the top edge of the crop rectangle that is located below the original boundi... |
| `bottomOffset` | number | The offset specifies the bottom edge of the crop rectangle that is located above the original bou... |
| `angle` | number | The rotation angle of the crop window around its center, in radians. Rotation angle is applied af... |

