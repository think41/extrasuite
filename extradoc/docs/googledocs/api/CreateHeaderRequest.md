# CreateHeaderRequest

Creates a Header. The new header is applied to the SectionStyle at the location of the SectionBreak if specified, otherwise it is applied to the DocumentStyle. If a header of the specified type already exists, a 400 bad request error is returned.

**Type:** object

## Properties

- **type** (enum): The type of header to create.
- **sectionBreakLocation** ([Location](location.md)): The location of the SectionBreak which begins the section this header should belong to. If `section_break_location' is unset or if it refers to the first section break in the document body, the header applies to the DocumentStyle
