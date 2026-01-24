# TableRow

Properties and contents of each row in a table.

## Schema

```json
{
  "rowHeight": [Dimension],
  "tableRowProperties": [TableRowProperties],
  "tableCells": array of [TableCell]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `rowHeight` | [Dimension] | Height of a row. |
| `tableRowProperties` | [TableRowProperties] | Properties of the row. |
| `tableCells` | array of [TableCell] | Properties and contents of each cell. Cells that span multiple columns are represented only once ... |

## Related Objects

- [Dimension](./dimension.md)
- [TableCell](./table-cell.md)
- [TableRowProperties](./table-row-properties.md)

