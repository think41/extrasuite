# MergeTableCellsRequest

Merges cells in a Table.

## Schema

```json
{
  "mergeTableCells": {
    "objectId": string,
    "tableRange": [TableRange]
  }
}
```

## Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `objectId` | string | No | The object ID of the table. |
| `tableRange` | [TableRange] | No | The table range specifying which cells of the table to merge. Any text in the cells being merged ... |

## Example

```json
{
  "requests": [
    {
      "mergeTableCells": {
        // Properties here
      }
    }
  ]
}
```

## Related Objects

- [TableRange](../objects/table-range.md)

