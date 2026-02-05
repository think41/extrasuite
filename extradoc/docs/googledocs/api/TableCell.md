# TableCell

The contents and style of a cell in a Table.

**Type:** object

## Properties

- **startIndex** (integer): The zero-based start index of this cell, in UTF-16 code units.
- **endIndex** (integer): The zero-based end index of this cell, exclusive, in UTF-16 code units.
- **content** (array of [StructuralElement](structuralelement.md)): The content of the cell.
- **tableCellStyle** ([TableCellStyle](tablecellstyle.md)): The style of the cell.
- **suggestedInsertionIds** (array of string): The suggested insertion IDs. A TableCell may have multiple insertion IDs if it's a nested suggested change. If empty, then this is not a suggested insertion.
- **suggestedDeletionIds** (array of string): The suggested deletion IDs. If empty, then there are no suggested deletions of this content.
- **suggestedTableCellStyleChanges** (object): The suggested changes to the table cell style, keyed by suggestion ID.
