# DeleteTableColumnRequest

Deletes a column from a table.

## Schema

```json
{
  "deleteTableColumn": {
    "tableObjectId": string,
    "cellLocation": [TableCellLocation]
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `tableObjectId` | string | No | The table to delete columns from. |
| `cellLocation` | [TableCellLocation] | No | The reference table cell location from which a column will be deleted. The column this cell spans... |

## Example

```json
{
  "requests": [
    {
      "deleteTableColumn": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [TableCellLocation](../objects/table-cell-location.md)

