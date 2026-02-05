# SectionBreak

A StructuralElement representing a section break. A section is a range of content that has the same SectionStyle. A section break represents the start of a new section, and the section style applies to the section after the section break. The document body always begins with a section break.

**Type:** object

## Properties

- **suggestedInsertionIds** (array of string): The suggested insertion IDs. A SectionBreak may have multiple insertion IDs if it's a nested suggested change. If empty, then this is not a suggested insertion.
- **suggestedDeletionIds** (array of string): The suggested deletion IDs. If empty, then there are no suggested deletions of this content.
- **sectionStyle** ([SectionStyle](sectionstyle.md)): The style of the section after this section break.
