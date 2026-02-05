# TableOfContents

A StructuralElement representing a table of contents.

**Type:** object

## Properties

- **content** (array of [StructuralElement](structuralelement.md)): The content of the table of contents.
- **suggestedInsertionIds** (array of string): The suggested insertion IDs. A TableOfContents may have multiple insertion IDs if it is a nested suggested change. If empty, then this is not a suggested insertion.
- **suggestedDeletionIds** (array of string): The suggested deletion IDs. If empty, then there are no suggested deletions of this content.
