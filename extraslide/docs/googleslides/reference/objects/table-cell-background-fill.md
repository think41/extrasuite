# TableCellBackgroundFill

The table cell background fill.

## Schema

```json
{
  "propertyState": string,
  "solidFill": [SolidFill]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `propertyState` | string | The background fill property state. Updating the fill on a table cell will implicitly update this... |
| `solidFill` | [SolidFill] | Solid color fill. |

### propertyState Values

| Value | Description |
|-------|-------------|
| `RENDERED` | If a property's state is RENDERED, then the element has the corresponding property when rendered ... |
| `NOT_RENDERED` | If a property's state is NOT_RENDERED, then the element does not have the corresponding property ... |
| `INHERIT` | If a property's state is INHERIT, then the property state uses the value of corresponding `proper... |

## Related Objects

- [SolidFill](./solid-fill.md)

