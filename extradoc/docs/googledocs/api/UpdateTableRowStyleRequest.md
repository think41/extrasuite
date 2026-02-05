# UpdateTableRowStyleRequest

Updates the TableRowStyle of rows in a table.

**Type:** object

## Properties

- **tableStartLocation** ([Location](location.md)): The location where the table starts in the document.
- **rowIndices** (array of integer): The list of zero-based row indices whose style should be updated. If no indices are specified, all rows will be updated.
- **tableRowStyle** ([TableRowStyle](tablerowstyle.md)): The styles to be set on the rows.
- **fields** (string): The fields that should be updated. At least one field must be specified. The root `tableRowStyle` is implied and should not be specified. A single `"*"` can be used as short-hand for listing every field. For example to update the minimum row height, set `fields` to `"min_row_height"`.
