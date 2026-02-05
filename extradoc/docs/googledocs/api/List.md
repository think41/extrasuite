# List

A List represents the list attributes for a group of paragraphs that all belong to the same list. A paragraph that's part of a list has a reference to the list's ID in its bullet.

**Type:** object

## Properties

- **listProperties** ([ListProperties](listproperties.md)): The properties of the list.
- **suggestedListPropertiesChanges** (object): The suggested changes to the list properties, keyed by suggestion ID.
- **suggestedInsertionId** (string): The suggested insertion ID. If empty, then this is not a suggested insertion.
- **suggestedDeletionIds** (array of string): The suggested deletion IDs. If empty, then there are no suggested deletions of this list.
