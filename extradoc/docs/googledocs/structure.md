# Structure of a Google Docs Document

Understanding Google Docs architecture is essential for effective API use. This documentation explains how document elements relate to each other and their styling properties.

## Top-Level Elements

A document serves as the outermost container in Google Docs—the unit saved in Google Drive, shared with users, and updated with content. The `documents` resource includes Tabs, `SuggestionsViewMode`, and other attributes like title, revision ID, and document ID.

## Tabs

Documents can contain multiple tabs with different text-level contents. Each Tab comprises:

- **TabProperties**: Contains tab attributes such as ID, title, and index
- **childTabs**: Exposes nested tabs directly beneath it
- **DocumentTab**: Represents the tab's text content

See @tabs.md for working with tabs.

## Body Content

The Body typically contains a document tab's full contents. Most programmable items exist within Body content as a sequence of `StructuralElement` objects.

### Structural Elements

A `StructuralElement` describes content that provides structure to the document. Structural elements and their content objects contain all visual components: text, inline images, and formatting.

### Paragraph Structure

A Paragraph is a `StructuralElement` representing text terminated by a newline. It comprises:

- **ParagraphElement**: Describes content within the paragraph
- **ParagraphStyle**: Optional element setting style properties
- **Bullet**: Optional element providing bullet specifications if the paragraph belongs to a list

See @lists.md for working with bulleted lists.

### Text Runs

A `TextRun` is a `ParagraphElement` that represents a contiguous string of text with all the same text style. Paragraphs can contain multiple text runs, but they never cross paragraph boundaries.

### Start and End Indexes

Elements within body content have `startIndex` and `endIndex` properties indicating their offset relative to the enclosing segment's beginning. Indexes are measured in UTF-16 code units. This means surrogate pairs consume two indexes.

## Accessing and Modifying Elements

Use `documents.batchUpdate` to modify many elements. For reading, use `documents.get` to obtain a JSON dump of the complete document, then parse the resulting data to locate specific elements.

See @requests-and-responses.md for details on these methods.

## Property Inheritance

A `StructuralElement` can inherit properties from parent objects. Text formatting applied overrides default formatting inherited from the paragraph's `TextStyle`. Unset formatting features continue inheriting from paragraph styles.

See @format-text.md for details on text formatting and style inheritance.
