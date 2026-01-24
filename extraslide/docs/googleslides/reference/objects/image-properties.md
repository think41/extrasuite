# ImageProperties

The properties of the Image.

## Schema

```json
{
  "cropProperties": [CropProperties],
  "transparency": number,
  "brightness": number,
  "contrast": number,
  "recolor": [Recolor],
  "outline": [Outline],
  "shadow": [Shadow],
  "link": [Link]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `cropProperties` | [CropProperties] | The crop properties of the image. If not set, the image is not cropped. This property is read-only. |
| `transparency` | number | The transparency effect of the image. The value should be in the interval [0.0, 1.0], where 0 mea... |
| `brightness` | number | The brightness effect of the image. The value should be in the interval [-1.0, 1.0], where 0 mean... |
| `contrast` | number | The contrast effect of the image. The value should be in the interval [-1.0, 1.0], where 0 means ... |
| `recolor` | [Recolor] | The recolor effect of the image. If not set, the image is not recolored. This property is read-only. |
| `outline` | [Outline] | The outline of the image. If not set, the image has no outline. |
| `shadow` | [Shadow] | The shadow of the image. If not set, the image has no shadow. This property is read-only. |
| `link` | [Link] | The hyperlink destination of the image. If unset, there is no link. |

## Related Objects

- [CropProperties](./crop-properties.md)
- [Link](./link.md)
- [Outline](./outline.md)
- [Recolor](./recolor.md)
- [Shadow](./shadow.md)

