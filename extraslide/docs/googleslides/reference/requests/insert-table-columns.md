# InsertTableColumnsRequest

Inserts columns into a table. Other columns in the table will be resized to fit the new column.

## Schema

```json
{
  "insertTableColumns": {
    "tableObjectId": string,
    "cellLocation": [TableCellLocation],
    "insertRight": boolean,
    "number": integer
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `tableObjectId` | string | No | The table to insert columns into. |
| `cellLocation` | [TableCellLocation] | No | The reference table cell location from which columns will be inserted. A new column will be inser... |
| `insertRight` | boolean | No | Whether to insert new columns to the right of the reference cell location. - `True`: insert to th... |
| `number` | integer | No | The number of columns to be inserted. Maximum 20 per request. |

## Example

```json
{
  "requests": [
    {
      "insertTableColumns": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [TableCellLocation](../objects/table-cell-location.md)

