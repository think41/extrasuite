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

A modification is a delete-then-insert at the same position:

1. Delete the old content (Section 9.1)
2. Insert the new content (Section 9.2)

The delete happens first in the request sequence (they execute top-to-bottom). After deletion, the insertion point is at `pristine_start` (unchanged because content above was removed).

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

This is the most complex operation. All row/column structural operations reference the table by its `table_start` (pristine index), which remains valid because the segment-level backwards walk ensures nothing below the table has been modified yet.

Requests are generated in this order:

**Phase 1: Column Deletions (highest column index first)**

```json
{
  "deleteTableColumn": {
    "tableCellLocation": {
      "tableStartLocation": { "index": table_start, "segmentId": segment_id },
      "rowIndex": 0,
      "columnIndex": col_idx
    }
  }
}
```

Column deletions use pristine column indices, processed highest-first so that each deletion doesn't affect the index of subsequently deleted columns.

**Phase 2: Row Deletions and Cell Content Modifications (backwards walk)**

Walk all rows **bottom-to-top** (highest row index first). For each row:

- If the row is **DELETED**: emit `deleteTableRow`
  ```json
  {
    "deleteTableRow": {
      "tableCellLocation": {
        "tableStartLocation": { "index": table_start, "segmentId": segment_id },
        "rowIndex": row_idx,
        "columnIndex": 0
      }
    }
  }
  ```

- If the row is **MODIFIED**: walk its cells **right-to-left** (highest column index first). For each modified cell, generate content requests using the ContentBlock logic (Section 9), treating the cell as a mini-segment with `segment_end = cell.pristine_end`.

Row deletions and cell modifications are interleaved in the backwards walk. Processing bottom-to-top ensures:
- Deleting row N doesn't affect content indexes in rows < N
- Modifying cells in row M doesn't affect cells in rows < M
- `deleteTableRow` uses row index (structural), while content modifications use content indexes. Neither affects the other within the same backwards pass.

**Phase 3: Column Insertions (deferred, highest column index first)**

```json
{
  "insertTableColumn": {
    "tableCellLocation": {
      "tableStartLocation": { "index": table_start, "segmentId": segment_id },
      "rowIndex": 0,
      "columnIndex": reference_col_idx
    },
    "insertRight": true|false
  }
}
```

After each column insertion, compute new cell positions for the inserted column (each new cell is 1 index unit — just a newline) and insert content using ContentBlock logic.

**Phase 4: Row Insertions (deferred, highest row index first)**

```json
{
  "insertTableRow": {
    "tableCellLocation": {
      "tableStartLocation": { "index": table_start, "segmentId": segment_id },
      "rowIndex": reference_row_idx,
      "columnIndex": 0
    },
    "insertBelow": true|false
  }
}
```

After each row insertion, compute new cell positions (each new cell is 1 index unit) and insert content using ContentBlock logic.

**Phase 5: Column Width Updates**

```json
{
  "updateTableColumnProperties": {
    "tableStartLocation": { "index": table_start, "segmentId": segment_id },
    "columnIndices": [col_idx],
    "tableColumnProperties": { "widthType": "FIXED_WIDTH", "width": { "magnitude": N, "unit": "PT" } },
    "fields": "widthType,width"
  }
}
```

**Why this ordering?**

1. **Column deletes first**: Removing a column removes cells from every row. Must happen before row processing to avoid operating on cells that will be deleted.
2. **Row deletes + cell modifications interleaved, bottom-to-top**: The backwards walk invariant ensures index stability. `deleteTableRow` uses row indices (unaffected by content changes), while content operations use content indexes (unaffected by operations at higher row positions).
3. **Structural inserts deferred**: `insertTableRow` / `insertTableColumn` change the table's index structure. If done before cell modifications, pristine content indexes would be invalidated. By deferring inserts until after all content operations, pristine indexes remain valid.

### 10.4 New Cell Content After Structural Insert

After `insertTableRow`, each new cell contains a single newline (1 index unit). After `insertTableColumn`, each new cell in every existing row is empty (1 unit).

To insert content into new cells:
1. Compute the cell content start using Section 3.6, treating existing cells as their pristine length and new cells as length 1
2. Walk cells right-to-left within the new row/column
3. Use ContentBlock insertion logic with `strip_trailing_newline = true` (the cell already has its sentinel newline)

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
- Adding a footnote: `createFootnote` at `endOfSegmentLocation`
- Deleting a footnote: `deleteContentRange` for the 1-character reference in the body

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
