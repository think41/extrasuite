# UnmergeTableCellsRequest

Unmerges cells in a Table.

## Schema

```json
{
  "unmergeTableCells": {
    "objectId": string,
    "tableRange": [TableRange]
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the table. |
| `tableRange` | [TableRange] | No | The table range specifying which cells of the table to unmerge. All merged cells in this range wi... |

## Example

```json
{
  "requests": [
    {
      "unmergeTableCells": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [TableRange](../objects/table-range.md)

