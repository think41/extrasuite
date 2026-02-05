# CreateParagraphBulletsRequest

Creates bullets for all of the paragraphs that overlap with the given range. The nesting level of each paragraph will be determined by counting leading tabs in front of each paragraph. To avoid excess space between the bullet and the corresponding paragraph, these leading tabs are removed by this request. This may change the indices of parts of the text. If the paragraph immediately before paragraphs being updated is in a list with a matching preset, the paragraphs being updated are added to that preceding list.

**Type:** object

## Properties

- **range** ([Range](range.md)): The range to apply the bullet preset to.
- **bulletPreset** (enum): The kinds of bullet glyphs to be used.
