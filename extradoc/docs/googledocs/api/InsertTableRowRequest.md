# InsertTableRowRequest

Inserts an empty row into a table.

**Type:** object

## Properties

- **tableCellLocation** ([TableCellLocation](tablecelllocation.md)): The reference table cell location from which rows will be inserted. A new row will be inserted above (or below) the row where the reference cell is. If the reference cell is a merged cell, a new row will be inserted above (or below) the merged cell.
- **insertBelow** (boolean): Whether to insert new row below the reference cell location. - `True`: insert below the cell. - `False`: insert above the cell.
