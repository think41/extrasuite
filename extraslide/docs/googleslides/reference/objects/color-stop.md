# ColorStop

A color and position in a gradient band.

## Schema

```json
{
  "color": [OpaqueColor],
  "alpha": number,
  "position": number
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `color` | [OpaqueColor] | The color of the gradient stop. |
| `alpha` | number | The alpha value of this color in the gradient band. Defaults to 1.0, fully opaque. |
| `position` | number | The relative position of the color stop in the gradient band measured in percentage. The value sh... |

## Related Objects

- [OpaqueColor](./opaque-color.md)

