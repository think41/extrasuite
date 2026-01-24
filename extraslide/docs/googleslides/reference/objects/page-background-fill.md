# PageBackgroundFill

The page background fill.

## Schema

```json
{
  "propertyState": string,
  "solidFill": [SolidFill],
  "stretchedPictureFill": [StretchedPictureFill]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `propertyState` | string | The background fill property state. Updating the fill on a page will implicitly update this field... |
| `solidFill` | [SolidFill] | Solid color fill. |
| `stretchedPictureFill` | [StretchedPictureFill] | Stretched picture fill. |

### propertyState Values

| Value | Description |
|-------|-------------|
| `RENDERED` | If a property's state is RENDERED, then the element has the corresponding property when rendered ... |
| `NOT_RENDERED` | If a property's state is NOT_RENDERED, then the element does not have the corresponding property ... |
| `INHERIT` | If a property's state is INHERIT, then the property state uses the value of corresponding `proper... |

## Related Objects

- [SolidFill](./solid-fill.md)
- [StretchedPictureFill](./stretched-picture-fill.md)

