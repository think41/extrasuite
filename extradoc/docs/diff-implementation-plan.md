# ExtraDoc Diff Implementation Plan

## Overview

Block-level diff/push implementation for Google Docs. Uses tree-based decomposition with bottom-up processing to ensure index stability.

## Status

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Cleanup | ✅ Complete |
| Phase 2 | Paragraph-level block diff | ✅ Complete |
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

## Phase 2: Paragraph-Level Block Diff ✅

**Goal:** Detect changes at paragraph granularity for surgical updates

### Completed Tasks

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

4. **Updated tests**
   - Parsing tests updated for new individual paragraph blocks
   - Added `TestParagraphLevelGranularity` test class with 3 new tests

### Verified Behavior

```
pristine: [title, subtitle, p1, p2]
current:  [title, subtitle', p1, p2']

Result:
- ContentBlock([subtitle]) → MODIFIED (only subtitle, not title)
- ContentBlock([p2]) → MODIFIED (only p2, separated by unchanged p1)
```

---

## Phase 3: ContentBlock Request Generation 🔲

**Goal:** Generate actual batchUpdate requests from block changes

### Tasks

1. **Implement `_generate_content_insert_requests()`**
   - Parse XML content to extract paragraphs
   - Generate `insertText` for text content (newlines create paragraph breaks)
   - Insert special elements bottom-up by offset (pagebreak, footnoteref, etc.)
   - Apply paragraph styles (headings via `updateParagraphStyle`)
   - Apply bullets (`createParagraphBullets`)
   - Apply text styles (`updateTextStyle` for bold, italic, links)

2. **Implement `_generate_content_delete_requests()`**
   - Calculate index range of content to delete
   - Generate `deleteContentRange` request

3. **Handle MODIFIED ContentBlock**
   - Simple approach: Delete + Insert at same position
   - Delete old content, then insert new content

4. **Processing order**
   - Sort all changes by start_index descending (bottom-up)
   - Guarantees index stability

### Data Model (Reference)

```python
@dataclass
class ParsedContentBlock:
    text: str                              # Full text, \n = paragraph separator
    special_elements: list[SpecialElement] # [(offset, type, attrs)]
    paragraphs: list[ParagraphMeta]        # Style info per paragraph
    text_runs: list[TextRunMeta]           # Styled ranges within paragraphs
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Modified ContentBlock | Delete + Insert | Simple, reliable, no complex text diffing |
| Block grouping | By change status | Smaller modified regions, surgical changes |
| Processing order | Bottom-up by index | Guarantees index stability |
| Paragraph parsing | Individual blocks | Enables fine-grained change detection |
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
- `test_diff_detects_text_change` (will pass after Phase 3)

### Real Document Testing
Verified with real Google Doc:
- No changes detected on unmodified document ✅
- Single paragraph modification detected correctly ✅
- Consecutive modifications grouped together ✅
- Non-consecutive modifications separated ✅
- Header changes tracked with correct segment ID ✅
