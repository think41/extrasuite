# Shadow

The shadow properties of a page element. If these fields are unset, they may be inherited from a parent placeholder if it exists. If there is no parent, the fields will default to the value used for new page elements created in the Slides editor, which may depend on the page element kind.

## Schema

```json
{
  "type": string,
  "transform": [AffineTransform],
  "alignment": string,
  "blurRadius": [Dimension],
  "color": [OpaqueColor],
  "alpha": number,
  "rotateWithShape": boolean,
  "propertyState": string
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `type` | string | The type of the shadow. This property is read-only. |
| `transform` | [AffineTransform] | Transform that encodes the translate, scale, and skew of the shadow, relative to the alignment po... |
| `alignment` | string | The alignment point of the shadow, that sets the origin for translate, scale and skew of the shad... |
| `blurRadius` | [Dimension] | The radius of the shadow blur. The larger the radius, the more diffuse the shadow becomes. |
| `color` | [OpaqueColor] | The shadow color value. |
| `alpha` | number | The alpha of the shadow's color, from 0.0 to 1.0. |
| `rotateWithShape` | boolean | Whether the shadow should rotate with the shape. This property is read-only. |
| `propertyState` | string | The shadow property state. Updating the shadow on a page element will implicitly update this fiel... |

### type Values

| Value | Description |
|-------|-------------|
| `SHADOW_TYPE_UNSPECIFIED` | Unspecified shadow type. |
| `OUTER` | Outer shadow. |

### alignment Values

| Value | Description |
|-------|-------------|
| `RECTANGLE_POSITION_UNSPECIFIED` | Unspecified. |
| `TOP_LEFT` | Top left. |
| `TOP_CENTER` | Top center. |
| `TOP_RIGHT` | Top right. |
| `LEFT_CENTER` | Left center. |
| `CENTER` | Center. |
| `RIGHT_CENTER` | Right center. |
| `BOTTOM_LEFT` | Bottom left. |
| `BOTTOM_CENTER` | Bottom center. |
| `BOTTOM_RIGHT` | Bottom right. |

### propertyState Values

| Value | Description |
|-------|-------------|
| `RENDERED` | If a property's state is RENDERED, then the element has the corresponding property when rendered ... |
| `NOT_RENDERED` | If a property's state is NOT_RENDERED, then the element does not have the corresponding property ... |
| `INHERIT` | If a property's state is INHERIT, then the property state uses the value of corresponding `proper... |

## Related Objects

- [AffineTransform](./affine-transform.md)
- [Dimension](./dimension.md)
- [OpaqueColor](./opaque-color.md)

