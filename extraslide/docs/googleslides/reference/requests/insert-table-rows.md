# InsertTableRowsRequest

Inserts rows into a table.

## Schema

```json
{
  "insertTableRows": {
    "tableObjectId": string,
    "cellLocation": [TableCellLocation],
    "insertBelow": boolean,
    "number": integer
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `tableObjectId` | string | No | The table to insert rows into. |
| `cellLocation` | [TableCellLocation] | No | The reference table cell location from which rows will be inserted. A new row will be inserted ab... |
| `insertBelow` | boolean | No | Whether to insert new rows below the reference cell location. - `True`: insert below the cell. - ... |
| `number` | integer | No | The number of rows to be inserted. Maximum 20 per request. |

## Example

```json
{
  "requests": [
    {
      "insertTableRows": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [TableCellLocation](../objects/table-cell-location.md)

