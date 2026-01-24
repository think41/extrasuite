# SolidFill

A solid color fill. The page or page element is filled entirely with the specified color value. If any field is unset, its value may be inherited from a parent placeholder if it exists.

## Schema

```json
{
  "color": [OpaqueColor],
  "alpha": number
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `color` | [OpaqueColor] | The color value of the solid fill. |
| `alpha` | number | The fraction of this `color` that should be applied to the pixel. That is, the final pixel color ... |

## Related Objects

- [OpaqueColor](./opaque-color.md)

