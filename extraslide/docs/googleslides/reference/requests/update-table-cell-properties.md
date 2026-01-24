# UpdateTableCellPropertiesRequest

Update the properties of a TableCell.

## Schema

```json
{
  "updateTableCellProperties": {
    "objectId": string,
    "tableRange": [TableRange],
    "tableCellProperties": [TableCellProperties],
    "fields": string
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the table. |
| `tableRange` | [TableRange] | No | The table range representing the subset of the table to which the updates are applied. If a table... |
| `tableCellProperties` | [TableCellProperties] | No | The table cell properties to update. |
| `fields` | string | No | The fields that should be updated. At least one field must be specified. The root `tableCellPrope... |

## Example

```json
{
  "requests": [
    {
      "updateTableCellProperties": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [TableCellProperties](../objects/table-cell-properties.md)
- [TableRange](../objects/table-range.md)

