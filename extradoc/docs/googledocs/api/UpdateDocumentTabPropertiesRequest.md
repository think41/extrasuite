# UpdateDocumentTabPropertiesRequest

Update the properties of a document tab.

**Type:** object

## Properties

- **tabProperties** ([TabProperties](tabproperties.md)): The tab properties to update.
- **fields** (string): The fields that should be updated. At least one field must be specified. The root `tab_properties` is implied and should not be specified. A single `"*"` can be used as short-hand for listing every field.
