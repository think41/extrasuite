# InlineObjectElement

A ParagraphElement that contains an InlineObject.

**Type:** object

## Properties

- **inlineObjectId** (string): The ID of the InlineObject this element contains.
- **suggestedInsertionIds** (array of string): The suggested insertion IDs. An InlineObjectElement may have multiple insertion IDs if it's a nested suggested change. If empty, then this is not a suggested insertion.
- **suggestedDeletionIds** (array of string): The suggested deletion IDs. If empty, then there are no suggested deletions of this content.
- **textStyle** ([TextStyle](textstyle.md)): The text style of this InlineObjectElement. Similar to text content, like text runs and footnote references, the text style of an inline object element can affect content layout as well as the styling of text inserted next to it.
- **suggestedTextStyleChanges** (object): The suggested text style changes to this InlineObject, keyed by suggestion ID.
