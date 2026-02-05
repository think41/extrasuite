# InsertTableRequest

Inserts a table at the specified location. A newline character will be inserted before the inserted table.

**Type:** object

## Properties

- **location** ([Location](location.md)): Inserts the table at a specific model index. A newline character will be inserted before the inserted table, therefore the table start index will be at the specified location index + 1. The table must be inserted inside the bounds of an existing Paragraph. For instance, it cannot be inserted at a table's start index (i.e. between an existing table and its preceding paragraph). Tables cannot be inserted inside a footnote or equation.
- **endOfSegmentLocation** ([EndOfSegmentLocation](endofsegmentlocation.md)): Inserts the table at the end of the given header, footer or document body. A newline character will be inserted before the inserted table. Tables cannot be inserted inside a footnote.
- **rows** (integer): The number of rows in the table.
- **columns** (integer): The number of columns in the table.
