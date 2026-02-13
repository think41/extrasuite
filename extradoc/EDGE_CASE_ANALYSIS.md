# Google Docs API Edge Case Analysis

## Purpose
This document catalogs all edge cases and validation rules for Google Docs batchUpdate API based on official documentation, comparing them against our mock implementation in `mock_api.py`.

## Edge Cases from Documentation

### 1. DeleteContentRangeRequest Edge Cases

#### 1.1 Surrogate Pair Protection
**Rule**: Cannot delete one code unit of a surrogate pair (emoji, certain Unicode chars consume 2 UTF-16 units)
**Current Implementation**: ❌ NOT IMPLEMENTED
**Priority**: HIGH
**Test Needed**: Delete operation that would split 😀 emoji (2 UTF-16 units)

#### 1.2 Final Newline Protection
**Rule**: Cannot delete the last newline character from:
- Body
- Header
- Footer
- Footnote
- TableCell
- TableOfContents

**Current Implementation**: ✅ PARTIALLY IMPLEMENTED
- Body: ✅ Implemented (line 1775-1780)
- Header/Footer/Footnote: ✅ Implemented (uses same segment validation)
- TableCell: ❌ NOT IMPLEMENTED
- TableOfContents: ❌ NOT IMPLEMENTED

**Priority**: HIGH
**Test Needed**:
- Try deleting final newline from table cell
- Try deleting final newline from table of contents

#### 1.3 Partial Structural Element Deletion
**Rule**: Cannot delete start or end of these without deleting entire element:
- Table
- TableOfContents
- Equation

**Current Implementation**: ✅ PARTIALLY IMPLEMENTED
- Table: ✅ Implemented (lines 1788-1796)
- TableOfContents: ❌ NOT IMPLEMENTED
- Equation: ❌ NOT IMPLEMENTED

**Priority**: MEDIUM
**Test Needed**:
- Try partially deleting TableOfContents
- Try partially deleting Equation

#### 1.4 Newline Before Structural Elements
**Rule**: Cannot delete newline before these without deleting entire element:
- Table
- TableOfContents
- SectionBreak

**Current Implementation**: ✅ PARTIALLY IMPLEMENTED
- Table: ✅ Implemented (lines 1799-1802)
- TableOfContents: ❌ NOT IMPLEMENTED
- SectionBreak: ❌ NOT IMPLEMENTED

**Priority**: MEDIUM
**Test Needed**:
- Try deleting newline before TableOfContents
- Try deleting newline before SectionBreak

#### 1.5 Individual Table Parts
**Rule**: Cannot delete individual table rows or cells
- Content WITHIN cells can be deleted
- Whole rows/columns can only be deleted via specific requests

**Current Implementation**: ❌ NOT IMPLEMENTED
**Priority**: MEDIUM
**Test Needed**: Try deleting a range that encompasses only part of a table row

#### 1.6 Paragraph Boundary Crossing
**Rule**: Deleting across paragraph boundaries may:
- Merge paragraph styles
- Merge or split lists
- Affect positioned objects
- Modify bookmarks

**Current Implementation**: ❌ NOT IMPLEMENTED (no validation, but also no state updates)
**Priority**: LOW (validation-only mock doesn't need to track these changes)

### 2. InsertTextRequest Edge Cases

#### 2.1 Paragraph Boundary Requirement
**Rule**: Text must be inserted inside existing paragraph bounds
- Cannot insert at table's start index
- Must insert in preceding paragraph instead

**Current Implementation**: ✅ IMPLEMENTED (lines 1722-1730)
**Priority**: HIGH
**Test Coverage**: ✅ test_insert_text_at_table_start_fails (NEEDED)

#### 2.2 Control Character Stripping
**Rule**: These characters are automatically stripped:
- U+0000-U+0008
- U+000C-U+001F

**Current Implementation**: ✅ IMPLEMENTED (line 1570)
**Priority**: HIGH
**Test Coverage**: ✅ test_insert_text_strips_control_characters (lines 180-193)

#### 2.3 Private Use Area Stripping
**Rule**: U+E000-U+F8FF are stripped from inserted text

**Current Implementation**: ✅ IMPLEMENTED (line 1572)
**Priority**: MEDIUM
**Test Coverage**: ❌ MISSING

#### 2.4 Newline Creates Paragraph
**Rule**: Inserting \n creates new paragraph with copied style from current position

**Current Implementation**: ❌ NOT IMPLEMENTED (validation only, no structure updates)
**Priority**: LOW (would need full document structure updates)

#### 2.5 Grapheme Cluster Preservation
**Rule**: System may shift insertion points to avoid splitting grapheme clusters (e.g., emoji with skin tone modifiers)

**Current Implementation**: ❌ NOT IMPLEMENTED
**Priority**: LOW (complex Unicode handling)

### 3. Index Space and Segmentation

#### 3.1 Separate Segment Indexing
**Rule**: Each segment has independent index space starting at 1:
- Body
- Each Header (by ID)
- Each Footer (by ID)
- Each Footnote (by ID)

**Current Implementation**: ✅ IMPLEMENTED
- `_get_segment()` properly isolates segments (lines 1602-1641)
**Priority**: HIGH
**Test Coverage**: ✅ Implicit in existing tests

#### 3.2 Tab Isolation
**Rule**: Each tab maintains separate content and index spaces

**Current Implementation**: ✅ IMPLEMENTED
- `_get_tab()` validates tab isolation (lines 1575-1600)
**Priority**: HIGH
**Test Coverage**: ✅ test_invalid_tab_id, test_explicit_tab_id (lines 747-773)

### 4. Image Insertion Edge Cases

#### 4.1 File Size Limit
**Rule**: Images must be under 50 MB

**Current Implementation**: ❌ NOT IMPLEMENTED
**Priority**: LOW (validation-only mock, can't check actual image size from URI)

#### 4.2 Resolution Limit
**Rule**: Images must not exceed 25 megapixels

**Current Implementation**: ❌ NOT IMPLEMENTED
**Priority**: LOW (same reason as 4.1)

#### 4.3 Format Restriction
**Rule**: Only PNG, JPEG, GIF formats allowed

**Current Implementation**: ❌ NOT IMPLEMENTED
**Priority**: LOW (can't determine format from URI alone)

#### 4.4 URI Size Limit
**Rule**: URI must be under 2 KB (2048 characters)

**Current Implementation**: ✅ IMPLEMENTED (lines 1275-1276, 1495-1496)
**Priority**: HIGH
**Test Coverage**: ✅ test_insert_inline_image_uri_too_long (lines 1470-1482)

#### 4.5 Location Restrictions - Footnotes
**Rule**: Cannot insert images in footnotes

**Current Implementation**: ✅ IMPLEMENTED (lines 1285-1289)
**Priority**: MEDIUM
**Test Coverage**: ❌ MISSING

#### 4.6 Location Restrictions - Equations
**Rule**: Cannot insert images in equations

**Current Implementation**: ❌ NOT IMPLEMENTED
**Priority**: LOW (equations not tracked in mock)

#### 4.7 Paragraph Boundary Requirement
**Rule**: Images must be inserted inside paragraph bounds (like text)

**Current Implementation**: ✅ IMPLEMENTED (index validation via _insert_text_impl pattern)
**Priority**: HIGH
**Test Coverage**: ❌ MISSING

### 5. UTF-16 Indexing

#### 5.1 Surrogate Pairs Consume 2 Units
**Rule**: Emoji and certain Unicode consume 2 index units
- Example: "😀" = 2 units
- Example: "A" = 1 unit
- Example: "Hello😀World" = 12 units (5+2+5)

**Current Implementation**: ✅ HELPER AVAILABLE
- `utf16_len()` imported from extradoc.indexer (line 24)
- Used for named range validation (line 545)
**Priority**: HIGH
**Test Coverage**: ❌ MISSING comprehensive surrogate pair tests

#### 5.2 Zero-Based vs One-Based Indexing
**Rule**: Index 0 is reserved; valid content starts at index 1

**Current Implementation**: ✅ IMPLEMENTED
- Multiple validations check `index >= 1` (lines 1492, 1656, etc.)
**Priority**: HIGH
**Test Coverage**: ✅ test_insert_text_invalid_index (lines 213-224)

### 6. Range Validation

#### 6.1 StartIndex < EndIndex
**Rule**: endIndex must be strictly greater than startIndex

**Current Implementation**: ✅ IMPLEMENTED (lines 1658-1661, 1760-1763)
**Priority**: HIGH
**Test Coverage**: ✅ test_delete_content_range_invalid_range (lines 293-304)

#### 6.2 Within Bounds
**Rule**: Ranges cannot exceed segment length

**Current Implementation**: ✅ IMPLEMENTED (lines 1669-1674)
**Priority**: HIGH
**Test Coverage**: ✅ Implicit in various tests

#### 6.3 Minimum Index
**Rule**: startIndex must be at least 1

**Current Implementation**: ✅ IMPLEMENTED (lines 1656-1657, 1759)
**Priority**: HIGH
**Test Coverage**: ✅ Multiple tests

### 7. Segment-Specific Restrictions

#### 7.1 Page Breaks Only in Body
**Rule**: Page breaks cannot be inserted in headers, footers, or footnotes

**Current Implementation**: ✅ IMPLEMENTED (lines 1331-1335)
**Priority**: MEDIUM
**Test Coverage**: ✅ test_insert_page_break_in_header_fails (lines 1497-1513)

#### 7.2 Section Breaks Only in Body
**Rule**: Section breaks cannot be inserted in headers, footers, or footnotes

**Current Implementation**: ✅ IMPLEMENTED (lines 1376-1380)
**Priority**: MEDIUM
**Test Coverage**: ✅ test_insert_section_break_in_footer_fails (lines 1543-1566)

#### 7.3 Footnotes Cannot Be Nested
**Rule**: Cannot create footnotes in headers, footers, or other footnotes

**Current Implementation**: ✅ IMPLEMENTED (lines 849-853)
**Priority**: MEDIUM
**Test Coverage**: ✅ test_create_footnote_in_header_fails (lines 984-1000)

#### 7.4 Section Styles Only in Body
**Rule**: Section styles can only be applied to body, not headers/footers/footnotes

**Current Implementation**: ✅ IMPLEMENTED (lines 1117-1122)
**Priority**: MEDIUM
**Test Coverage**: ✅ test_update_section_style_in_header_fails (lines 1251-1275)

### 8. Table-Specific Edge Cases

#### 8.1 Column Width Minimum
**Rule**: Column width must be at least 5 points

**Current Implementation**: ✅ IMPLEMENTED (lines 988-994)
**Priority**: MEDIUM
**Test Coverage**: ✅ test_update_table_column_properties_too_narrow (lines 1069-1090)

#### 8.2 Positive Dimensions
**Rule**: Tables must have rows >= 1 and columns >= 1

**Current Implementation**: ✅ IMPLEMENTED (lines 471-474)
**Priority**: HIGH
**Test Coverage**: ✅ test_insert_table_invalid_dimensions (lines 460-471)

#### 8.3 Cannot Insert at Table Boundary
**Rule**: Cannot insert text at table's startIndex (covered in 2.1)

**Current Implementation**: ✅ IMPLEMENTED (lines 1722-1730)
**Priority**: HIGH
**Test Coverage**: ❌ MISSING

### 9. Additional Edge Cases from API Docs

#### 9.1 Named Range Name Length
**Rule**: Named range names must be 1-256 UTF-16 code units

**Current Implementation**: ✅ IMPLEMENTED (lines 544-549)
**Priority**: MEDIUM
**Test Coverage**: ✅ test_create_named_range_validates_name_length (lines 514-532)

#### 9.2 TableOfContents Handling
**Rule**: TableOfContents is a special structural element with protection rules

**Current Implementation**: ❌ NOT IMPLEMENTED
**Priority**: MEDIUM
**Test Coverage**: ❌ MISSING

#### 9.3 Equation Handling
**Rule**: Equations are special structural elements with protection rules

**Current Implementation**: ❌ NOT IMPLEMENTED
**Priority**: MEDIUM
**Test Coverage**: ❌ MISSING

#### 9.4 SectionBreak Protection
**Rule**: Cannot delete newline before SectionBreak without deleting the break

**Current Implementation**: ❌ NOT IMPLEMENTED
**Priority**: MEDIUM
**Test Coverage**: ❌ MISSING

## Summary

### ✅ Well Implemented (15 cases)
- Final newline protection (body, header, footer, footnote)
- Partial table deletion
- Newline before table
- Paragraph boundary for insert
- Control character stripping
- Private use area stripping
- Segment isolation
- Tab isolation
- URI size limit
- Footnote location restrictions
- Index validation (>= 1, within bounds, start < end)
- Segment-specific restrictions (page breaks, section breaks, footnotes, section styles)
- Table column width minimum
- Table dimensions positive
- Named range name length

### ❌ Missing Implementation (11 cases)
1. **Surrogate pair splitting protection** (HIGH priority)
2. **Final newline in TableCell** (HIGH priority)
3. **Final newline in TableOfContents** (MEDIUM priority)
4. **Partial TableOfContents deletion** (MEDIUM priority)
5. **Partial Equation deletion** (MEDIUM priority)
6. **Newline before TableOfContents** (MEDIUM priority)
7. **Newline before SectionBreak** (MEDIUM priority)
8. **Individual table row/cell deletion** (MEDIUM priority)
9. **Image in equation restriction** (LOW priority)
10. **Grapheme cluster preservation** (LOW priority)
11. **Image file validation** (LOW priority - can't check from URI)

### 🧪 Missing Tests (8 areas)
1. Private use area character stripping
2. Image in footnote restriction
3. Image at paragraph boundary
4. Comprehensive surrogate pair tests
5. Insert at table boundary
6. TableOfContents operations
7. Equation operations
8. SectionBreak protection

## Implementation Priority

### Phase 1: Critical (High Priority)
1. Surrogate pair splitting protection in DeleteContentRange
2. TableCell final newline protection
3. Test: Insert at table boundary
4. Test: Comprehensive surrogate pair handling

### Phase 2: Important (Medium Priority)
5. TableOfContents structure tracking and protection
6. SectionBreak structure tracking and protection
7. Equation structure tracking and protection
8. Individual table row/cell deletion validation
9. Tests for all TableOfContents/SectionBreak/Equation cases

### Phase 3: Nice to Have (Low Priority)
10. Grapheme cluster preservation
11. Image in equation restriction
12. Additional edge case tests

## Recommendations

1. **Immediate Action**: Implement Phase 1 items as they represent critical data corruption risks
2. **Document Structure Enhancement**: Consider adding a document walker that tracks all structural elements (tables, TableOfContents, equations, section breaks) to enable proper validation
3. **Test Coverage**: Add comprehensive tests for surrogate pairs, structural elements, and boundary conditions
4. **Mock Fidelity**: The mock should reject the same operations that the real API rejects, even if it doesn't update internal state
