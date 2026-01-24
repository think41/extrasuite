# DeleteTableRowRequest

Deletes a row from a table.

## Schema

```json
{
  "deleteTableRow": {
    "tableObjectId": string,
    "cellLocation": [TableCellLocation]
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `tableObjectId` | string | No | The table to delete rows from. |
| `cellLocation` | [TableCellLocation] | No | The reference table cell location from which a row will be deleted. The row this cell spans will ... |

## Example

```json
{
  "requests": [
    {
      "deleteTableRow": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [TableCellLocation](../objects/table-cell-location.md)

