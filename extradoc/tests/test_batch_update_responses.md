# Test Plan: Batch Update Response Document Structure

This document outlines test scenarios for verifying that the MockGoogleDocsAPI returns document structures that exactly match what the real Google Docs API would return after batch update operations.

## Testing Strategy

For each batch update request type, we need to verify:
1. The response structure is correct (replies array, revision ID, etc.)
2. The document returned by `get()` after `batch_update()` has the correct structure
3. Indexes are updated correctly for all elements
4. Content is modified as expected
5. Style and formatting are applied correctly
6. Structural elements (tables, headers, etc.) have correct nested structure

## Test Scenarios

### Category 1: Text Operations

#### TC-001: InsertText - Simple text insertion
- **Setup**: Document with "Hello\n"
- **Operation**: Insert " World" at index 6
- **Expected Result**:
  - Document content is "Hello World\n"
  - TextRun endIndex updated from 7 to 13
  - Paragraph endIndex updated from 7 to 13

#### TC-002: InsertText - Insert with newline creates new paragraph
- **Setup**: Document with "Hello\n"
- **Operation**: Insert "Title\n" at index 1
- **Expected Result**:
  - Two paragraphs exist
  - First paragraph: "Title\n" (indices 1-7)
  - Second paragraph: "Hello\n" (indices 7-13)
  - All subsequent indexes shifted by 6

#### TC-003: InsertText - Insert at end of segment location
- **Setup**: Document with "Hello\n"
- **Operation**: Insert " World" using endOfSegmentLocation
- **Expected Result**:
  - Document content is "Hello World\n"
  - Text inserted before final newline
  - Indexes updated correctly

#### TC-004: DeleteContentRange - Simple deletion
- **Setup**: Document with "Hello World\n"
- **Operation**: Delete range 6-11 (delete " World")
- **Expected Result**:
  - Document content is "Hello\n"
  - TextRun endIndex reduced from 13 to 7
  - Paragraph endIndex reduced from 13 to 7

#### TC-005: DeleteContentRange - Delete across paragraph boundary
- **Setup**: Document with two paragraphs "Para1\n" and "Para2\n"
- **Operation**: Delete range 5-8 (delete "\nPa")
- **Expected Result**:
  - Single paragraph "Parara2\n"
  - Paragraphs merged
  - Indexes updated correctly

#### TC-006: DeleteContentRange - Delete with surrogate pairs
- **Setup**: Document with "Hello😀World\n"
- **Operation**: Delete range 6-8 (delete emoji)
- **Expected Result**:
  - Document content is "HelloWorld\n"
  - Indexes account for 2-unit emoji deletion

### Category 2: Style Operations

#### TC-007: UpdateTextStyle - Apply bold to range
- **Setup**: Document with "Hello World\n"
- **Operation**: UpdateTextStyle bold=true on range 1-6
- **Expected Result**:
  - Document may have split TextRuns (implementation dependent)
  - TextRun covering "Hello" has textStyle.bold: true
  - TextRun covering " World" has textStyle without bold or bold: false

#### TC-008: UpdateTextStyle - Apply multiple styles
- **Setup**: Document with "Hello\n"
- **Operation**: UpdateTextStyle with bold, italic, and foregroundColor
- **Expected Result**:
  - TextRun has all three style properties set
  - Style structure matches Google Docs format

#### TC-009: UpdateParagraphStyle - Apply heading style
- **Setup**: Document with "Title\n"
- **Operation**: UpdateParagraphStyle namedStyleType=HEADING_1
- **Expected Result**:
  - Paragraph has paragraphStyle.namedStyleType: "HEADING_1"

#### TC-010: UpdateParagraphStyle - Apply alignment
- **Setup**: Document with "Center me\n"
- **Operation**: UpdateParagraphStyle alignment=CENTER
- **Expected Result**:
  - Paragraph has paragraphStyle.alignment: "CENTER"

### Category 3: List Operations

#### TC-011: CreateParagraphBullets - Create bulleted list
- **Setup**: Document with three paragraphs
- **Operation**: CreateParagraphBullets with bulletPreset=NUMBERED_DECIMAL
- **Expected Result**:
  - Each paragraph has bullet property
  - NestingLevel structure created
  - List ID assigned

#### TC-012: DeleteParagraphBullets - Remove bullets
- **Setup**: Document with bulleted list
- **Operation**: DeleteParagraphBullets on range
- **Expected Result**:
  - Bullet properties removed from paragraphs
  - NestingLevel removed

### Category 4: Named Ranges

#### TC-013: CreateNamedRange - Create single named range
- **Setup**: Document with "Hello World\n"
- **Operation**: CreateNamedRange name="greeting" range 1-6
- **Expected Result**:
  - Response includes namedRangeId
  - Document.tabs[0].documentTab.namedRanges contains "greeting"
  - Named range has correct start/end indexes
  - namedRangeId is unique and present

#### TC-014: CreateNamedRange - Create multiple ranges with same name
- **Setup**: Document with content
- **Operation**: CreateNamedRange twice with same name, different ranges
- **Expected Result**:
  - namedRanges["name"].namedRanges has 2 entries
  - Each has unique namedRangeId
  - Both ranges preserved

#### TC-015: DeleteNamedRange - Delete by ID
- **Setup**: Document with 2 named ranges of same name
- **Operation**: DeleteNamedRange by namedRangeId
- **Expected Result**:
  - Specific range removed
  - Other range with same name preserved
  - Document structure updated

#### TC-016: DeleteNamedRange - Delete by name
- **Setup**: Document with 2 named ranges of same name
- **Operation**: DeleteNamedRange by name
- **Expected Result**:
  - All ranges with that name removed
  - Document structure updated

### Category 5: Table Operations

#### TC-017: InsertTable - Create table
- **Setup**: Document with "Before\n"
- **Operation**: InsertTable rows=2, columns=3 at index 7
- **Expected Result**:
  - Table structural element created at correct index
  - Table has tableRows array with 2 entries
  - Each row has tableCells array with 3 entries
  - Each cell has content with paragraph containing "\n"
  - Indexes for table structure correct
  - "After" content indexes shifted

#### TC-018: InsertTable - Insert at end of segment
- **Setup**: Document with "Content\n"
- **Operation**: InsertTable using endOfSegmentLocation
- **Expected Result**:
  - Table inserted before final newline
  - Indexes correct

#### TC-019: InsertTableRow - Add row to existing table
- **Setup**: Document with 2x2 table
- **Operation**: InsertTableRow
- **Expected Result**:
  - Table.tableRows has additional entry
  - New row has correct number of cells
  - Cell indexes updated
  - Subsequent content indexes shifted

#### TC-020: InsertTableColumn - Add column to existing table
- **Setup**: Document with 2x2 table
- **Operation**: InsertTableColumn
- **Expected Result**:
  - Each row has additional cell
  - Table.columns count increased
  - Cell indexes updated
  - Subsequent content indexes shifted

#### TC-021: DeleteTableRow - Remove row
- **Setup**: Document with 3x2 table
- **Operation**: DeleteTableRow
- **Expected Result**:
  - Table.tableRows has one fewer entry
  - Indexes shifted for remaining content
  - Table structure intact

#### TC-022: DeleteTableColumn - Remove column
- **Setup**: Document with 2x3 table
- **Operation**: DeleteTableColumn
- **Expected Result**:
  - Each row has one fewer cell
  - Table.columns count decreased
  - Indexes shifted correctly

### Category 6: Header/Footer/Footnote Operations

#### TC-023: CreateHeader - Create DEFAULT header
- **Setup**: Empty document
- **Operation**: CreateHeader type=DEFAULT
- **Expected Result**:
  - Response includes headerId
  - Document.tabs[0].documentTab.headers contains new header
  - Header has content array with single paragraph "\n"
  - Header segment indexes start at 1

#### TC-024: CreateFooter - Create DEFAULT footer
- **Setup**: Empty document
- **Operation**: CreateFooter type=DEFAULT
- **Expected Result**:
  - Response includes footerId
  - Document.tabs[0].documentTab.footers contains new footer
  - Footer has content array with single paragraph "\n"

#### TC-025: CreateFootnote - Create footnote
- **Setup**: Document with "Text\n"
- **Operation**: CreateFootnote at index 3
- **Expected Result**:
  - Response includes footnoteId
  - Document.tabs[0].documentTab.footnotes contains new footnote
  - Footnote has content with " \n" (space + newline)
  - Body has footnoteReference element at index 3

#### TC-026: DeleteHeader - Remove header
- **Setup**: Document with DEFAULT header
- **Operation**: DeleteHeader
- **Expected Result**:
  - Header removed from document.tabs[0].documentTab.headers
  - Can create new DEFAULT header again

#### TC-027: DeleteFooter - Remove footer
- **Setup**: Document with DEFAULT footer
- **Operation**: DeleteFooter
- **Expected Result**:
  - Footer removed from document structure

### Category 7: Tab Operations

#### TC-028: AddDocumentTab - Create new tab
- **Setup**: Document with 1 tab
- **Operation**: AddDocumentTab
- **Expected Result**:
  - Response includes tabId
  - Document.tabs has 2 entries
  - New tab has tabProperties with generated tabId
  - New tab has documentTab with empty body

#### TC-029: DeleteTab - Remove tab
- **Setup**: Document with 2 tabs
- **Operation**: DeleteTab
- **Expected Result**:
  - Tab removed from document.tabs array

### Category 8: Complex Multi-Operation Scenarios

#### TC-030: Insert at start then insert at end
- **Setup**: Document with "Middle\n"
- **Operation**:
  1. Insert "Start " at index 1
  2. Insert " End" at index 13 (after first insert)
- **Expected Result**:
  - Document content is "Start Middle End\n"
  - All indexes correct
  - Single paragraph

#### TC-031: Delete then insert at same location
- **Setup**: Document with "Hello World\n"
- **Operation**:
  1. Delete range 6-11 (delete " World")
  2. Insert " Universe" at index 6
- **Expected Result**:
  - Document content is "Hello Universe\n"
  - Indexes updated correctly

#### TC-032: Create named range, insert before it, verify range unchanged
- **Setup**: Document with "Hello World\n"
- **Operation**:
  1. CreateNamedRange name="world" range 7-12
  2. Insert "Wonderful " at index 1
- **Expected Result**:
  - Named range still points to indices 7-12 (not updated)
  - Named range now covers different content (implementation note)

#### TC-033: Insert table then modify cell content
- **Setup**: Document with "Start\n"
- **Operation**:
  1. InsertTable 2x2 at end of segment
  2. InsertText into first cell
- **Expected Result**:
  - Table structure correct
  - Cell content updated
  - Indexes correct throughout

#### TC-034: Multiple style updates in sequence
- **Setup**: Document with "Hello World\n"
- **Operation**:
  1. UpdateTextStyle bold on 1-6
  2. UpdateTextStyle italic on 7-12
  3. UpdateTextStyle foregroundColor on 1-12
- **Expected Result**:
  - Correct style segments (implementation dependent on run splitting)
  - All styles applied correctly

### Category 9: Edge Cases

#### TC-035: Insert text with emoji
- **Setup**: Document with "Hello\n"
- **Operation**: Insert "😀" at index 6
- **Expected Result**:
  - Document content is "Hello😀\n"
  - Emoji accounts for 2 UTF-16 code units
  - Paragraph endIndex is 9 (not 8)

#### TC-036: Multiple emojis and deletion
- **Setup**: Document with "A😀B😎C\n"
- **Operation**: Delete range 2-8 (delete "😀B😎")
- **Expected Result**:
  - Document content is "AC\n"
  - Indexes updated correctly accounting for surrogate pairs

#### TC-037: Insert at every paragraph boundary
- **Setup**: Document with "Para1\nPara2\nPara3\n"
- **Operation**: Insert "•" at start of each paragraph
- **Expected Result**:
  - Three paragraphs with bullets
  - Indexes shifted correctly
  - All paragraphs intact

#### TC-038: Delete entire table including boundaries
- **Setup**: Document with "Before\n[TABLE]\nAfter\n"
- **Operation**: DeleteContentRange covering entire table
- **Expected Result**:
  - Table removed from structure
  - "Before\n" and "After\n" paragraphs adjacent
  - Indexes updated

#### TC-039: Create max-length named range name (256 UTF-16 units)
- **Setup**: Document with content
- **Operation**: CreateNamedRange with 256-character name
- **Expected Result**:
  - Named range created successfully
  - Name stored correctly

#### TC-040: Batch update with revision ID update
- **Setup**: Document with initial revision
- **Operation**: Any batch update
- **Expected Result**:
  - Response.writeControl.requiredRevisionId is new revision
  - Document.revisionId updated
  - Subsequent get() returns new revision ID

### Category 10: Inline Objects and Special Elements

#### TC-041: InsertInlineImage - Insert image
- **Setup**: Document with "Text\n"
- **Operation**: InsertInlineImage at index 3
- **Expected Result**:
  - Response includes objectId
  - Paragraph has inlineObjectElement
  - Document.inlineObjects contains image object
  - Indexes shifted for inline object (typically 1 unit)

#### TC-042: InsertPageBreak - Insert page break
- **Setup**: Document with "Page1\n"
- **Operation**: InsertPageBreak at end of segment
- **Expected Result**:
  - PageBreak structural element created
  - Indexes updated

#### TC-043: InsertSectionBreak - Insert section break
- **Setup**: Document with "Section1\n"
- **Operation**: InsertSectionBreak type=NEXT_PAGE
- **Expected Result**:
  - SectionBreak structural element created
  - Indexes updated

## Implementation Notes

For tests to pass, the MockGoogleDocsAPI implementation needs to:

1. **Actually modify the document structure** - Currently many handlers are validation-only
2. **Update all indexes** when content is inserted or deleted
3. **Split TextRuns** when styles are applied to partial ranges (or use alternative representation)
4. **Create proper nested structures** for tables, headers, footers, etc.
5. **Generate unique IDs** for named ranges, headers, footers, footnotes, tabs, images
6. **Track and update revision IDs** correctly
7. **Handle surrogate pairs** correctly in index calculations
8. **Merge paragraphs** when deletions cross paragraph boundaries
9. **Create new paragraphs** when newlines are inserted
10. **Update structural tracker** after each operation

## Testing Approach

Each test should:
1. Create initial document state
2. Apply batch update
3. Call `get()` to retrieve updated document
4. Assert on document structure at multiple levels:
   - Top-level fields (documentId, revisionId)
   - Tab structure
   - Body content array
   - Specific structural elements
   - Text content and indexes
   - Style properties
   - Named ranges, headers, footers, footnotes
5. Verify response structure (replies array, revision ID in writeControl)
