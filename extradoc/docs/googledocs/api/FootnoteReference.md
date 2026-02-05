# FootnoteReference

A ParagraphElement representing a footnote reference. A footnote reference is the inline content rendered with a number and is used to identify the footnote.

**Type:** object

## Properties

- **footnoteId** (string): The ID of the footnote that contains the content of this footnote reference.
- **footnoteNumber** (string): The rendered number of this footnote.
- **suggestedInsertionIds** (array of string): The suggested insertion IDs. A FootnoteReference may have multiple insertion IDs if it's a nested suggested change. If empty, then this is not a suggested insertion.
- **suggestedDeletionIds** (array of string): The suggested deletion IDs. If empty, then there are no suggested deletions of this content.
- **textStyle** ([TextStyle](textstyle.md)): The text style of this FootnoteReference.
- **suggestedTextStyleChanges** (object): The suggested text style changes to this FootnoteReference, keyed by suggestion ID.
