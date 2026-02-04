# PageBreak

A ParagraphElement representing a page break. A page break makes the subsequent text start at the top of the next page.

**Type:** object

## Properties

- **suggestedInsertionIds** (array of string): The suggested insertion IDs. A PageBreak may have multiple insertion IDs if it's a nested suggested change. If empty, then this is not a suggested insertion.
- **suggestedDeletionIds** (array of string): The suggested deletion IDs. If empty, then there are no suggested deletions of this content.
- **textStyle** ([TextStyle](textstyle.md)): The text style of this PageBreak. Similar to text content, like text runs and footnote references, the text style of a page break can affect content layout as well as the styling of text inserted next to it.
- **suggestedTextStyleChanges** (object): The suggested text style changes to this PageBreak, keyed by suggestion ID.
