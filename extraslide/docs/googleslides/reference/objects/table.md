# Table

A PageElement kind representing a table.

## Schema

```json
{
  "rows": integer,
  "columns": integer,
  "tableRows": array of [TableRow],
  "tableColumns": array of [TableColumnProperties],
  "horizontalBorderRows": array of [TableBorderRow],
  "verticalBorderRows": array of [TableBorderRow]
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `rows` | integer | Number of rows in the table. |
| `columns` | integer | Number of columns in the table. |
| `tableRows` | array of [TableRow] | Properties and contents of each row. Cells that span multiple rows are contained in only one of t... |
| `tableColumns` | array of [TableColumnProperties] | Properties of each column. |
| `horizontalBorderRows` | array of [TableBorderRow] | Properties of horizontal cell borders. A table's horizontal cell borders are represented as a gri... |
| `verticalBorderRows` | array of [TableBorderRow] | Properties of vertical cell borders. A table's vertical cell borders are represented as a grid. T... |

## Related Objects

- [TableBorderRow](./table-border-row.md)
- [TableColumnProperties](./table-column-properties.md)
- [TableRow](./table-row.md)

