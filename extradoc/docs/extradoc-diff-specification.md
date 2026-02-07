# ExtraDoc Diff Specification

## 1. Document Model

A Google Doc has the following hierarchy:

```
Document
├── Tab[]
│   └── Body
│       └── StructuralElement[]
│           ├── Paragraph
│           ├── Table
│           │   └── TableRow[]
│           │       └── TableCell[]
│           │           └── StructuralElement[] (recursive)
│           ├── SectionBreak
│           └── TableOfContents
├── Header[] (keyed by header ID, e.g. "kix.hdr1")
│   └── StructuralElement[]
├── Footer[] (keyed by footer ID)
│   └── StructuralElement[]
└── Footnote[] (keyed by footnote ID)
    └── StructuralElement[]
```

Documents must always be fetched with `includeTabsContent=true`. The legacy `body` field is ignored; all content comes from `tabs[].documentTab`.

Every element in the API has a unique ID assigned by Google Docs, **except TableCell**, which has no stable identity. For diffing, cells are identified by their column position within a row (using column IDs from `<col>` elements).

## 2. Segments and Index Spaces

A **segment** is an independent region of the document with its own contiguous UTF-16 index space. Operations on one segment never affect indexes in another segment.

| Segment Type | Start Index | Identified By |
|-------------|-------------|---------------|
| Body (per tab) | 1 | Tab ID (implicit for single-tab docs) |
| Header | 0 | Header ID (e.g., "kix.hdr1") |
| Footer | 0 | Footer ID (e.g., "kix.ftr1") |
| Footnote | 0 | Footnote ID (e.g., "kix.fn1") |

The body's index 0 is occupied by an implicit `sectionBreak` that is not part of the content.

**Table cells are NOT separate segments.** They occupy contiguous index ranges within their parent segment (body, header, etc.). However, each cell has a **segment-end restriction** that behaves like a mini-segment (see Section 8).

## 3. UTF-16 Index Model

All positions in Google Docs are measured in **UTF-16 code units**, not characters or bytes.

### 3.1 Character Costs

| Element | UTF-16 Cost |
|---------|------------|
| ASCII character (U+0000–U+007F) | 1 unit |
| BMP character (U+0000–U+FFFF) | 1 unit |
| Supplementary character (U+10000+), e.g. emoji | 2 units (surrogate pair) |

### 3.2 Structural Marker Costs

| Marker | UTF-16 Cost |
|--------|------------|
| Paragraph terminator (newline) | 1 unit |
| Table start marker | 1 unit |
| Table end marker | 1 unit |
| Row start marker | 1 unit |
| Cell start marker | 1 unit |

### 3.3 Special Element Costs

Each of the following inline elements occupies exactly 1 index unit:

- Inline image
- Page break
- Column break
- Horizontal rule
- Footnote reference
- Person mention
- Equation
- Date

### 3.4 Paragraph Length Formula

```
paragraph_length = utf16_len(text_content) + special_element_count + 1
```

Where:
- `text_content` = concatenation of all text runs in the paragraph
- `special_element_count` = number of inline special elements
- `+1` = the paragraph terminator (newline)

### 3.5 Table Length Formula

```
table_length = 1                           // table start marker
             + Σ_rows (
                 1                         // row start marker
                 + Σ_cells (
                     1                     // cell start marker
                     + cell_content_length // recursive
                   )
               )
             + 1                           // table end marker
```

`cell_content_length` is the sum of its structural element lengths (paragraphs, nested tables, etc.). Minimum cell content length is 1 (the mandatory cell-end newline).

**Example: 2x2 table, each cell contains "A" (1 char):**

```
table_start:  1
  row_0:      1 (row marker)
    cell_00:  1 (cell marker) + 2 (char 'A' + newline) = 3
    cell_01:  1 + 2 = 3
  row_1:      1
    cell_10:  1 + 2 = 3
    cell_11:  1 + 2 = 3
table_end:    1

Total: 1 + (1+3+3) + (1+3+3) + 1 = 16
```

### 3.6 Cell Content Start Index

To compute the content start index of cell at position (target_row, target_col):

```
idx = table_start_index + 1              // skip table start marker

for row in 0..target_row:
    idx += 1                             // skip row start marker
    for col in 0..num_cols_in_row:
        idx += 1                         // skip cell start marker
        if row == target_row AND col == target_col:
            return idx                   // cell content starts here
        idx += cell_content_length(row, col)
```

## 4. Block Types for Diffing

StructuralElements are classified into block types for diffing:

| Block Type | Source | Diffing Behavior |
|-----------|--------|-----------------|
| **Paragraph** | `<p>`, `<h1>`–`<h6>`, `<title>`, `<subtitle>`, `<li>` | Grouped into ContentBlocks |
| **Table** | `<table>` | Structural diff (rows/columns/cells) |
| **SectionBreak** | `<sectionBreak>` | Individual diff |
| **TableOfContents** | `<toc>` | Individual diff |

### 4.1 ContentBlock

A **ContentBlock** is a grouping of consecutive paragraphs that share the same change operation. ContentBlocks are not present in the raw document; they are produced by the diff algorithm.

**Grouping rules:**
1. Only consecutive paragraphs with the **same operation** (all ADDED, all DELETED, or all MODIFIED) are grouped
2. Paragraphs must be **adjacent in the current document** (no intervening unchanged or differently-changed blocks)
3. Paragraphs must have the **same tag type** (all `<p>`, or all `<li>`, or all `<h1>`, etc.)
4. **Unchanged paragraphs act as separators** — they break groups even if the paragraphs on either side have the same operation

**Example:**
```
Pristine:  [p1, p2, p3, p4, p5]
Current:   [p1, p2', p3', p4, p5']

Alignment: p1=unchanged, p2=modified, p3=modified, p4=unchanged, p5=modified

Result:
  ContentBlock(MODIFIED, [p2, p3])   // consecutive modified, grouped
  ContentBlock(MODIFIED, [p5])       // separated from p2/p3 by unchanged p4
```

## 5. The Diff Algorithm

### 5.1 Overview

**Input:** pristine XML, current XML
**Output:** a change tree

### 5.2 Step 1: Parse Both Documents

Parse each XML document into a block tree:

```
Document
├── Tab "t.0" (or synthetic tab for legacy docs without <tab>)
│   └── Body
│       ├── Paragraph "First paragraph"
│       ├── Table (rows=2, cols=2)
│       │   ├── Row "r0" → [Cell "0,0", Cell "0,1"]
│       │   └── Row "r1" → [Cell "1,0", Cell "1,1"]
│       └── Paragraph "Last paragraph"
├── Header "kix.hdr1"
│   └── Paragraph "Header text"
└── Footnote "kix.fn1"
    └── Paragraph "Footnote text"
```

For legacy documents (no `<tab>` elements), wrap `<body>` in a synthetic tab with a default ID.

### 5.3 Step 2: Calculate Pristine Indexes

Walk the **pristine** tree and compute `start_index` and `end_index` for every block using the formulas in Section 3. Only the pristine indexes are needed because the backwards-walk algorithm (Section 6) operates on pristine positions.

### 5.4 Step 3: Match Top-Level Containers

Match tabs between pristine and current by tab ID:
- Tab in current only → ADDED tab
- Tab in pristine only → DELETED tab
- Tab in both → compare contents

Match headers, footers, footnotes by their respective IDs:
- Unmatched → ADDED or DELETED
- Matched → compare contents

### 5.5 Step 4: Diff Structural Elements Within a Segment

Given two lists of blocks (pristine and current) from a matched segment, produce an alignment using a two-pass approach:

**Pass 1 — Exact content match:**
For each block in current, find an unmatched block in pristine with identical XML content (hash-based). Mark both as matched.

**Pass 2 — Structural key match:**
For remaining unmatched blocks, match by structural type:
- Paragraph: match by tag (p→p, h1→h1, li→li)
- Table: match by type (any table matches any other table)
- TOC: match by type
- SectionBreak: match by type

Within each structural key group, match in order (first unmatched pristine with first unmatched current).

**Result:** A list of alignment pairs `(pristine_idx | None, current_idx | None)`:
- `(None, j)` → block `j` in current was ADDED
- `(i, None)` → block `i` in pristine was DELETED
- `(i, j)` with identical content → UNCHANGED
- `(i, j)` with different content → MODIFIED

**Ordering:** The alignment list is ordered by current document position, with deletions interleaved at their pristine positions. This ensures the correct `pristine_start` is computed for insertions (see Section 5.7).

### 5.6 Step 5: Group Into ContentBlocks

Walk the alignment results and group consecutive paragraphs per the rules in Section 4.1. Non-paragraph blocks (Table, TOC, SectionBreak) are emitted as individual changes.

### 5.7 Step 6: Compute Insertion Points for ADDED Blocks

For ADDED blocks, `pristine_start = pristine_end = insertion_point`, where `insertion_point` is the `end_index` of the immediately preceding pristine block. If there is no preceding block, `insertion_point = segment_start_index`.

This is tracked by maintaining a `last_pristine_end` variable during the grouping walk. Unchanged blocks update this variable but do not generate changes.

### 5.8 Step 7: Recurse Into Modified Tables

When a TABLE is MODIFIED, perform structural diff:

1. **Match rows** by stable row ID (assigned at pull time, preserved by editors). For duplicate IDs, match positionally within each ID group.
2. **Match columns** by stable column ID (from `<col>` elements).
3. For each matched row pair with different content, match cells by column alignment.
4. For each matched cell pair with different content, recurse to Step 4 (diff structural elements within the cell).

Result is a sub-tree of changes:
```
TABLE (MODIFIED)
├── TABLE_COLUMN (ADDED, col_idx=2)
├── TABLE_COLUMN (DELETED, col_idx=4)
├── TABLE_ROW (ADDED, after_xml=...)
├── TABLE_ROW (DELETED, row_id="r3")
└── TABLE_ROW (MODIFIED, row_id="r1")
    ├── TABLE_CELL (MODIFIED, col_idx=0)
    │   └── CONTENT_BLOCK (MODIFIED, ...)
    └── TABLE_CELL (MODIFIED, col_idx=1)
        └── CONTENT_BLOCK (ADDED, ...)
```

## 6. The Change Tree

The diff algorithm produces a tree of **ChangeNode** objects:

```
ChangeNode:
  node_type:       DOCUMENT | TAB | SEGMENT | CONTENT_BLOCK | TABLE |
                   TABLE_ROW | TABLE_COLUMN | TABLE_CELL
  op:              UNCHANGED | ADDED | DELETED | MODIFIED
  node_id:         string (tab ID, header ID, row ID, etc.)
  before_xml:      string | null (pristine XML, for DELETE/MODIFY)
  after_xml:       string | null (current XML, for ADD/MODIFY)
  pristine_start:  int (start index in pristine segment)
  pristine_end:    int (end index in pristine segment)
  segment_type:    BODY | HEADER | FOOTER | FOOTNOTE (on SEGMENT nodes)
  segment_id:      string | null (Google Docs segment ID; null for body)
  segment_end:     int (end of segment index space, on SEGMENT nodes)
  table_start:     int (pristine table start index, on TABLE nodes)
  children:        ChangeNode[]
```

**Properties:**
- Only nodes with `op != UNCHANGED` (or ancestors thereof) appear in the tree
- `pristine_start` and `pristine_end` are always in the coordinate space of the containing segment
- For ADDED nodes: `pristine_start == pristine_end == insertion_point`
- SEGMENT nodes carry `segment_end` which is needed for the segment-end newline restriction

## 7. Request Generation: The Backwards Walk

### 7.1 The Core Invariant

> When processing a change at pristine position P, everything at positions < P is still at pristine state.

This is guaranteed by processing changes from **highest pristine_start to lowest** within each segment.

### 7.2 Why Backwards?

When you insert N characters at index P:
- Indexes 0..P-1 are unaffected
- Indexes P..end shift forward by N

When you delete characters from index P to Q:
- Indexes 0..P-1 are unaffected
- Indexes Q..end shift backward by (Q-P)

By processing highest-index-first, each operation only shifts content at or above its position. Content below remains at pristine indexes, allowing subsequent operations to use pristine indexes directly.

### 7.3 Walk Algorithm

```
for each segment_node in change_tree:
    segment_end_consumed = false

    for each child in segment_node.children, sorted by pristine_start DESCENDING:
        match child.node_type:
            CONTENT_BLOCK → generate_content_requests(child, segment, segment_end_consumed)
                            update segment_end_consumed if insert was at segment end
            TABLE         → generate_table_requests(child, segment)
            // other types handled similarly
```

### 7.4 Segment-End Consumed Tracking

The `segment_end_consumed` flag coordinates multiple insertions at the segment end. See Section 8.2 for details.

## 8. The Segment-End Newline Restriction

### 8.1 The Rule

Google Docs API forbids deleting the final newline character of any segment: body, header, footer, footnote, or **table cell**.

The final newline occupies the index position `segment_end - 1`.

### 8.2 Handling in Deletions

When generating a `deleteContentRange` request, clamp the end index:

```
effective_end = min(pristine_end, segment_end - 1)
```

If `effective_end <= pristine_start`, skip the deletion (nothing to delete after clamping).

### 8.3 Handling in Insertions

When inserting at the segment end, the existing final newline must not be duplicated:

1. Detect if the insertion point is at or beyond `segment_end - 1`
2. If at segment end AND `segment_end_consumed == false`:
   - Strip the trailing newline from the text to be inserted
   - Set `segment_end_consumed = true`
3. If at segment end AND `segment_end_consumed == true`:
   - Do NOT strip the trailing newline (a previous insert in the backwards walk already handled it)

**Why this matters:** In a backwards walk, the first change processed at the segment end is actually the *last* content in document order. Its trailing newline would duplicate the preserved sentinel newline, so we strip it. Subsequent inserts at the same position (earlier content in document order) must keep their newlines because the first insert already consumed the sentinel.

### 8.4 Table Cells as Mini-Segments

Each table cell has a final newline that cannot be deleted. For operations within a cell:
- `segment_end` for the cell = the cell's `pristine_end` index
- Same clamping and stripping rules apply
- `segment_end_consumed` is tracked independently per cell

## 9. Request Generation: ContentBlock

### 9.1 DELETED ContentBlock

Generate a single `deleteContentRange` request:

```json
{
  "deleteContentRange": {
    "range": {
      "startIndex": pristine_start,
      "endIndex": min(pristine_end, segment_end - 1),
      "segmentId": segment_id  // omit for body
    }
  }
}
```

### 9.2 ADDED ContentBlock

Generate requests in this order:

1. **insertText** — Insert the plain text (with embedded newlines that create paragraph boundaries):
   ```json
   {
     "insertText": {
       "location": { "index": pristine_start, "segmentId": segment_id },
       "text": "First paragraph\nSecond paragraph\n"
     }
   }
   ```
   If at segment end and not consumed: strip the final `\n` from the text.

2. **updateTextStyle** — Clear inherited formatting by applying an empty style to the full range, then apply actual styles per text run:
   ```json
   {
     "updateTextStyle": {
       "range": { "startIndex": start, "endIndex": end, "segmentId": segment_id },
       "textStyle": { "bold": true, "italic": false, ... },
       "fields": "bold,italic,..."
     }
   }
   ```

3. **insertPageBreak / insertSectionBreak** — For special elements, insert at their computed offset position (highest offset first to maintain index stability within the inserted text).

4. **updateParagraphStyle** — Set named styles (HEADING_1, TITLE, etc.) and paragraph properties (alignment, spacing, borders):
   ```json
   {
     "updateParagraphStyle": {
       "range": { "startIndex": para_start, "endIndex": para_end, "segmentId": segment_id },
       "paragraphStyle": { "namedStyleType": "HEADING_1" },
       "fields": "namedStyleType"
     }
   }
   ```

5. **createParagraphBullets** — For list items, group consecutive bullets of the same type:
   ```json
   {
     "createParagraphBullets": {
       "range": { "startIndex": group_start, "endIndex": group_end, "segmentId": segment_id },
       "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"
     }
   }
   ```

6. **deleteParagraphBullets** — When modifying content that was previously bulleted but is now plain, explicitly remove bullet formatting.

All style operation ranges are computed as offsets from `pristine_start` (the insertion point).

### 9.3 MODIFIED ContentBlock

To preserve comments, suggested edits, and list identities, modifications should be applied granularly rather than replacing the entire block.

1.  **Map Paragraphs:** align paragraphs in the pristine block to the current block (1-to-1 mapping where possible).
2.  **Granular Text Diff:** For each mapped paragraph pair:
    *   Compute the text difference (e.g. using `diff-match-patch`).
    *   Generate `deleteContentRange` for deletions.
    *   Generate `insertText` for insertions.
    *   **Crucial:** Do not delete the final newline of the paragraph unless the paragraph itself is being removed. Preserving the newline preserves the `listId` and paragraph-level metadata.
3.  **Update Styles:** Apply `updateTextStyle` and `updateParagraphStyle` to the modified ranges to match the new state.

### 9.4 Unmapped Paragraphs (Structural Changes)

If the number of paragraphs changes (split/merge) and cannot be mapped 1-to-1:
- **Deletions:** Use `deleteContentRange` (including newlines).
- **Insertions:** Use `insertText` (with newlines).

## 10. Request Generation: Table Operations

### 10.1 ADDED Table

1. **insertTable** at the insertion point:
   ```json
   {
     "insertTable": {
       "location": { "index": pristine_start, "segmentId": segment_id },
       "rows": num_rows,
       "columns": num_cols
     }
   }
   ```
   This creates an empty table. Each cell contains a single newline (1 index unit).

2. **Insert cell content** — For each cell with content, use the ContentBlock insertion logic (Section 9.2) at the computed cell content start index.

   Process cells **right-to-left within each row, bottom-to-top across rows** to maintain index stability.

   After `insertTable`, cell content start indexes are computed using the formula in Section 3.6, where each empty cell has `cell_content_length = 1`.

3. **Apply cell styles** — `updateTableCellStyle` for background colors, borders, etc.

4. **Apply column widths** — `updateTableColumnProperties` for fixed-width columns.

### 10.2 DELETED Table

Generate a single `deleteContentRange`:
```json
{
  "deleteContentRange": {
    "range": {
      "startIndex": pristine_start,
      "endIndex": min(pristine_end, segment_end - 1),
      "segmentId": segment_id
    }
  }
}
```

### 10.3 MODIFIED Table

To ensure index stability, operations are generated using a **strict backwards walk**. We must track the *post-modification length* of each row to correctly handle deferred column insertions.

**Execution Order (Generated Requests):**

1.  **Column Deletions (High to Low)**
    *   Uses pristine column indices.
    *   Removing a column reduces the length of every row. Since we process high-to-low, earlier columns are unaffected.

2.  **Row Deletions (High to Low)**
    *   Uses pristine row indices.
    *   Deleting Row N does not affect indices of Row N-1.

3.  **Cell Content Modifications & Row Insertions (Interleaved, Bottom-Up)**
    *   Iterate rows from last (highest index) to first.
    *   **If Row is Modified:**
        *   Process cells **Right-to-Left**.
        *   Apply ContentBlock changes (Section 9) to each cell.
        *   *Track the new length of this row.*
    *   **If Row is Inserted:**
        *   `insertTableRow` (inserts below the previous row).
        *   Populate new cells (Right-to-Left).
        *   *Track the length of this new row.*
    *   **If Row is Unchanged:**
        *   *Track its pristine length.*

4.  **Column Insertions (High to Low)**
    *   `insertTableColumn` (inserts right of previous column).
    *   **Populate New Cells:**
        *   This operation adds a cell to *every* row.
        *   We must populate these cells with content.
        *   **Calculation:** Iterate through all rows (Top-to-Bottom of the *modified* table).
        *   Start Index for Row 0 = Table Start + 1 (table marker).
        *   Start Index for Row N = End Index of Row N-1.
        *   Insertion Point for the new cell in Row N can be inferred from the previous cell in that row (or the end of the row if appending).
        *   Use the *tracked lengths* from Step 3 to maintain correct positioning.

5.  **Column Width Updates**

### 10.4 New Cell Content After Structural Insert

The logic for populating new cells (created by `insertTableRow` or `insertTableColumn`) must rely on the **tracked row lengths** from the backwards walk, not pristine lengths, because content modifications in Step 3 may have changed the row lengths.

1.  Calculate start index based on tracked lengths.
2.  Walk cells right-to-left within the new/modified region.
3.  Use ContentBlock insertion logic with `strip_trailing_newline = true` (since the new cell already has its sentinel newline).

## 11. Request Ordering Summary

All requests within a segment are generated during the backwards walk. The final request list is in execution order — no post-processing or reordering is needed.

**Global ordering across segments:**
1. Header/footer/tab creation and deletion requests (structural)
2. Content requests per segment, each segment independent
3. Within each segment: requests from backwards walk (highest pristine index first)

**Within a table modification:**
1. Column deletes (highest col first)
2. Row deletes (highest row first)
3. Cell content modifications (bottom-to-top, right-to-left)
4. Column inserts (highest col first) + new cell content
5. Row inserts (highest row first) + new cell content
6. Column width updates

## 12. Special Cases

### 12.1 Footnote References

Footnotes are inline in the XML: `<p>See note<footnote id="kix.fn1"><p>Footnote text</p></footnote></p>`.

When a paragraph contains a footnote:
- The footnote reference occupies 1 index in the body
- The footnote content has its own segment (index space starting at 0)
- **Adding a footnote:** `createFootnote` at `location: { "index": insertion_point, "segmentId": segment_id }`.
  - The insertion point is the `pristine_start` (or calculated offset) within the ContentBlock, same as text.
  - Do NOT use `endOfSegmentLocation`.
- **Deleting a footnote:** `deleteContentRange` for the 1-character reference in the body.

### 12.2 Horizontal Rules

Horizontal rules (`<hr/>`) are **read-only** in the Google Docs API. They cannot be inserted or deleted. The diff algorithm should skip changes that only involve horizontal rules.

### 12.3 Tabs

- Adding a tab: `addDocumentTab` request
- Deleting a tab: `deleteTab` request
- Modifying a tab: process its segments (body, headers, footers) normally

### 12.4 Headers and Footers

- Adding: `createHeader` / `createFooter` with type (DEFAULT, FIRST_PAGE, EVEN_PAGE)
- Deleting: `deleteHeader` / `deleteFooter` by header/footer ID
- Modifying: process as a segment with its own index space starting at 0

### 12.5 Empty Segments After Deletion

When all content in a segment is deleted, the segment still retains its final newline. The deletion range is clamped to preserve it.
