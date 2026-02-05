# Google Docs API Reference

This folder contains extracted schemas from the Google Docs API discovery document. Use this reference when you need precise field names and types for building API requests or parsing responses.

## Document Structure Schemas

These schemas define how a Google Doc is structured. Start with [Document](Document.md) and traverse down.

| Schema | Description |
|--------|-------------|
| [Document](Document.md) | Top-level document resource |
| [Tab](Tab.md) | A tab within a document |
| [TabProperties](TabProperties.md) | Properties of a tab (ID, title) |
| [DocumentTab](DocumentTab.md) | Content of a document tab |
| [Body](Body.md) | The main body content of a tab |
| [StructuralElement](StructuralElement.md) | A structural element (paragraph, table, etc.) |
| [Paragraph](Paragraph.md) | A paragraph structural element |
| [ParagraphElement](ParagraphElement.md) | Content within a paragraph |
| [TextRun](TextRun.md) | A contiguous run of text with same styling |

## Content Element Schemas

| Schema | Description |
|--------|-------------|
| [Table](Table.md) | A table structural element |
| [TableRow](TableRow.md) | A row in a table |
| [TableCell](TableCell.md) | A cell in a table row |
| [Header](Header.md) | A document header |
| [Footer](Footer.md) | A document footer |
| [Footnote](Footnote.md) | A document footnote |
| [InlineObject](InlineObject.md) | An inline object (image, chart) |
| [PositionedObject](PositionedObject.md) | A positioned object |
| [List](List.md) | A list definition |
| [ListProperties](ListProperties.md) | Properties of a list |
| [NestingLevel](NestingLevel.md) | A nesting level for lists |
| [NamedRanges](NamedRanges.md) | Collection of named ranges |
| [NamedRange](NamedRange.md) | A named range in the document |
| [Range](Range.md) | A range of content with start/end indexes |

## Style Schemas

| Schema | Description |
|--------|-------------|
| [TextStyle](TextStyle.md) | Styling for text (bold, italic, font, color) |
| [ParagraphStyle](ParagraphStyle.md) | Styling for paragraphs (alignment, spacing) |
| [DocumentStyle](DocumentStyle.md) | Document-level styling |
| [TableStyle](TableStyle.md) | Table styling |
| [TableCellStyle](TableCellStyle.md) | Table cell styling |
| [TableRowStyle](TableRowStyle.md) | Table row styling |
| [Dimension](Dimension.md) | A dimension value with magnitude and unit |
| [Color](Color.md) | A color value |
| [RgbColor](RgbColor.md) | RGB color components |
| [OptionalColor](OptionalColor.md) | An optional color wrapper |

## Request Schemas (for batchUpdate)

These schemas define the requests you can send via `documents.batchUpdate`.

### Text Operations

| Schema | Description |
|--------|-------------|
| [InsertTextRequest](InsertTextRequest.md) | Insert text at a location |
| [DeleteContentRangeRequest](DeleteContentRangeRequest.md) | Delete content in a range |
| [ReplaceAllTextRequest](ReplaceAllTextRequest.md) | Find and replace text |

### Style Operations

| Schema | Description |
|--------|-------------|
| [UpdateTextStyleRequest](UpdateTextStyleRequest.md) | Update text styling |
| [UpdateParagraphStyleRequest](UpdateParagraphStyleRequest.md) | Update paragraph styling |

### List Operations

| Schema | Description |
|--------|-------------|
| [CreateParagraphBulletsRequest](CreateParagraphBulletsRequest.md) | Create bullets/numbered list |
| [DeleteParagraphBulletsRequest](DeleteParagraphBulletsRequest.md) | Remove bullets from paragraphs |

### Table Operations

| Schema | Description |
|--------|-------------|
| [InsertTableRequest](InsertTableRequest.md) | Insert a new table |
| [InsertTableRowRequest](InsertTableRowRequest.md) | Insert a table row |
| [InsertTableColumnRequest](InsertTableColumnRequest.md) | Insert a table column |
| [DeleteTableRowRequest](DeleteTableRowRequest.md) | Delete a table row |
| [DeleteTableColumnRequest](DeleteTableColumnRequest.md) | Delete a table column |
| [UpdateTableCellStyleRequest](UpdateTableCellStyleRequest.md) | Update table cell styling |
| [UpdateTableColumnPropertiesRequest](UpdateTableColumnPropertiesRequest.md) | Update column properties |
| [UpdateTableRowStyleRequest](UpdateTableRowStyleRequest.md) | Update row styling |
| [MergeTableCellsRequest](MergeTableCellsRequest.md) | Merge table cells |
| [UnmergeTableCellsRequest](UnmergeTableCellsRequest.md) | Unmerge table cells |

### Image Operations

| Schema | Description |
|--------|-------------|
| [InsertInlineImageRequest](InsertInlineImageRequest.md) | Insert an inline image |

### Named Range Operations

| Schema | Description |
|--------|-------------|
| [CreateNamedRangeRequest](CreateNamedRangeRequest.md) | Create a named range |
| [DeleteNamedRangeRequest](DeleteNamedRangeRequest.md) | Delete a named range |
| [ReplaceNamedRangeContentRequest](ReplaceNamedRangeContentRequest.md) | Replace named range content |

### Header/Footer/Footnote Operations

| Schema | Description |
|--------|-------------|
| [CreateHeaderRequest](CreateHeaderRequest.md) | Create a header |
| [CreateFooterRequest](CreateFooterRequest.md) | Create a footer |
| [CreateFootnoteRequest](CreateFootnoteRequest.md) | Create a footnote |
| [DeleteHeaderRequest](DeleteHeaderRequest.md) | Delete a header |
| [DeleteFooterRequest](DeleteFooterRequest.md) | Delete a footer |

### Batch Request Wrapper

| Schema | Description |
|--------|-------------|
| [BatchUpdateDocumentRequest](BatchUpdateDocumentRequest.md) | Wrapper for batch update requests |
| [Request](Request.md) | Union type for all request types |

### Additional Operations

| Schema | Description |
|--------|-------------|
| [InsertPageBreakRequest](InsertPageBreakRequest.md) | Insert a page break |
| [InsertSectionBreakRequest](InsertSectionBreakRequest.md) | Insert a section break |
| [UpdateDocumentStyleRequest](UpdateDocumentStyleRequest.md) | Update document-level styling |
| [UpdateSectionStyleRequest](UpdateSectionStyleRequest.md) | Update section styling |
| [DeletePositionedObjectRequest](DeletePositionedObjectRequest.md) | Delete a positioned object |
| [ReplaceImageRequest](ReplaceImageRequest.md) | Replace an image |

## Helper Types

These types are used within requests and document structure.

| Schema | Description |
|--------|-------------|
| [Location](Location.md) | A location within a document (index + tabId) |
| [EndOfSegmentLocation](EndOfSegmentLocation.md) | Location at end of a segment |
| [WriteControl](WriteControl.md) | Controls for handling concurrent edits |
| [SubstringMatchCriteria](SubstringMatchCriteria.md) | Criteria for text matching |
| [TableCellLocation](TableCellLocation.md) | Location of a table cell |
| [TableRange](TableRange.md) | A range of table cells |
| [Size](Size.md) | Width and height dimensions |
| [Link](Link.md) | A hyperlink |
| [WeightedFontFamily](WeightedFontFamily.md) | Font family with weight |
| [ParagraphBorder](ParagraphBorder.md) | Border styling for paragraphs |
| [Shading](Shading.md) | Background shading |
| [Bullet](Bullet.md) | Bullet properties for list items |

## Paragraph Element Types

These are the different types of content that can appear within a paragraph.

| Schema | Description |
|--------|-------------|
| [TextRun](TextRun.md) | A run of text with consistent styling |
| [AutoText](AutoText.md) | Auto-generated text (page numbers, etc.) |
| [PageBreak](PageBreak.md) | A page break |
| [ColumnBreak](ColumnBreak.md) | A column break |
| [FootnoteReference](FootnoteReference.md) | Reference to a footnote |
| [HorizontalRule](HorizontalRule.md) | A horizontal rule |
| [Equation](Equation.md) | An equation |
| [InlineObjectElement](InlineObjectElement.md) | Reference to an inline object |
| [Person](Person.md) | A person mention |
| [RichLink](RichLink.md) | A rich link (smart chip) |

## Response Schemas

| Schema | Description |
|--------|-------------|
| [BatchUpdateDocumentResponse](BatchUpdateDocumentResponse.md) | Response from batchUpdate |
| [Response](Response.md) | Union type for all response types |
| [CreateNamedRangeResponse](CreateNamedRangeResponse.md) | Response with created named range ID |
| [InsertInlineImageResponse](InsertInlineImageResponse.md) | Response with inserted image ID |
| [ReplaceAllTextResponse](ReplaceAllTextResponse.md) | Response with replacement count |
| [CreateHeaderResponse](CreateHeaderResponse.md) | Response with created header ID |
| [CreateFooterResponse](CreateFooterResponse.md) | Response with created footer ID |
| [CreateFootnoteResponse](CreateFootnoteResponse.md) | Response with created footnote ID |
