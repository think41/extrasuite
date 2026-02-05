# DeleteTableColumnRequest

Deletes a column from a table.

**Type:** object

## Properties

- **tableCellLocation** ([TableCellLocation](tablecelllocation.md)): The reference table cell location from which the column will be deleted. The column this cell spans will be deleted. If this is a merged cell that spans multiple columns, all columns that the cell spans will be deleted. If no columns remain in the table after this deletion, the whole table is deleted.
