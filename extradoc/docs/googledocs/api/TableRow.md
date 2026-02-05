# TableRow

The contents and style of a row in a Table.

**Type:** object

## Properties

- **startIndex** (integer): The zero-based start index of this row, in UTF-16 code units.
- **endIndex** (integer): The zero-based end index of this row, exclusive, in UTF-16 code units.
- **tableCells** (array of [TableCell](tablecell.md)): The contents and style of each cell in this row. It's possible for a table to be non-rectangular, so some rows may have a different number of cells than other rows in the same table.
- **suggestedInsertionIds** (array of string): The suggested insertion IDs. A TableRow may have multiple insertion IDs if it's a nested suggested change. If empty, then this is not a suggested insertion.
- **suggestedDeletionIds** (array of string): The suggested deletion IDs. If empty, then there are no suggested deletions of this content.
- **tableRowStyle** ([TableRowStyle](tablerowstyle.md)): The style of the table row.
- **suggestedTableRowStyleChanges** (object): The suggested style changes to this row, keyed by suggestion ID.
