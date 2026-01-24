# UpdateTableBorderPropertiesRequest

Updates the properties of the table borders in a Table.

## Schema

```json
{
  "updateTableBorderProperties": {
    "objectId": string,
    "tableRange": [TableRange],
    "borderPosition": string,
    "tableBorderProperties": [TableBorderProperties],
    "fields": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the table. |
| `tableRange` | [TableRange] | No | The table range representing the subset of the table to which the updates are applied. If a table... |
| `borderPosition` | string | No | The border position in the table range the updates should apply to. If a border position is not s... |
| `tableBorderProperties` | [TableBorderProperties] | No | The table border properties to update. |
| `fields` | string | No | The fields that should be updated. At least one field must be specified. The root `tableBorderPro... |

### borderPosition Values

| Value | Description |
|-------|-------------|
| `ALL` | All borders in the range. |
| `BOTTOM` | Borders at the bottom of the range. |
| `INNER` | Borders on the inside of the range. |
| `INNER_HORIZONTAL` | Horizontal borders on the inside of the range. |
| `INNER_VERTICAL` | Vertical borders on the inside of the range. |
| `LEFT` | Borders at the left of the range. |
| `OUTER` | Borders along the outside of the range. |
| `RIGHT` | Borders at the right of the range. |
| `TOP` | Borders at the top of the range. |

## Example

```json
{
  "requests": [
    {
      "updateTableBorderProperties": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [TableBorderProperties](../objects/table-border-properties.md)
- [TableRange](../objects/table-range.md)

