# Table

A StructuralElement representing a table.

**Type:** object

## Properties

- **rows** (integer): Number of rows in the table.
- **columns** (integer): Number of columns in the table. It's possible for a table to be non-rectangular, so some rows may have a different number of cells.
- **tableRows** (array of [TableRow](tablerow.md)): The contents and style of each row.
- **suggestedInsertionIds** (array of string): The suggested insertion IDs. A Table may have multiple insertion IDs if it's a nested suggested change. If empty, then this is not a suggested insertion.
- **suggestedDeletionIds** (array of string): The suggested deletion IDs. If empty, then there are no suggested deletions of this content.
- **tableStyle** ([TableStyle](tablestyle.md)): The style of the table.
