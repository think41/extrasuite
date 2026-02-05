# UpdateSectionStyleRequest

Updates the SectionStyle.

**Type:** object

## Properties

- **range** ([Range](range.md)): The range overlapping the sections to style. Because section breaks can only be inserted inside the body, the segment ID field must be empty.
- **sectionStyle** ([SectionStyle](sectionstyle.md)): The styles to be set on the section. Certain section style changes may cause other changes in order to mirror the behavior of the Docs editor. See the documentation of SectionStyle for more information.
- **fields** (string): The fields that should be updated. At least one field must be specified. The root `section_style` is implied and must not be specified. A single `"*"` can be used as short-hand for listing every field. For example to update the left margin, set `fields` to `"margin_left"`.
