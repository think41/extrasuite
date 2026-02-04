# Structural Edit Rules and Behavior

This documentation covers constraints and limitations when editing Google Docs through the API. All edits must maintain valid document structure.

## Insert Text

When adding text via the API, a newline character automatically generates a new paragraph, copying style from the current paragraph position. Text insertion requires an existing paragraph boundary—you cannot insert at a table's start index, for instance.

The system may shift insertion points to avoid splitting Unicode grapheme clusters. Text styling typically matches adjacent characters. Certain control characters and private-use Unicode ranges are automatically removed during insertion.

See @move-text.md for text insertion code examples.

## Insert Inline Images

Images must satisfy specific requirements:
- Under 50 MB file size
- Not exceeding 25 megapixels
- PNG, JPEG, or GIF format
- Image URI must be publicly accessible and under 2 KB

Like text, images must be placed within paragraph bounds rather than at structural element boundaries. Images cannot be embedded within footnotes or equations.

See @images.md for image insertion code examples.

## Format Text

When applying formatting across a range, any partially or completely overlapped paragraph receives the formatting. The range may extend to include adjacent newlines. If a range fully contains a list item, its bullet styling updates to match.

See @format-text.md for formatting code examples.

## Create Paragraph Bullets

Bullets apply to all paragraphs overlapping the specified range. Nesting levels depend on leading tabs before each paragraph, which are removed during bullet creation—potentially shifting text indexes. Bullets matching an immediately preceding list cause paragraph merging with that list.

See @lists.md for bullet creation code examples.

## Delete Text

Deletions crossing paragraph boundaries may alter styles, lists, positioned objects, and bookmarks. Invalid deletions that would corrupt document structure are rejected, including:

- Separating surrogate pairs
- Removing the final newline from body, header, footer, footnote, or table cell elements
- Partially deleting tables, equations, or section breaks
- Removing newlines preceding structural elements without deleting the entire element
- Deleting individual table rows or cells

You may delete content within table cells without restriction.

See @move-text.md for deletion code examples.
