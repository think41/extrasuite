# HorizontalRule

A ParagraphElement representing a horizontal line.

**Type:** object

## Properties

- **suggestedInsertionIds** (array of string): The suggested insertion IDs. A HorizontalRule may have multiple insertion IDs if it is a nested suggested change. If empty, then this is not a suggested insertion.
- **suggestedDeletionIds** (array of string): The suggested deletion IDs. If empty, then there are no suggested deletions of this content.
- **textStyle** ([TextStyle](textstyle.md)): The text style of this HorizontalRule. Similar to text content, like text runs and footnote references, the text style of a horizontal rule can affect content layout as well as the styling of text inserted next to it.
- **suggestedTextStyleChanges** (object): The suggested text style changes to this HorizontalRule, keyed by suggestion ID.
