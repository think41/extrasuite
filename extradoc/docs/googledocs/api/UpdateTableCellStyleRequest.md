# UpdateTableCellStyleRequest

Updates the style of a range of table cells.

**Type:** object

## Properties

- **tableRange** ([TableRange](tablerange.md)): The table range representing the subset of the table to which the updates are applied.
- **tableStartLocation** ([Location](location.md)): The location where the table starts in the document. When specified, the updates are applied to all the cells in the table.
- **tableCellStyle** ([TableCellStyle](tablecellstyle.md)): The style to set on the table cells. When updating borders, if a cell shares a border with an adjacent cell, the corresponding border property of the adjacent cell is updated as well. Borders that are merged and invisible are not updated. Since updating a border shared by adjacent cells in the same request can cause conflicting border updates, border updates are applied in the following order: - `border_right` - `border_left` - `border_bottom` - `border_top`
- **fields** (string): The fields that should be updated. At least one field must be specified. The root `tableCellStyle` is implied and should not be specified. A single `"*"` can be used as short-hand for listing every field. For example to update the table cell background color, set `fields` to `"backgroundColor"`. To reset a property to its default value, include its field name in the field mask but leave the field itself unset.
