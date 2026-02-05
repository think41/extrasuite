# InlineObject

An object that appears inline with text. An InlineObject contains an EmbeddedObject such as an image.

**Type:** object

## Properties

- **objectId** (string): The ID of this inline object. Can be used to update an object’s properties.
- **inlineObjectProperties** ([InlineObjectProperties](inlineobjectproperties.md)): The properties of this inline object.
- **suggestedInlineObjectPropertiesChanges** (object): The suggested changes to the inline object properties, keyed by suggestion ID.
- **suggestedInsertionId** (string): The suggested insertion ID. If empty, then this is not a suggested insertion.
- **suggestedDeletionIds** (array of string): The suggested deletion IDs. If empty, then there are no suggested deletions of this content.
