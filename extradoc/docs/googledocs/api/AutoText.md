# AutoText

A ParagraphElement representing a spot in the text that's dynamically replaced with content that can change over time, like a page number.

**Type:** object

## Properties

- **type** (enum): The type of this auto text.
- **suggestedInsertionIds** (array of string): The suggested insertion IDs. An AutoText may have multiple insertion IDs if it's a nested suggested change. If empty, then this is not a suggested insertion.
- **suggestedDeletionIds** (array of string): The suggested deletion IDs. If empty, then there are no suggested deletions of this content.
- **textStyle** ([TextStyle](textstyle.md)): The text style of this AutoText.
- **suggestedTextStyleChanges** (object): The suggested text style changes to this AutoText, keyed by suggestion ID.
