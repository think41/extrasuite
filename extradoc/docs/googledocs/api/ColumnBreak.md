# ColumnBreak

A ParagraphElement representing a column break. A column break makes the subsequent text start at the top of the next column.

**Type:** object

## Properties

- **suggestedInsertionIds** (array of string): The suggested insertion IDs. A ColumnBreak may have multiple insertion IDs if it's a nested suggested change. If empty, then this is not a suggested insertion.
- **suggestedDeletionIds** (array of string): The suggested deletion IDs. If empty, then there are no suggested deletions of this content.
- **textStyle** ([TextStyle](textstyle.md)): The text style of this ColumnBreak. Similar to text content, like text runs and footnote references, the text style of a column break can affect content layout as well as the styling of text inserted next to it.
- **suggestedTextStyleChanges** (object): The suggested text style changes to this ColumnBreak, keyed by suggestion ID.
