# ExtraDoc Phase 4: Complete Push Implementation

## Status: Core Features Complete

**Last Updated:** 2026-02-06

### Working Features (Verified against real Google Docs)

| Feature | Status | Notes |
|---------|--------|-------|
| Body content (add/modify/delete) | ✅ Working | |
| Text styling (bold, italic, etc.) | ✅ Working | |
| Text highlight colors | ✅ Working | `bg` attribute via `<span class="...">` |
| Bullet lists (including nested) | ✅ Working | Tabs processed for nesting |
| Table cell content | ✅ Working | |
| Table cell borders/backgrounds | ✅ Working | Class-based styles in styles.xml |
| Table column widths | ✅ Working | `<col>` elements for fixed widths |
| Table row add/delete | ✅ Working | |
| Header/footer content | ✅ Working | |
| Footnotes (pull) | ✅ Working | Inline model |

### Partially Working
| Feature | Status | Notes |
|---------|--------|-------|
| Footnotes (push) | 🔄 Needs testing | Code exists, needs end-to-end verification |

### Not Implemented (API Limitations)
| Feature | Status | Notes |
|---------|--------|-------|
| Autotext (page numbers) | ❌ | API doesn't support insertion |
| Images | ❌ | Requires Drive upload flow |
| Person mentions | ❌ | Requires verified email |
| Horizontal rules | ⚠️ Read-only | Cannot add/remove |

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

## Nested Bullet Lists: ✅ WORKING

**Status:** Working correctly with proper understanding of API behavior.

### How It Works

The Google Docs API processes leading tabs (`\t`) to determine nesting levels when calling `createParagraphBullets`. The key insight is **when** this processing occurs:

| Scenario | Tabs Processed? | Nesting Correct? |
|----------|----------------|------------------|
| New list (no adjacent bullets) | ✅ Yes | ✅ Yes |
| Appending to end of list | ✅ Yes | ✅ Yes |
| After non-bullet separator | ✅ Yes | ✅ Yes |
| Delete + re-insert (MODIFY) | ✅ Yes | ✅ Yes |
| Insert middle of existing list | ❌ No | ❌ No |

### The Key Rule

**Tab processing only works when creating a NEW list.** When paragraphs are merged into an existing list (due to adjacency with same preset), tabs are NOT processed.

From the documentation:
> If the paragraph immediately before paragraphs being updated is in a list with a matching preset, the paragraphs being updated are added to that preceding list.

When this merge happens, nesting levels are inherited from context, not computed from tabs.

### Implementation Strategy

For extradoc's push workflow:

1. **MODIFIED ContentBlocks** - Delete first, then insert with tabs → ✅ Works (deletion breaks list continuity)
2. **ADDED ContentBlocks at end** - Insert with tabs → ✅ Works (appends to list correctly)
3. **ADDED ContentBlocks in middle** - Two options:
   - Option A: Insert a non-bullet separator paragraph before/after
   - Option B: Accept that nested items will inherit surrounding nesting level

### Code Example

```python
# This works - text with tabs, then createParagraphBullets
text = "Item 1\n\tItem 1.1\n\tItem 1.2\n\t\tItem 1.2.1\nItem 2\n"
requests = [
    {"insertText": {"location": {"index": 1}, "text": text}},
    {"createParagraphBullets": {
        "range": {"startIndex": 1, "endIndex": 1 + len(text)},
        "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"
    }}
]
# Result: Item 1 (L0), Item 1.1 (L1), Item 1.2 (L1), Item 1.2.1 (L2), Item 2 (L0)
```

### Verified Test Results (2026-02-06)

Tested against document `15dNMijQYl3juFdu8LqLvJoh3K10DREbtUm82489hgAs`:

1. **Clean document insert**: Tabs removed, nesting levels 0/1/2 correct
2. **Append to existing list**: Tabs removed, nesting correct
3. **Delete + re-insert**: Tabs removed, nesting correct (even with changed levels)
4. **Separator paragraph**: Creates new list, tabs processed correctly

## What Is Pending

### Footnotes (Partially Implemented)
**Status:** Pull working, push needs testing

- ✅ **Pull-side:** Inline footnote model working - `<footnote>` tag appears at reference location with content inside
- ✅ **Two-batch workflow:** client.py handles footnote ID mapping for structural operations
- 🔄 **Push-side:** `_generate_special_element_request` handles `footnote` and `footnoteref`, but needs end-to-end testing
- ❓ **Open issue:** block_diff may trigger full content replacement instead of incremental changes when footnotes are added inline

**Next steps:**
1. Test adding a new footnote inline and verify `createFootnote` request generated
2. Test modifying footnote content and verify correct requests
3. Test deleting a footnote

### Special Elements (API Limitations)
These cannot be fully implemented due to Google Docs API limitations:

| Element | Status | Notes |
|---------|--------|-------|
| **Autotext (page numbers)** | ❌ Not supported | Cannot insert via batchUpdate API. Workaround: use placeholder `[PAGE]` |
| **Images** | ❌ Not implemented | Requires separate upload to Drive, then `insertInlineImage` |
| **Person mentions** | ❌ Not implemented | Requires specific `personProperties` with verified email |
| **Horizontal rules** | ⚠️ Read-only | Cannot add/remove via API, only modify adjacent content |

### Needs Design
- **Document-level styles (DocumentStyle)** - Page margins, page size, background color, header/footer margins, page orientation. Uses `UpdateDocumentStyleRequest`. Need to design:
  - How to represent in XML (attributes on `<doc>` element? separate `<documentStyle>` element?)
  - Which properties to expose (margins, page size, background, orientation)
  - How to handle PAGELESS vs paged documents
  - See `docs/googledocs/api/DocumentStyle.md` and `docs/googledocs/api/UpdateDocumentStyleRequest.md`

### Needs Fix
- **Footnote index calculation** - Currently relies on `.raw/document.json` for accurate table indexes when footnotes are present. Should calculate indexes correctly from XML without needing raw API response.

### Needs Testing/Verification
- **Paragraph borders** - Supported in style_converter but not exposed in XML format

### Text Highlight Colors ✅ PUSH WORKING

**Status:** Push working, pull-side style factorization has known issue.

**How it works (Push):**
1. Define a text style in `styles.xml`: `<style id="highlight-yellow" bg="#FFFF00"/>`
2. Use `<span class="highlight-yellow">text</span>` in document.xml
3. Push generates correct `updateTextStyle` request with `backgroundColor`

**Tested (2026-02-06):**
- Added `<span class="highlight-yellow">regular paragraph</span>` to document
- Push generated correct request: `{"updateTextStyle": {"textStyle": {"backgroundColor": {"color": {"rgbColor": {"red": 1.0, "green": 1.0, "blue": 0.0}}}}, "fields": "backgroundColor"}}`
- Raw API response confirmed highlight applied to exact index range (11-28)

**Known issue (Pull-side):**
- Style factorizer may incorrectly merge text highlights into `_base` style instead of preserving as separate text spans
- This is a pull-side issue, not a push-side issue

### Low Priority
- **Named style definitions** - Custom heading styles beyond H1-H6

### Table Column Width Styling ✅ COMPLETE

**Status:** Column width styling working end-to-end.

**How it works:**
1. **Pull-side:** Extracts column widths from `tableStyle.tableColumnProperties`, adds `<col index="N" width="Xpt"/>` elements for FIXED_WIDTH columns
2. **Push-side:** Detects `<col>` element changes, generates `UpdateTableColumnPropertiesRequest`
3. **Uses raw API indexes** from `.raw/document.json` for accurate table positioning

**Example:**
```xml
<table id="cDyp2nz">
  <col index="0" width="150pt"/>
  <tr id="g9SKchj">
    <td id="gUEeXJW" class="cell-jT0KF"><p><b>Header 1</b></p></td>
    <td id="8Jw5e9F" class="cell-OU-ho"><p><b>Header 2</b></p></td>
  </tr>
</table>
```

**Tested (2026-02-06):**
- Added `<col index="0" width="150pt"/>` to table → correct `UpdateTableColumnPropertiesRequest` generated
- Push applied fixed width → verified in Google Docs and on re-pull

### Table Cell Border Styling ✅ COMPLETE

**Status:** Class-based cell styling working end-to-end.

**How it works:**
1. **Pull-side:** Extracts cell styles from Google Docs API, generates style definitions in `styles.xml`, adds `class` attribute to `<td>` elements
2. **Push-side:** Parses `styles.xml`, resolves class attributes to style properties, generates `updateTableCellStyle` requests
3. **Cells processed right-to-left** to prevent index corruption during multi-cell modifications

**Example:**
```xml
<!-- document.xml -->
<td id="gUEeXJW" class="cell-jT0KF"><p><b>Header 1</b></p></td>

<!-- styles.xml -->
<style id="cell-jT0KF" bg="#FFFFCC" borderBottom="2,#FF0000,SOLID"
       borderLeft="2,#FF0000,SOLID" borderRight="2,#FF0000,SOLID"
       borderTop="2,#FF0000,SOLID" paddingBottom="5pt" paddingLeft="5pt"
       paddingRight="5pt" paddingTop="5pt" valign="top"/>
```

**Tested (2026-02-06):**
- Modified cell class to reference a different style → correct `updateTableCellStyle` request generated
- Push applied yellow background and red borders → verified on re-pull

**Files modified:**
- `style_factorizer.py` - Added `extract_cell_style()`, `collect_cell_styles()`, `_factorize_cell_styles()`
- `xml_converter.py` - Added `class` attribute to `<td>` elements
- `diff_engine.py` - Added `parse_cell_styles()`, updated `_generate_cell_style_request()` to resolve class → properties

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
| Footnote index calculation | Inline footnotes affect index calculation | Use raw API indexes from `.raw/document.json` |

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
