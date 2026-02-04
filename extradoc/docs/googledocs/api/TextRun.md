# TextRun

A ParagraphElement that represents a run of text that all has the same styling.

**Type:** object

## Properties

- **content** (string): The text of this run. Any non-text elements in the run are replaced with the Unicode character U+E907.
- **suggestedInsertionIds** (array of string): The suggested insertion IDs. A TextRun may have multiple insertion IDs if it's a nested suggested change. If empty, then this is not a suggested insertion.
- **suggestedDeletionIds** (array of string): The suggested deletion IDs. If empty, then there are no suggested deletions of this content.
- **textStyle** ([TextStyle](textstyle.md)): The text style of this run.
- **suggestedTextStyleChanges** (object): The suggested text style changes to this run, keyed by suggestion ID.
