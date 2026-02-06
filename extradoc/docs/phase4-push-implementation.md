# ExtraDoc Phase 4: Complete Push Implementation

## Status: Core Features Complete

**Last Updated:** 2026-02-06

Core push functionality is working. Verified against real Google Docs:
- Body content (add/modify/delete): ✅ Working
- Text styling (bold, italic): ✅ Working
- Bullet lists: ✅ Working
- Table cell content: ✅ Working
- Header/footer content: ✅ Working

## Overview

Implement complete push functionality following these priorities:
1. **Structural elements first** - Create headers/footers/tabs, capture IDs, then populate content
2. **Complete styling support** - All text styles AND all paragraph styles
3. **Content population** - Tables, special elements, segment content

## What Was Done

### Phase 1: Declarative Style System ✅ COMPLETE

Created `src/extradoc/style_converter.py` with:
- `StyleType` enum (BOOL, PT, FLOAT, COLOR, ENUM, ENUM_MAP, FONT, LINK, BORDER)
- `StyleProp` dataclass for declarative style definitions
- `TEXT_STYLE_PROPS` - Text style mappings (bold, italic, underline, strikethrough, smallcaps, superscript, subscript, font, size, color, bg, links)
- `PARAGRAPH_STYLE_PROPS` - Paragraph style mappings (alignment, lineSpacing, spaceAbove, spaceBelow, indentation, keepTogether, keepNext, avoidWidow, direction, shading, borders)
- `TABLE_CELL_STYLE_PROPS` - Table cell style mappings (bg, valign, padding)
- `convert_styles()` - Generic function to convert XML styles to API requests
- Helper functions: `build_text_style_request()`, `build_paragraph_style_request()`, `build_table_cell_style_request()`

### Phase 2: Structural Element Creation ✅ COMPLETE

Created `src/extradoc/request_generators/structural.py` with:
- `STRUCTURAL_REQUEST_TYPES` - Set of structural request types
- `separate_structural_requests()` - Split structural from content requests
- `extract_created_ids()` - Extract placeholder-to-real ID mappings from API responses
- `substitute_placeholder_ids()` - Replace placeholders with real IDs in requests
- `has_segment_id()` - Check if object references specific segment IDs
- `separate_by_segment_ids()` - Separate requests by segment ID references
- `extract_placeholder_footnote_ids()` - Extract and strip placeholder footnote IDs

### Phase 3: Table Request Generator ✅ COMPLETE

Created `src/extradoc/request_generators/table.py` with:
- `generate_table_cell_style_requests()` - Generate updateTableCellStyle requests for styled cells
- `calculate_cell_positions()` - Map (row, col) -> insertion index for table cells
- `calculate_table_length()` - Calculate minimum length of an empty table
- `generate_insert_table_request()` - Generate insertTable request
- `generate_insert_table_row_request()` - Generate insertTableRow request
- `generate_delete_table_row_request()` - Generate deleteTableRow request
- `generate_insert_table_column_request()` - Generate insertTableColumn request
- `generate_delete_table_column_request()` - Generate deleteTableColumn request

### Phase 4: Content Request Generator ✅ COMPLETE

Created `src/extradoc/request_generators/content.py` with:
- `ParsedContent` dataclass for parsed content blocks
- `TextRun`, `ParagraphInfo`, `SpecialElement` dataclasses
- `parse_content_xml()` - Parse ContentBlock XML into structured data
- `generate_content_requests()` - Generate insertText + updateTextStyle + updateParagraphStyle + createParagraphBullets requests
- `generate_delete_content_request()` - Generate deleteContentRange request
- `_generate_special_element_request()` - Handle pagebreak, columnbreak, footnoteref

### Phase 5: Refactor diff_engine.py ✅ COMPLETE

Updated `src/extradoc/diff_engine.py` to:
- Import from `style_converter` for style conversion
- Import from `request_generators.table` for table row/column request generation
- Removed duplicate table request generation functions
- Uses `convert_styles()` for text style conversion

### Phase 6: Update client.py ✅ COMPLETE

Updated `src/extradoc/client.py` to:
- Import `separate_by_segment_ids` and `extract_placeholder_footnote_ids` from structural module
- Use these utilities in the push workflow for cleaner two-batch execution

### Phase 7: Table Cell Content Modification ✅ COMPLETE

Updated `src/extradoc/diff_engine.py` with:
- `_calculate_cell_content_index()` - Compute cell content start positions
- `_calculate_cell_content_length()` - Calculate UTF-16 length of cell content
- `_get_element_text_length()` - Helper for text length calculation
- `_calculate_nested_table_length()` - Handle nested tables
- `_get_pristine_cell_length()` - Get pristine cell content length
- `_extract_cell_inner_content()` - Extract inner paragraphs from cell XML
- Fixed MODIFIED cell handling to use reusable `_generate_content_insert_requests`
- Added `_skipReorder` marker to keep table cell insert+style requests together
- Skip recursive child processing for TABLE blocks (handled in `_generate_table_modify_requests`)
- Fixed header/footer content changes by checking `pristine_end > pristine_start`
  (headers/footers start at index 0, not 1 like body)

### Phase 8: Integration Testing ✅ COMPLETE

Verified against real Google Doc (document ID: 15dNMijQYl3juFdu8LqLvJoh3K10DREbtUm82489hgAs):

| Test Case | Status | Notes |
|-----------|--------|-------|
| Body text insertion | ✅ Pass | Styled text with bold/italic correctly applied |
| Body text modification | ✅ Pass | Delete + insert working |
| Body content deletion | ✅ Pass | deleteContentRange working |
| Bullet list insertion | ✅ Pass | createParagraphBullets working |
| Table cell modification | ✅ Pass | Cell content with styling correctly applied |
| Header modification | ✅ Pass | Content replaced with correct styling |
| Footer modification | ✅ Pass | Content added to empty footer |

**Key fixes applied during testing:**
1. Request ordering - Added `_skipReorder` marker to keep table cell insert+style requests together (prevents style corruption)
2. Header/footer index handling - Fixed condition `pristine_start_index > 0` to `pristine_end_index > pristine_start_index` (headers/footers start at 0)
3. Recursive processing - Skip TABLE child changes since they're handled by `_generate_table_modify_requests`

## Known Issue: Nested Bullet Lists

**Status:** Not working as expected. Needs further investigation.

### The Problem

When creating nested bullet lists (`<li level="1">`), the Google Docs API is not correctly setting the nesting level despite following the documented approach.

### What the Documentation Says

From `docs/googledocs/api/CreateParagraphBulletsRequest.md`:
> The nesting level of each paragraph will be determined by counting leading tabs in front of each paragraph. To avoid excess space between the bullet and the corresponding paragraph, these leading tabs are removed by this request.

From `docs/googledocs/lists.md`:
> Paragraph nesting levels are determined by counting leading tabs.
> **Important limitation:** You cannot adjust nesting levels of existing bullets. Instead, delete the bullet, add leading tabs, then recreate it.

### What Was Tried

1. **Insert text with tabs, then createParagraphBullets in same batchUpdate**
   - Inserted: `"Item A\n\tNested Item B\n\tNested Item C\n"`
   - Called `createParagraphBullets` on the range
   - **Result:** Tabs remained in text (not removed), all items at level 0

2. **Separate insertText for tabs, then createParagraphBullets**
   - First insert content without tabs
   - Then insert tab characters at start of lines
   - Then call `createParagraphBullets`
   - **Result:** Same - tabs remained, all items at level 0

3. **Consolidated bullet requests (grouping adjacent bullets)**
   - Fixed bug where non-adjacent bullets were grouped together
   - Still didn't fix the nesting level issue

### Observed Behavior

- The tabs (`\t`) are NOT removed by `createParagraphBullets` as documented
- The `nestingLevel` field in the bullet object is not set (defaults to 0)
- The `indentStart` does increase (72pt for items with tabs vs 36pt for level 0)
- Visual appearance shows indentation but semantic nesting level is wrong

### Hypothesis

The tab-based nesting mechanism may:
1. Only work in specific contexts (e.g., Google Docs web UI)
2. Require tabs to exist BEFORE any bullet is created on the paragraph
3. Have undocumented prerequisites or timing requirements
4. Be a bug or limitation in the batchUpdate API

### Impact

- Level 0 bullets work correctly
- Nested bullets (level > 0) will appear visually indented but won't have correct semantic nesting
- Round-trip (pull → push → pull) may not preserve nesting levels correctly

### Workaround

For now, nested bullets are not fully supported. Users can:
1. Use only level 0 bullets
2. Accept that nested bullets will have visual indentation but may not round-trip correctly

### Next Steps

- Search for Google Docs API forum posts about this issue
- Try creating nested bullets via Google Docs UI and examining the API response
- Consider filing a bug report with Google if this is an API issue

## What Is Pending

### Special Elements (Low Priority)
- **Footnotes with precise positioning** - Currently uses `endOfSegmentLocation`, needs text content insertion first for precise index
- **Autotext (page numbers)** - Cannot insert via batchUpdate API, use placeholder `[PAGE]`
- **Images** - Requires separate upload flow
- **Person mentions** - Requires specific personProperties

### Additional Style Support
- Table column width styling
- Table border styling
- Named style definitions (custom heading styles)
- **Nested bullet lists** - See issue documentation above

## Architecture

```
src/extradoc/
├── diff_engine.py          # Orchestration only - calls other modules
├── style_converter.py      # Declarative style mappings + conversion
├── request_generators/     # Request generation by type
│   ├── __init__.py
│   ├── structural.py       # Headers, footers, tabs, footnotes
│   ├── table.py            # Table structure + cell content
│   └── content.py          # Text insertion, paragraph styling
└── client.py               # Two-batch execution with ID tracking
```

## Testing Against Real Google Docs

### Test Document
Use this document for testing: https://docs.google.com/document/d/15dNMijQYl3juFdu8LqLvJoh3K10DREbtUm82489hgAs/edit

### Test Workflow

1. **Pull the document:**
   ```bash
   cd extradoc
   uv run python -m extradoc pull "15dNMijQYl3juFdu8LqLvJoh3K10DREbtUm82489hgAs" output/
   ```

2. **Make edits to the XML:**
   Edit `output/15dNMijQYl3juFdu8LqLvJoh3K10DREbtUm82489hgAs/document.xml`

3. **Preview changes (diff):**
   ```bash
   uv run python -m extradoc diff output/15dNMijQYl3juFdu8LqLvJoh3K10DREbtUm82489hgAs/
   ```
   Save the diff output for debugging:
   ```bash
   uv run python -m extradoc diff output/15dNMijQYl3juFdu8LqLvJoh3K10DREbtUm82489hgAs/ > output/diff.json
   ```

4. **Push changes:**
   ```bash
   uv run python -m extradoc push output/15dNMijQYl3juFdu8LqLvJoh3K10DREbtUm82489hgAs/
   ```

5. **Verify by pulling again:**
   ```bash
   uv run python -m extradoc pull "15dNMijQYl3juFdu8LqLvJoh3K10DREbtUm82489hgAs" output-after/
   ```
   Compare the before and after XML to confirm changes were applied correctly.

### Test Cases to Verify

#### Text Styling
```xml
<!-- Add yellow highlight -->
<p>This is <span class="hilite">highlighted text</span>.</p>

<!-- Where hilite style in styles.xml has: bg="#FFFF00" -->
```

#### Paragraph Styling
```xml
<!-- Centered paragraph -->
<p align="CENTER">This paragraph is centered.</p>

<!-- With spacing -->
<p spaceAbove="12" spaceBelow="6">Paragraph with custom spacing.</p>
```

#### Headings
```xml
<h1>Heading 1</h1>
<h2>Heading 2</h2>
```

#### Lists
```xml
<li type="bullet" level="0">First item</li>
<li type="bullet" level="1">Nested item</li>
<li type="decimal" level="0">Numbered item</li>
```

#### Tables
```xml
<table rows="2" cols="2">
  <tr>
    <td bg="#E0E0E0"><p>Header 1</p></td>
    <td bg="#E0E0E0"><p>Header 2</p></td>
  </tr>
  <tr>
    <td><p>Cell 1</p></td>
    <td><p>Cell 2</p></td>
  </tr>
</table>
```

#### Headers/Footers
```xml
<!-- Add a footer -->
<footer id="new_footer">
  <p>Page footer content</p>
</footer>
```

## Known Limitations

| Feature | Limitation | Workaround |
|---------|------------|------------|
| Autotext (page numbers) | Cannot insert via batchUpdate | Use placeholder `[PAGE]` |
| Person mentions | Requires specific personProperties | Insert as styled text |
| New tabs with content | Requires two-batch (create, then populate) | Documented behavior |
| Horizontal rules | Read-only in Google Docs API | Cannot add/remove, only modify adjacent content |
| Images | Requires separate upload to Drive | Not yet implemented |

## Files Summary

| File | Purpose |
|------|---------|
| `src/extradoc/style_converter.py` | Declarative style mappings + `convert_styles()` |
| `src/extradoc/request_generators/__init__.py` | Package init with exports |
| `src/extradoc/request_generators/structural.py` | Header/footer/tab/footnote requests |
| `src/extradoc/request_generators/table.py` | Table structure + cell styling |
| `src/extradoc/request_generators/content.py` | Text insertion + text/paragraph styling |
| `src/extradoc/diff_engine.py` | Orchestration, uses new modules |
| `src/extradoc/client.py` | Two-batch execution with ID tracking |
