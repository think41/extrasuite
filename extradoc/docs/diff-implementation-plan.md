# ExtraDoc Diff Implementation Plan

## Overview

Block-level diff/push implementation for Google Docs. Uses tree-based decomposition with bottom-up processing to ensure index stability.

## Status

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Cleanup | ✅ Complete |
| Phase 2 | Structural block operations | ✅ Complete |
| Phase 3 | ContentBlock request generation | 🔲 Not Started |

---

## Phase 1: Cleanup ✅

**Goal:** Remove old rebuild strategy, fix failing tests

### Completed Tasks

1. **Deleted outdated docs**
   - `docs/implementation-gap.md` - Referenced obsolete HTML format
   - `docs/README.md` - Referenced non-existent files

2. **Cleaned up `diff_engine.py`**
   - Removed `_rebuild_section()` and related helper functions
   - Rewrote `diff_documents()` to use `block_diff.py`
   - Kept request generation helpers (`_operation_to_request`, `_generate_paragraph_insert`, etc.)

3. **Fixed tests**
   - `test_diff_no_changes` - Now passes (returns empty list for identical docs)
   - `test_push_no_changes` - Now passes (handles 0 changes correctly)

---

## Phase 2: Structural Block Operations ✅

**Goal:** Detect and handle all structural block changes (tables, headers, footers, tabs, footnotes)

### 2.1 Paragraph-Level Block Diff ✅

1. **Added `PARAGRAPH` block type**
   - Each paragraph is parsed as its own `PARAGRAPH` block
   - During diffing, consecutive same-status paragraphs are grouped into `CONTENT_BLOCK` changes

2. **Enhanced `_parse_structural_elements()`**
   - Parses each paragraph individually (not grouped upfront)
   - Tracks tag type (`p`, `h1`, `li`, etc.) in attributes

3. **Implemented `_group_paragraph_changes()`**
   - Groups consecutive modified paragraphs into single `CONTENT_BLOCK` change
   - Non-consecutive changes result in separate changes
   - Unchanged paragraphs act as separators between change groups

### 2.2 Table Operations ✅

| Operation | Request Type | Notes |
|-----------|--------------|-------|
| Insert table | `insertTable` | Creates empty table structure |
| Delete table | `deleteContentRange` | Covers entire table range |
| Insert row | `insertTableRow` | Uses `insertBelow=True` |
| Delete row | `deleteTableRow` | By row index |
| Insert column | `insertTableColumn` | Uses existing column ref + `insertRight=True` |
| Delete column | `deleteTableColumn` | Deduplicated (one request per column) |

**Index calculation:** Table indexes are computed by walking the document structure (not from raw JSON), using `calculate_table_indexes()` in `indexer.py`.

**Container path:** Row changes tracked via `row_idx:N` in container_path. Column changes tracked via `col_idx:N`.

### 2.3 Header/Footer Operations ✅

| Operation | Request Type | Notes |
|-----------|--------------|-------|
| Create header | `createHeader` | Creates empty header for section type |
| Delete header | `deleteHeader` | By header ID |
| Create footer | `createFooter` | Creates empty footer for section type |
| Delete footer | `deleteFooter` | By footer ID |

**Note:** Header/footer content modifications require Phase 3 (ContentBlock handling).

### 2.4 Tab Operations ✅

| Operation | Request Type | Notes |
|-----------|--------------|-------|
| Add tab | `addDocumentTab` | Optional title from XML |
| Delete tab | `deleteTab` | By tab ID |

**Note:** Tab content modifications require Phase 3.

### 2.5 Footnote Operations ✅

**Inline Footnote Model:** Footnotes are rendered inline where the reference appears:

```xml
<p>See note<footnote id="kix.fn1"><p>Footnote content.</p></footnote> for details.</p>
```

| Operation | Request Type | Notes |
|-----------|--------------|-------|
| Create footnote | `createFootnote` | Uses `endOfSegmentLocation` (adds at end) |
| Delete footnote | `deleteContentRange` | 1-character deletion at reference position |

**Current limitations:**
- Footnote creation uses `endOfSegmentLocation` (adds at document end). Precise positioning requires Phase 3 to ensure target text exists.
- Footnote deletion index calculation is approximate for documents with tables/complex structure. Full accuracy requires Phase 3 content tracking.

### Verified with Real Google Docs

- Table insert/delete row ✅
- Table insert/delete column ✅
- Header create/delete ✅
- Footer create/delete ✅
- Footnote create (at end) ✅

---

## Phase 3: ContentBlock Request Generation 🔲

**Goal:** Generate batchUpdate requests for paragraph content (text, formatting, special elements)

### 3.1 ContentBlock Data Model

```python
@dataclass
class ParsedContentBlock:
    text: str                              # Full text, \n = paragraph separator
    special_elements: list[SpecialElement] # [(offset, type, attrs)]
    paragraphs: list[ParagraphMeta]        # Style info per paragraph
    text_runs: list[TextRunMeta]           # Styled ranges within paragraphs

@dataclass
class SpecialElement:
    offset: int          # UTF-16 offset from ContentBlock start
    element_type: str    # "pagebreak", "footnoteref", "columnbreak", "hr"
    attributes: dict

@dataclass
class ParagraphMeta:
    start_offset: int
    end_offset: int
    named_style: str       # "NORMAL_TEXT", "HEADING_1", etc.
    bullet_type: str | None
    bullet_level: int

@dataclass
class TextRunMeta:
    start_offset: int
    end_offset: int
    styles: dict           # {"bold": True, "italic": True, "link": "..."}
```

### 3.2 New ContentBlock (ADDED)

```python
def generate_new_content_block(block: ParsedContentBlock, insert_index: int, segment_id: str | None):
    requests = []

    # 1. Insert all text at once (newlines create paragraph breaks)
    requests.append(insertText(block.text, insert_index, segment_id))

    # 2. Insert special elements (bottom-up by offset)
    for elem in sorted(block.special_elements, key=lambda e: e.offset, reverse=True):
        idx = insert_index + elem.offset
        if elem.type == "pagebreak":
            requests.append(insertPageBreak(idx, segment_id))
        elif elem.type == "footnoteref":
            requests.append(createFootnote(idx, segment_id))
        elif elem.type == "columnbreak":
            requests.append(insertSectionBreak(idx, "CONTINUOUS", segment_id))
        # Note: HR handled via paragraph border styling

    # 3. Apply paragraph styles (headings)
    for para in block.paragraphs:
        if para.named_style != "NORMAL_TEXT":
            requests.append(updateParagraphStyle(
                insert_index + para.start_offset,
                insert_index + para.end_offset,
                {"namedStyleType": para.named_style},
                segment_id
            ))

    # 4. Apply bullets
    for para in block.paragraphs:
        if para.bullet_type:
            requests.append(createParagraphBullets(
                insert_index + para.start_offset,
                insert_index + para.end_offset,
                bullet_preset(para.bullet_type),
                segment_id
            ))

    # 5. Apply text styles (bold, italic, links)
    for run in block.text_runs:
        if run.styles:
            requests.append(updateTextStyle(
                insert_index + run.start_offset,
                insert_index + run.end_offset,
                run.styles,
                segment_id
            ))

    return requests
```

### 3.3 Deleted ContentBlock

```python
def generate_delete_content_block(start_index: int, end_index: int, segment_id: str | None):
    return [deleteContentRange(start_index, end_index, segment_id)]
```

### 3.4 Modified ContentBlock

Simple approach: Delete + Insert

```python
def generate_modify_content_block(pristine: ParsedContentBlock, current: ParsedContentBlock,
                                   pristine_start: int, pristine_end: int, segment_id: str | None):
    requests = []

    # 1. Delete old content
    requests.append(deleteContentRange(pristine_start, pristine_end, segment_id))

    # 2. Insert new content at same position
    requests.extend(generate_new_content_block(current, pristine_start, segment_id))

    return requests
```

### 3.5 Processing Order

All changes processed bottom-up by start_index:

```python
def generate_all_requests(changes: list[BlockChange]) -> list[dict]:
    requests = []

    # Sort by start_index descending (bottom-up)
    for change in sorted(changes, key=lambda c: c.start_index, reverse=True):
        if change.block_type == BlockType.CONTENT_BLOCK:
            if change.change_type == ChangeType.ADDED:
                requests.extend(generate_new_content_block(...))
            elif change.change_type == ChangeType.DELETED:
                requests.extend(generate_delete_content_block(...))
            elif change.change_type == ChangeType.MODIFIED:
                requests.extend(generate_modify_content_block(...))
        elif change.block_type == BlockType.TABLE:
            requests.extend(generate_table_requests(...))
        # ... other block types

    return requests
```

### 3.6 Tasks

1. **Implement `ParsedContentBlock` extraction from XML**
   - Parse paragraph XML to extract text, styles, and special elements
   - Calculate UTF-16 offsets for each element

2. **Implement `_generate_content_insert_requests()`**
   - Generate `insertText` for text content
   - Insert special elements bottom-up by offset
   - Apply paragraph styles and bullets
   - Apply text styles

3. **Implement `_generate_content_delete_requests()`**
   - Calculate index range from pristine document
   - Generate `deleteContentRange` request

4. **Handle MODIFIED ContentBlock**
   - Delete old content, insert new content at same position

5. **Update footnote positioning**
   - Use precise indexes when creating footnotes
   - Accurate index calculation for footnote deletion

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Modified ContentBlock | Delete + Insert | Simple, reliable, no complex text diffing |
| Block grouping | By change status | Smaller modified regions, surgical changes |
| Processing order | Bottom-up by index | Guarantees index stability |
| Paragraph parsing | Individual blocks | Enables fine-grained change detection |
| Inline footnotes | Position + content together | Enables proper diff detection |
| Images | Deferred | Requires separate upload flow |

---

## Test Strategy

### Unit Tests
- Block parsing (`test_block_diff.py::TestBlockParsing`)
- Block alignment (`test_block_diff.py::TestBlockAlignment`)
- Paragraph-level granularity (`test_block_diff.py::TestParagraphLevelGranularity`)
- Request generation (TODO in Phase 3)

### Integration Tests
- `test_pull_integration.py::test_diff_no_changes` ✅
- `test_push_no_changes` ✅
- `test_diff_detects_text_change` ✅

### Real Document Testing

All verified with ExtraDoc Showcase document:

**Phase 2 (Structural):**
- No changes detected on unmodified document ✅
- Table insert/delete row/column ✅
- Header create/delete ✅
- Footer create/delete ✅
- Footnote create (at end) ✅

**Phase 3 (Content) - TODO:**
- Text insertion/deletion
- Heading style changes
- Bullet list changes
- Bold/italic formatting
- Link insertion
