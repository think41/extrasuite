# ExtraDoc True Diff Engine - Architecture v2

## Goal

Generate **minimal, correct batchUpdate requests** by computing indexes against a working document state that evolves as we process changes, rather than computing all indexes against the static pristine document.

## The Index Drift Problem (Why v1 Failed)

The fundamental issue with v1: **Insert indexes from different change blocks are all based on PRISTINE positions, but they're applied to a document that has been modified by prior operations.**

Example:
```
Pristine: [A at 0-10] [B at 10-20] [C at 20-30]
Edited:   [A' at 0-15] [B at 15-25] [C' at 25-35]

V1 approach (broken):
1. Generate: Delete A[0-10], Insert A' at 0
2. Generate: Delete C[20-30], Insert C' at 20  ← Uses pristine index 20!
3. After sorting and applying:
   - Delete C[20-30] ✓
   - Delete A[0-10] ✓
   - Insert A' at 0 ✓
   - Insert C' at 20 ✗ ← Document has changed! Index 20 is wrong!
```

## The Solution: Bottom-Up Processing with Working XML

### Core Insight

Process changes from the **bottom of the document upward**. Changes at higher indexes don't affect lower indexes. After processing each change, we copy the corresponding region from the edited XML to our working copy.

```
working_xml = copy(pristine_xml)

for each change (bottom-up by pristine index):
    1. Compute indexes from working_xml (accurate for this region)
    2. Generate operations for this change
    3. Copy region from edited_xml to working_xml
    4. Queue operations

send_all(operations)  # In order we generated them
```

### Why This Works

1. **Bottom-up eliminates cross-chunk drift**: When we process index 20-30, indexes 0-19 are untouched in working_xml
2. **Copy = Apply**: The operations transform pristine → edited, so the edited XML IS the result
3. **No offset tracking**: Each index calculation is simple (just read from working_xml)
4. **Matches Google's model**: Operations are generated in the order they'll be applied

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        diff_documents()                              │
│  Entry point: pristine_xml, current_xml → list[batchUpdate]         │
│  - Parse both documents                                              │
│  - Process each segment independently (body, headers, footers)       │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Segment Diffing (per segment)                     │
│  Each segment has its own index space starting at 0 (body at 1)     │
│  - Sequence diff to identify change blocks                           │
│  - Process blocks BOTTOM-UP by pristine index                        │
│  - Maintain working_elements that evolves with each change           │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Change Block Processing                           │
│  For each change block (in reverse order):                          │
│  - EQUAL: Check for subtle style differences                         │
│  - DELETE: Delete elements, remove from working_elements             │
│  - INSERT: Insert at position in working_elements, add to working   │
│  - REPLACE: Delete old, insert new, update working_elements          │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Element Diffing (same type)                       │
│  When pristine and current elements have same type:                  │
│  - Paragraph: diff text + styles (existing logic works)             │
│  - Table: diff structure or cell-by-cell                            │
│  - Special: compare attributes                                       │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Request Generation                                │
│  Operations are already in correct order (bottom-up)                 │
│  - Convert DiffOperations to batchUpdate JSON                        │
│  - No re-sorting needed!                                             │
└─────────────────────────────────────────────────────────────────────┘
```

## Processing Order Rules

| Change Type | Processing Order | Index Source | Working XML Update |
|-------------|------------------|--------------|-------------------|
| **Replace/Modify** | Bottom-up by pristine index | working_elements | Replace element |
| **Delete (bulk)** | Bottom-up by pristine index | Pristine index (still valid) | Remove elements |
| **Insert (bulk)** | **Reverse order** (last element first) at same position | Insertion point in working_elements | Add elements |
| **Equal** | Skip (but check for style-only changes) | N/A | No change |

### Why Insert Bulk Uses Reverse Order

```
Pristine: [A, B, C]
Edited:   [A, B, X, Y, Z, C]

Processing (bottom-up, then reverse for inserts):
1. C: unchanged
2. Z: Insert at position after B (index 20)
3. Y: Insert at position after B (index 20) → pushes Z right
4. X: Insert at position after B (index 20) → pushes Y, Z right
5. B: unchanged
6. A: unchanged

Result in working_xml: [A, B, X, Y, Z, C] ✓
```

Each insert at the same position pushes previous insertions to the right, achieving correct order.

## One Line Per Element XML Format

Structure the XML so each element is on its own line. This makes diff hunks map cleanly to elements:

```xml
<doc>
<body>
<p style="h1">Resume</p>
<p>John Doe | Engineer</p>
<p style="h2">Summary</p>
<p>Experienced engineer with 8+ years.</p>
<table rows="2" cols="2">...</table>
<p>Final paragraph.</p>
</body>
</doc>
```

Benefits:
1. **Clean diff hunks**: Each changed element is its own hunk
2. **Easy element extraction**: Parse line-by-line
3. **Predictable structure**: A hunk = an element change
4. **Composable testing**: Test each element type independently

## Complete batchUpdate Operations Catalog

Google Docs API provides **41 batchUpdate operations**. Here's our support plan:

### MUST SUPPORT (Core Diff Operations)

| Change Type | batchUpdate Request | Notes |
|-------------|---------------------|-------|
| Text inserted | `InsertText` | Core text operation |
| Text deleted | `DeleteContentRange` | Core text operation |
| Text replaced | Delete + Insert at same index | Compound operation |
| Bold/italic/underline/etc | `UpdateTextStyle` | With field mask |
| Font/size/color change | `UpdateTextStyle` | With field mask |
| Heading style (H1-H6) | `UpdateParagraphStyle` | namedStyleType field |
| Bullet added | `CreateParagraphBullets` | With bullet preset |
| Bullet removed | `DeleteParagraphBullets` | Range-based |
| Page break inserted | `InsertPageBreak` | Body only, not in tables/footnotes |
| Section break inserted | `InsertSectionBreak` | Creates new section |
| Header created | `CreateHeader` | DEFAULT type |
| Header deleted | `DeleteHeader` | By header ID |
| Footer created | `CreateFooter` | DEFAULT type |
| Footer deleted | `DeleteFooter` | By footer ID |
| Footnote created | `CreateFootnote` | Inserts reference + creates segment |
| Image inserted | `InsertInlineImage` | PNG/JPEG/GIF, <50MB |
| Person mention | `InsertPerson` | @mentions |
| Date field | `InsertDate` | With format/timezone |
| Table inserted | `InsertTable` | Rows + columns |
| Table row added | `InsertTableRow` | Above or below |
| Table row deleted | `DeleteTableRow` | By cell location |
| Table column added | `InsertTableColumn` | Left or right |
| Table column deleted | `DeleteTableColumn` | By cell location |
| Table cell styling | `UpdateTableCellStyle` | Background, borders |
| Table column width | `UpdateTableColumnProperties` | Width, widthType |
| Table row height | `UpdateTableRowStyle` | Min height |

### MUST SUPPORT (Advanced Operations)

| Change Type | batchUpdate Request | Detection Method |
|-------------|---------------------|------------------|
| Cell merged | `MergeTableCells` | `rowspan`/`colspan` increased in current vs pristine |
| Cell unmerged | `UnmergeTableCells` | `rowspan`/`colspan` decreased in current vs pristine |
| Image replaced | `ReplaceImage` | Same `data-object-id` but different `src` |
| Document style changed | `UpdateDocumentStyle` | Diff `styles.xml` document-level properties |
| Section style changed | `UpdateSectionStyle` | Diff `styles.xml` section-level properties |
| Tab added | `AddDocumentTab` | New `<tab>` element in current XML |
| Tab deleted | `DeleteTab` | `<tab>` element removed from current XML |
| Tab properties changed | `UpdateDocumentTabProperties` | `<tab>` attributes differ (title, index) |

### DEFER (Complex/Edge Cases)

| Operation | Reason |
|-----------|--------|
| `PinTableHeaderRows` | Display property, rarely used |
| `DeletePositionedObject` | Positioned (anchored) objects, not inline |

### OUT OF SCOPE (Imperative/Meta Operations)

| Operation | Reason |
|-----------|--------|
| `ReplaceAllText` | Global find/replace, not diff-based |
| `CreateNamedRange` | Metadata, not visible content |
| `DeleteNamedRange` | Metadata |
| `ReplaceNamedRangeContent` | Metadata |

## Constraints from Google Docs API

1. **Last paragraph rule**: Cannot delete final newline in body/header/footer/footnote/cell
2. **UTF-16 indexing**: All indexes use UTF-16 code units (surrogate pairs = 2)
3. **Segment isolation**: Headers/footers/footnotes each have separate index spaces starting at 0
4. **HR is read-only**: Horizontal rules cannot be inserted via API (only styled paragraphs)
5. **Body starts at 1**: Body segment indexes start at 1, not 0

## Implementation Status

### Phase 1: Core Infrastructure ✅ IMPLEMENTED

- [x] `sequence_diff.py` with element signature matching
- [x] `DiffChange` dataclass for change blocks
- [x] Basic `diff_documents()` entry point
- [x] Section-level diffing framework

### Phase 2: Paragraph & Text Diffing ✅ IMPLEMENTED

- [x] `diff_paragraph()` for content and style changes
- [x] Character-level `diff_text()`
- [x] `diff_run_styles()` for style-only changes
- [x] Named style and bullet handling

### Phase 3: Fix Index Drift (THIS PHASE) 🔄 IN PROGRESS

**Goal**: Implement bottom-up processing with working XML to eliminate index drift.

**Changes Required**:

1. **Refactor `_diff_section()`** to process change blocks bottom-up:
   ```python
   def _diff_section(pristine: Section, current: Section) -> list[DiffOperation]:
       # Get change blocks from sequence_diff
       diff_result = sequence_diff(p_elements, c_elements)

       # Reverse to process bottom-up
       diff_result_reversed = list(reversed(diff_result))

       # Maintain working elements (copy of pristine)
       working_elements = list(p_elements)  # [(elem, start, end), ...]

       operations = []
       for change in diff_result_reversed:
           if change.type == "equal":
               # Check for style-only differences
               ...
           elif change.type == "delete":
               ops = process_delete(change, working_elements)
               operations.extend(ops)
               # Remove from working_elements
               ...
           elif change.type == "insert":
               ops = process_insert(change, working_elements)
               operations.extend(ops)
               # Add to working_elements
               ...
           elif change.type == "replace":
               ops = process_replace(change, working_elements)
               operations.extend(ops)
               # Update working_elements
               ...

       # Operations are already in correct order!
       return operations
   ```

2. **Implement `_recompute_indexes(working_elements)`**:
   - Recalculate start/end indexes for all elements in working_elements
   - Called after each modification to working_elements

3. **Handle bulk insertions correctly**:
   - Insert elements in REVERSE order at the same position
   - Each insert pushes previous insertions to the right

4. **Handle bulk deletions correctly**:
   - Delete in bottom-up order (already natural from reversed processing)

**Exit Criteria**:
- Multi-block changes produce correct output
- Bulk insertions work correctly
- Bulk deletions work correctly
- Existing tests still pass

### Phase 4: Special Elements

1. Page breaks: `InsertPageBreak` (body only constraint)
2. Section breaks: `InsertSectionBreak`
3. Footnotes: `CreateFootnote` (creates reference + segment)
4. Images: `InsertInlineImage`
5. Person mentions: `InsertPerson`
6. Date fields: `InsertDate`

**Exit Criteria**: Each special element type can be added/removed

### Phase 5: Headers, Footers, Footnotes

1. Header/Footer creation: `CreateHeader` / `CreateFooter`
2. Header/Footer deletion: `DeleteHeader` / `DeleteFooter`
3. Content diffing within headers/footers (separate index space)
4. Footnote content diffing (separate index space per footnote)

**Exit Criteria**: Header added → CreateHeader + content; Content within header changed → minimal updates

### Phase 6: Tables

1. Implement `diff_table()`:
   - Same structure → diff cell by cell
   - Row added → `InsertTableRow`
   - Row deleted → `DeleteTableRow`
   - Column added → `InsertTableColumn`
   - Column deleted → `DeleteTableColumn`
   - Structure completely changed → delete + `InsertTable`

2. Implement `diff_cell_content()`:
   - Apply paragraph diffing to cell content
   - Cell styling → `UpdateTableCellStyle`

3. Implement table property changes:
   - Column width → `UpdateTableColumnProperties`
   - Row height → `UpdateTableRowStyle`

4. Implement cell merge/unmerge:
   - Detect `rowspan`/`colspan` changes per cell
   - `rowspan`/`colspan` increased → `MergeTableCells`
   - `rowspan`/`colspan` decreased → `UnmergeTableCells`

**Exit Criteria**: Cell text change → minimal update; Row added → InsertTableRow; Cell merged → MergeTableCells

### Phase 7: Document & Tab Level

1. Implement tab diffing:
   - Tab added → `AddDocumentTab`
   - Tab deleted → `DeleteTab`
   - Tab properties changed → `UpdateDocumentTabProperties`

2. Implement styles.xml diffing:
   - Document styles → `UpdateDocumentStyle`
   - Section styles → `UpdateSectionStyle`

3. Implement image replacement:
   - Same `data-object-id` but different `src` → `ReplaceImage`

**Exit Criteria**: Tab added → AddDocumentTab; Document margin changed → UpdateDocumentStyle

### Phase 8: Edge Cases & Polish

1. Last paragraph rule enforcement (already implemented)
2. Empty paragraph handling
3. HR (horizontal rule) - read-only handling
4. Performance optimization for large documents
5. Multi-tab index handling (each tab has independent body index space)

## Key Algorithms

### Bottom-Up Change Processing

```python
def process_changes_bottom_up(diff_result, p_elements, c_elements, segment_id):
    """Process change blocks from bottom of document upward."""
    operations = []

    # Copy pristine elements as our working state
    working = [(elem, start, end) for elem, start, end in p_elements]

    # Process in reverse order (bottom-up)
    for change in reversed(diff_result):
        if change.type == "equal":
            # May still have style differences - check and handle
            continue

        elif change.type == "delete":
            # Find elements to delete in working (by pristine index range)
            for p_elem in reversed(change.pristine_elements):
                idx = find_element_index(working, p_elem)
                if idx is not None:
                    elem, start, end = working[idx]
                    operations.append(make_delete_op(start, end, segment_id))
                    working.pop(idx)
            # Recompute indexes after deletion
            recompute_indexes(working)

        elif change.type == "insert":
            # Find insertion point in working
            insert_point = find_insert_point(working, change)
            insert_idx = get_index_at_point(working, insert_point)

            # Insert elements in REVERSE order at same position
            for c_elem in reversed(change.current_elements):
                ops, length = emit_element(c_elem, insert_idx, segment_id)
                operations.extend(ops)
                # Insert into working at the same position
                working.insert(insert_point, (c_elem, insert_idx, insert_idx + length))
            # Recompute indexes
            recompute_indexes(working)

        elif change.type == "replace":
            # Delete old elements (bottom-up)
            for p_elem in reversed(change.pristine_elements):
                idx = find_element_index(working, p_elem)
                if idx is not None:
                    elem, start, end = working[idx]
                    operations.append(make_delete_op(start, end, segment_id))
                    working.pop(idx)

            # Recompute after deletions
            recompute_indexes(working)

            # Insert new elements (reverse order)
            insert_point = find_insert_point_for_replace(working, change)
            insert_idx = get_index_at_point(working, insert_point)

            for c_elem in reversed(change.current_elements):
                ops, length = emit_element(c_elem, insert_idx, segment_id)
                operations.extend(ops)
                working.insert(insert_point, (c_elem, insert_idx, insert_idx + length))

            recompute_indexes(working)

    return operations


def recompute_indexes(working, section_type="body"):
    """Recompute all element indexes in working list."""
    current_idx = 1 if section_type == "body" else 0

    for i, (elem, _, _) in enumerate(working):
        start = current_idx
        end = start + element_length(elem)
        working[i] = (elem, start, end)
        current_idx = end
```

### Bulk Insert Example

```
Pristine: [A, B, C] with indexes [0-10, 10-20, 20-30]
Edited:   [A, B, X, Y, Z, C]

Sequence diff: [equal(A,B), insert(X,Y,Z), equal(C)]

Processing (reversed):
1. equal(C) - skip
2. insert(X,Y,Z) at position after B:
   - working = [(A,0,10), (B,10,20), (C,20,30)]
   - insert_point = 2 (after B, before C)
   - insert_idx = 20 (end of B)

   Insert Z at 20: ops += [InsertText(20, "Z\n")]
   working.insert(2, (Z, 20, 22))
   recompute → [(A,0,10), (B,10,20), (Z,20,22), (C,22,32)]

   Insert Y at 20: ops += [InsertText(20, "Y\n")]
   working.insert(2, (Y, 20, 22))
   recompute → [(A,0,10), (B,10,20), (Y,20,22), (Z,22,24), (C,24,34)]

   Insert X at 20: ops += [InsertText(20, "X\n")]
   working.insert(2, (X, 20, 22))
   recompute → [(A,0,10), (B,10,20), (X,20,22), (Y,22,24), (Z,24,26), (C,26,36)]

3. equal(A,B) - skip

Final operations (in generation order):
1. InsertText(20, "Z\n")
2. InsertText(20, "Y\n")
3. InsertText(20, "X\n")

When Google applies these:
- Insert Z at 20 → [A, B, Z, C]
- Insert Y at 20 → [A, B, Y, Z, C]
- Insert X at 20 → [A, B, X, Y, Z, C] ✓
```

## Helper Functions Specification

### `find_element_index(working, element)`

Find the list index of an element in working_elements by identity (not equality).

```python
def find_element_index(working: list[tuple[Any, int, int]], element: Any) -> int | None:
    """Find the list index of element in working by identity."""
    for i, (elem, _, _) in enumerate(working):
        if elem is element:  # Identity check, not equality
            return i
    return None
```

### `find_insert_point(working, change)`

Determine where to insert new elements. The insertion point is the list index where new elements should be inserted (before that position).

```python
def find_insert_point(working: list[tuple[Any, int, int]], change: DiffChange) -> int:
    """Find list index where new elements should be inserted.

    For an insert change, we need to find where in working_elements the
    new content should go. This is typically after the last "equal" element
    that precedes this insert in the original diff.

    Returns: List index (0 to len(working)) where insert() should place elements.
    """
    # The change has pristine_start which tells us the character index
    # where insertion should happen. Find the element that ends at or
    # contains this index.
    target_idx = change.pristine_start

    for i, (elem, start, end) in enumerate(working):
        if end >= target_idx:
            return i  # Insert before this element

    return len(working)  # Insert at end
```

### `get_index_at_point(working, insert_point)`

Get the character index for insertion given a list position.

```python
def get_index_at_point(working: list[tuple[Any, int, int]], insert_point: int) -> int:
    """Get character index for insertion at list position."""
    if insert_point == 0:
        return 1  # Body starts at 1 (or 0 for other segments)
    if insert_point >= len(working):
        # Insert at end - use end of last element
        if working:
            return working[-1][2]
        return 1
    # Insert before element at insert_point - use its start index
    return working[insert_point][1]
```

## Edge Cases

### Empty Documents
- Pristine empty, current has content → Insert all content
- Pristine has content, current empty → Delete all (respecting last paragraph rule)
- Both empty → No operations

### Single Element
- One paragraph changed → Standard paragraph diff
- One paragraph deleted → Delete (if not last)
- One paragraph added → Insert

### Element Type Changes
When an element changes type (e.g., paragraph → table):
- Sequence diff will report as "replace" (delete old + insert new)
- This is correct behavior - no special handling needed

### Mixed Change Blocks
When a replace block has different counts:
- Pristine: [A, B] → Current: [X, Y, Z]
- Delete A, B (bottom-up: B first, then A)
- Insert X, Y, Z (reverse: Z, Y, X at same position)

### Style-Only Changes in "Equal" Blocks
Elements may have same signature but different styles:
```python
# In process_equal():
for p_elem, c_elem in zip(change.pristine_elements, change.current_elements):
    if not deep_elements_match(p_elem, c_elem):
        # Same text, different styles - generate style updates
        ops = diff_element_styles(p_elem, c_elem, ...)
        operations.extend(ops)
```

### Last Paragraph Rule
- Never delete the structural newline at segment end
- If deleting would leave segment empty, keep one empty paragraph
- Already implemented in `_enforce_last_paragraph_rule()`

### Tables Within Cells
Table cells can contain multiple paragraphs or nested tables:
- Each cell is a mini-segment with its own content
- Apply the same diff logic recursively
- Cell index space is part of the parent table's index space

## Files Summary

| File | Status | Description |
|------|--------|-------------|
| `src/extradoc/diff_engine.py` | Modify | Implement bottom-up processing |
| `src/extradoc/sequence_diff.py` | Keep | Already works correctly |
| `src/extradoc/desugar.py` | Keep | Already works correctly |
| `tests/test_diff_engine.py` | Add | Tests for multi-block changes |

---

## Testing Guide

### Test Documents

Use these real Google Docs for integration testing:

| Document | URL | Purpose |
|----------|-----|---------|
| Basic Test Doc | https://docs.google.com/document/d/1eFtqhZbBwZgxKZPLSbfgDVgcrEk1p-xipMJT7XxFHV8/edit | Simple paragraphs, basic formatting |
| Comprehensive Test | https://docs.google.com/document/d/15dNMijQYl3juFdu8LqLvJoh3K10DREbtUm82489hgAs/edit | Tables, headers, footers, all element types |

### Test Categories

#### 1. Unit Tests (No API Calls)

Test pure diff logic with constructed XML:

```python
# tests/test_diff_engine.py

class TestBottomUpProcessing:
    """Tests for the bottom-up processing algorithm."""

    def test_identical_documents_no_requests(self):
        """Identical documents produce zero requests."""
        xml = '<doc><body><p>Hello World</p></body></doc>'
        requests = diff_documents(xml, xml)
        assert requests == []

    def test_single_paragraph_text_change(self):
        """Single paragraph text change generates minimal ops."""
        pristine = '<doc><body><p>Hello World</p></body></doc>'
        current = '<doc><body><p>Hello Universe</p></body></doc>'
        requests = diff_documents(pristine, current)
        # Verify delete + insert for changed word only
        assert any('deleteContentRange' in r for r in requests)
        assert any('insertText' in r for r in requests)

    def test_bulk_insert_middle(self):
        """Inserting multiple elements in middle works correctly."""
        pristine = '<doc><body><p>A</p><p>B</p><p>C</p></body></doc>'
        current = '<doc><body><p>A</p><p>B</p><p>X</p><p>Y</p><p>Z</p><p>C</p></body></doc>'
        requests = diff_documents(pristine, current)

        # Should have 3 InsertText operations
        inserts = [r for r in requests if 'insertText' in r]
        assert len(inserts) == 3

        # All inserts should be at the same base index (before adjustments)
        # The order should be Z, Y, X (reverse) so Google applies them correctly

    def test_bulk_delete_middle(self):
        """Deleting multiple elements from middle works correctly."""
        pristine = '<doc><body><p>A</p><p>X</p><p>Y</p><p>Z</p><p>B</p></body></doc>'
        current = '<doc><body><p>A</p><p>B</p></body></doc>'
        requests = diff_documents(pristine, current)

        # Should have 3 DeleteContentRange operations
        deletes = [r for r in requests if 'deleteContentRange' in r]
        assert len(deletes) == 3

        # Deletes should be in descending index order (Z first, then Y, then X)

    def test_multi_block_changes(self):
        """Multiple non-adjacent change blocks work correctly."""
        pristine = '<doc><body><p>A</p><p>B</p><p>C</p><p>D</p><p>E</p></body></doc>'
        current = '<doc><body><p>A-modified</p><p>B</p><p>C-modified</p><p>D</p><p>E-modified</p></body></doc>'
        requests = diff_documents(pristine, current)

        # This is the core index drift test case
        # All three changes should apply correctly without corruption

    def test_insert_at_end(self):
        """Inserting at document end respects structural newline."""
        pristine = '<doc><body><p>First</p></body></doc>'
        current = '<doc><body><p>First</p><p>Second</p><p>Third</p></body></doc>'
        requests = diff_documents(pristine, current)

        # Should insert before structural newline, not after

    def test_style_only_change(self):
        """Style change without text change generates UpdateTextStyle."""
        pristine = '<doc><body><p>Hello</p></body></doc>'
        current = '<doc><body><p><b>Hello</b></p></body></doc>'
        requests = diff_documents(pristine, current)

        # Should have only UpdateTextStyle, no delete/insert
        assert len(requests) == 1
        assert 'updateTextStyle' in requests[0]

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_to_content(self):
        """Empty document to content."""
        pristine = '<doc><body><p></p></body></doc>'
        current = '<doc><body><p>New content</p></body></doc>'
        requests = diff_documents(pristine, current)
        assert len(requests) > 0

    def test_delete_all_keeps_last_paragraph(self):
        """Deleting all content keeps structural paragraph."""
        pristine = '<doc><body><p>Content</p><p>More</p></body></doc>'
        current = '<doc><body><p></p></body></doc>'
        requests = diff_documents(pristine, current)
        # Should not fail due to last paragraph rule

    def test_table_cell_content_change(self):
        """Changing text within a table cell."""
        pristine = '<doc><body><table rows="1" cols="1"><tr><td><p>Old</p></td></tr></table></body></doc>'
        current = '<doc><body><table rows="1" cols="1"><tr><td><p>New</p></td></tr></table></body></doc>'
        requests = diff_documents(pristine, current)
        # Should update cell content without recreating table
```

#### 2. Integration Tests (With Golden Files)

Test against captured API responses:

```bash
# Create golden file from real document
uv run python -m extradoc pull "https://docs.google.com/document/d/1eFtqhZbBwZgxKZPLSbfgDVgcrEk1p-xipMJT7XxFHV8/edit" --save-raw

# Run tests against golden files
uv run pytest tests/test_pull_integration.py -v
```

```python
# tests/test_diff_integration.py

def test_golden_file_no_changes():
    """Pulled document with no edits produces zero requests."""
    doc_id = "1eFtqhZbBwZgxKZPLSbfgDVgcrEk1p-xipMJT7XxFHV8"
    folder = Path(f"tests/golden/{doc_id}")

    # Load pristine from .pristine/document.zip
    pristine_xml = load_pristine(folder)
    # Load current from document.xml (unmodified)
    current_xml = load_current(folder)

    requests = diff_documents(pristine_xml, current_xml)
    assert requests == [], "Unmodified document should produce no requests"

def test_golden_file_with_known_edit():
    """Apply known edit and verify correct requests."""
    doc_id = "1eFtqhZbBwZgxKZPLSbfgDVgcrEk1p-xipMJT7XxFHV8"
    folder = Path(f"tests/golden/{doc_id}")

    pristine_xml = load_pristine(folder)
    current_xml = load_current(folder)

    # Apply a known edit
    current_xml = current_xml.replace("Hello", "Goodbye")

    requests = diff_documents(pristine_xml, current_xml)

    # Verify expected operations
    assert any('deleteContentRange' in str(r) for r in requests)
    assert any('Goodbye' in str(r) for r in requests)
```

#### 3. Manual Testing Workflow

For testing against real Google Docs:

```bash
# Step 1: Pull the test document
uv run python -m extradoc pull "https://docs.google.com/document/d/15dNMijQYl3juFdu8LqLvJoh3K10DREbtUm82489hgAs/edit"
cd 15dNMijQYl3juFdu8LqLvJoh3K10DREbtUm82489hgAs/

# Step 2: Make edits to document.xml
# - Change some text
# - Add a paragraph
# - Delete a paragraph
# - Change formatting

# Step 3: Preview the diff (dry run)
uv run python -m extradoc diff .
# Review the JSON output - verify it looks correct

# Step 4: Apply changes
uv run python -m extradoc push .

# Step 5: Verify in Google Docs
# Open the document in browser and verify changes applied correctly

# Step 6: Pull again and verify round-trip
uv run python -m extradoc pull "https://docs.google.com/document/d/15dNMijQYl3juFdu8LqLvJoh3K10DREbtUm82489hgAs/edit" --output fresh/
# Compare fresh/ with original to verify consistency
```

#### 4. Regression Tests

After fixing index drift, add this specific test:

```python
def test_resume_document_multi_section_changes():
    """The exact failing case from RCA - resume with 7→11 elements."""
    # Pristine: 7 elements
    pristine = '''<doc><body>
<p style="h1">Name</p>
<p>Contact info</p>
<p style="h2">Summary</p>
<p>Summary text</p>
<p style="h2">Skills</p>
<p>Skills list</p>
<p></p>
</body></doc>'''

    # Current: 11 elements with multiple sections changed
    current = '''<doc><body>
<p style="h1">Alex Chen</p>
<p>Engineer | SF</p>
<p style="h2">Summary</p>
<p>Experienced engineer with 8+ years.</p>
<p style="h2">Skills</p>
<p>Python, Go, TypeScript</p>
<p style="h2">Experience</p>
<p>Senior Engineer at TechCorp</p>
<p>Lead developer on key projects.</p>
<p style="h2">Education</p>
<p>BS Computer Science</p>
</body></doc>'''

    requests = diff_documents(pristine, current)

    # Verify no index drift:
    # - All delete indexes should be valid for the document state at that point
    # - All insert indexes should be valid for the document state at that point
    # - Content should not be jumbled

    # This test passes if we can apply these requests to Google Docs
    # without getting "Experienced engineer with 8+ Languages: Python"
```

### Debugging Guide

#### When Tests Fail

1. **Print the diff result**:
   ```python
   from extradoc.sequence_diff import sequence_diff
   diff_result = sequence_diff(p_elements, c_elements)
   for change in diff_result:
       print(f"{change.type}: p={change.pristine_elements}, c={change.current_elements}")
   ```

2. **Print working_elements state**:
   ```python
   def debug_working(working, label):
       print(f"--- {label} ---")
       for i, (elem, start, end) in enumerate(working):
           print(f"  [{i}] {start}-{end}: {elem}")
   ```

3. **Print generated operations**:
   ```python
   for op in operations:
       print(f"{op.op_type} @ {op.index}-{op.end_index}: {op.content[:20] if op.content else ''}")
   ```

#### Common Issues

| Symptom | Likely Cause | Debug Approach |
|---------|--------------|----------------|
| Content jumbled | Index drift across change blocks | Print working_elements after each change block |
| Missing content | Delete range too large | Check last paragraph rule enforcement |
| Duplicate content | Insert at wrong position | Verify insert_point calculation |
| Style not applied | UpdateTextStyle range wrong | Print run boundaries and style ops |
| "Invalid index" from API | Index exceeds document length | Print segment length vs operation indexes |

#### Validating Against Google Docs

```python
def validate_requests(requests, document_length):
    """Validate that all requests have valid indexes."""
    for r in requests:
        if 'deleteContentRange' in r:
            rng = r['deleteContentRange']['range']
            assert rng['startIndex'] >= 0
            assert rng['endIndex'] <= document_length
            assert rng['startIndex'] < rng['endIndex']
        elif 'insertText' in r:
            loc = r['insertText']['location']
            assert loc['index'] >= 0
            assert loc['index'] <= document_length
```

### Running All Tests

```bash
# Unit tests
uv run pytest tests/test_diff_engine.py -v

# Integration tests
uv run pytest tests/test_diff_integration.py -v

# Full test suite with coverage
uv run pytest tests/ -v --cov=src/extradoc --cov-report=html

# Type checking
uv run mypy src/extradoc

# Linting
uv run ruff check . && uv run ruff format .

# All checks (CI equivalent)
uv run pytest tests/ -v && uv run mypy src/extradoc && uv run ruff check .
```

### Test Coverage Goals

| Component | Coverage Target | Notes |
|-----------|-----------------|-------|
| `diff_engine.py` | 90%+ | Core logic, all branches |
| `sequence_diff.py` | 95%+ | Already well-tested |
| `desugar.py` | 80%+ | Parser coverage |
| Edge cases | 100% | All documented edge cases have tests |
