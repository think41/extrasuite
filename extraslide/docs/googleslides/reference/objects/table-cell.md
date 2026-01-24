# TableCell

Properties and contents of each table cell.

## Schema

```json
{
  "location": [TableCellLocation],
  "rowSpan": integer,
  "columnSpan": integer,
  "text": [TextContent],
  "tableCellProperties": [TableCellProperties]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `location` | [TableCellLocation] | The location of the cell within the table. |
| `rowSpan` | integer | Row span of the cell. |
| `columnSpan` | integer | Column span of the cell. |
| `text` | [TextContent] | The text content of the cell. |
| `tableCellProperties` | [TableCellProperties] | The properties of the table cell. |

## Related Objects

- [TableCellLocation](./table-cell-location.md)
- [TableCellProperties](./table-cell-properties.md)
- [TextContent](./text-content.md)

