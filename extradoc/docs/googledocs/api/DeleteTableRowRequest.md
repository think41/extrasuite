# DeleteTableRowRequest

Deletes a row from a table.

**Type:** object

## Properties

- **tableCellLocation** ([TableCellLocation](tablecelllocation.md)): The reference table cell location from which the row will be deleted. The row this cell spans will be deleted. If this is a merged cell that spans multiple rows, all rows that the cell spans will be deleted. If no rows remain in the table after this deletion, the whole table is deleted.
