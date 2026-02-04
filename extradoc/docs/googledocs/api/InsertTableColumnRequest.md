# InsertTableColumnRequest

Inserts an empty column into a table.

**Type:** object

## Properties

- **tableCellLocation** ([TableCellLocation](tablecelllocation.md)): The reference table cell location from which columns will be inserted. A new column will be inserted to the left (or right) of the column where the reference cell is. If the reference cell is a merged cell, a new column will be inserted to the left (or right) of the merged cell.
- **insertRight** (boolean): Whether to insert new column to the right of the reference cell location. - `True`: insert to the right. - `False`: insert to the left.
