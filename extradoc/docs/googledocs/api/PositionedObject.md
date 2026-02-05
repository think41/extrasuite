# PositionedObject

An object that's tethered to a Paragraph and positioned relative to the beginning of the paragraph. A PositionedObject contains an EmbeddedObject such as an image.

**Type:** object

## Properties

- **objectId** (string): The ID of this positioned object.
- **positionedObjectProperties** ([PositionedObjectProperties](positionedobjectproperties.md)): The properties of this positioned object.
- **suggestedPositionedObjectPropertiesChanges** (object): The suggested changes to the positioned object properties, keyed by suggestion ID.
- **suggestedInsertionId** (string): The suggested insertion ID. If empty, then this is not a suggested insertion.
- **suggestedDeletionIds** (array of string): The suggested deletion IDs. If empty, then there are no suggested deletions of this content.
