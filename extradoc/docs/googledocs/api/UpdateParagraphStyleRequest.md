# UpdateParagraphStyleRequest

Update the styling of all paragraphs that overlap with the given range.

**Type:** object

## Properties

- **range** ([Range](range.md)): The range overlapping the paragraphs to style.
- **paragraphStyle** ([ParagraphStyle](paragraphstyle.md)): The styles to set on the paragraphs. Certain paragraph style changes may cause other changes in order to mirror the behavior of the Docs editor. See the documentation of ParagraphStyle for more information.
- **fields** (string): The fields that should be updated. At least one field must be specified. The root `paragraph_style` is implied and should not be specified. A single `"*"` can be used as short-hand for listing every field. For example, to update the paragraph style's alignment property, set `fields` to `"alignment"`. To reset a property to its default value, include its field name in the field mask but leave the field itself unset.
