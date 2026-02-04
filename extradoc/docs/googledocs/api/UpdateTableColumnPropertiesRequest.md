# UpdateTableColumnPropertiesRequest

Updates the TableColumnProperties of columns in a table.

**Type:** object

## Properties

- **tableStartLocation** ([Location](location.md)): The location where the table starts in the document.
- **columnIndices** (array of integer): The list of zero-based column indices whose property should be updated. If no indices are specified, all columns will be updated.
- **tableColumnProperties** ([TableColumnProperties](tablecolumnproperties.md)): The table column properties to update. If the value of `table_column_properties#width` is less than 5 points (5/72 inch), a 400 bad request error is returned.
- **fields** (string): The fields that should be updated. At least one field must be specified. The root `tableColumnProperties` is implied and should not be specified. A single `"*"` can be used as short-hand for listing every field. For example to update the column width, set `fields` to `"width"`.
