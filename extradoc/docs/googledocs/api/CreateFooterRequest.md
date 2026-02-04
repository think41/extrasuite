# CreateFooterRequest

Creates a Footer. The new footer is applied to the SectionStyle at the location of the SectionBreak if specified, otherwise it is applied to the DocumentStyle. If a footer of the specified type already exists, a 400 bad request error is returned.

**Type:** object

## Properties

- **type** (enum): The type of footer to create.
- **sectionBreakLocation** ([Location](location.md)): The location of the SectionBreak immediately preceding the section whose SectionStyle this footer should belong to. If this is unset or refers to the first section break in the document, the footer applies to the document style.
