# TableCellProperties

The properties of the TableCell.

## Schema

```json
{
  "tableCellBackgroundFill": [TableCellBackgroundFill],
  "contentAlignment": string
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `tableCellBackgroundFill` | [TableCellBackgroundFill] | The background fill of the table cell. The default fill matches the fill for newly created table ... |
| `contentAlignment` | string | The alignment of the content in the table cell. The default alignment matches the alignment for n... |

### contentAlignment Values

| Value | Description |
|-------|-------------|
| `CONTENT_ALIGNMENT_UNSPECIFIED` | An unspecified content alignment. The content alignment is inherited from the parent if it exists. |
| `CONTENT_ALIGNMENT_UNSUPPORTED` | An unsupported content alignment. |
| `TOP` | An alignment that aligns the content to the top of the content holder. Corresponds to ECMA-376 ST... |
| `MIDDLE` | An alignment that aligns the content to the middle of the content holder. Corresponds to ECMA-376... |
| `BOTTOM` | An alignment that aligns the content to the bottom of the content holder. Corresponds to ECMA-376... |

## Related Objects

- [TableCellBackgroundFill](./table-cell-background-fill.md)

