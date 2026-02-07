# ExtraDoc Implementation Gaps

This document tracks bugs, limitations, and implementation gaps discovered during testing.

**Last Updated:** 2026-02-07

---

## Summary

| Category | Count |
|----------|-------|
| Critical Bugs (Open) | 0 |
| Major Bugs (Open) | 4 |
| Fixed Bugs | 15 |
| API Limitations | 5 |

---

## API Limitations (Cannot Fix)

These are limitations of the Google Docs API, not bugs in extradoc.

### Checkbox Lists Do Not Work

**Status:** ❌ API Limitation
**Severity:** Feature cannot work as designed

**Problem:** `type="checkbox"` list items become regular bullet items instead of checkboxes.

**Investigation Results:**
- The preset `BULLET_CHECKBOX` is valid and accepted by the API
- However, the API creates lists with `glyphType: "GLYPH_TYPE_UNSPECIFIED"` and no `glyphSymbol`
- Real checkboxes in Google Docs use a different internal mechanism not exposed via the API
- Community reports confirm: checkbox state cannot be detected or set via the API

**Workaround:** Use Unicode checkbox symbols manually (☐ ☑ ☒) in text content.

---

## Critical Bugs (Open)

*No open critical bugs at this time.*

---

## Major Bugs (Open)

### Table Column Operations Fail

**Status:** 🔴 Open
**Severity:** Major - blocks table structure changes
**Discovered:** 2026-02-07

**Problem:** Changing the number of columns in an existing table fails with API error:
```
Invalid requests[33].insertTableColumn: Invalid table start location.
Must specify the start index of the table.
```

**Reproduction:**
1. Pull a document with a 3-column table
2. Edit XML to have a 2-column table (or vice versa)
3. Push fails with the above error

**Root Cause:** The `insertTableColumn` or `deleteTableColumn` request is not receiving the correct table start index.

**Workaround:** Delete the entire table and create a new one with the desired column count in two separate push operations.

---

### Drastic Rewrites Scramble Document Structure

**Status:** 🔴 Open
**Severity:** Major - unpredictable results on large changes
**Discovered:** 2026-02-07

**Problem:** When making major structural changes (e.g., replacing all content with completely different content), the diff algorithm produces unexpected results. Paragraphs may become headings, content may be reordered, or elements may be duplicated.

**Reproduction:**
1. Pull a document with headings, paragraphs, tables, and lists
2. Replace entire body with completely different content structure
3. Push - result has wrong element types (e.g., `<p>` becomes `<h1>`)

**Example:** A complete rewrite from tech documentation to a short story resulted in:
- Many `<p>` elements becoming `<h1>` headings
- Content appearing in wrong order
- Chapter headings merged together

**Root Cause:** The diff algorithm attempts to minimize changes by "morphing" existing elements rather than delete-all + insert-all. This optimization produces incorrect results when content is substantially different.

**Workaround:** For major rewrites, perform in two steps:
1. Delete all content, push
2. Pull fresh, add new content, push

---

### Phantom Empty Elements After Push

**Status:** 🔴 Open
**Severity:** Major - document pollution
**Discovered:** 2026-02-07

**Problem:** After a push operation, re-pulling the document reveals empty elements that were not in the source XML:
- Empty headings: `<h2></h2>`
- Empty list items: `<li type="bullet" level="0"></li>`

**Reproduction:**
1. Create a document with headings and lists
2. Push changes
3. Pull - observe empty elements not present in original XML

**Root Cause:** Unknown. May be related to:
- Index calculation errors leaving orphan newlines
- Request ordering issues creating empty paragraphs that inherit styles
- Interaction between delete and insert operations

**Workaround:** Manually delete empty elements after push, or ignore them if they don't affect document appearance.

---

### Base Font Style Changes Not Applied

**Status:** 🟡 Needs Investigation
**Severity:** Medium - styling limitation
**Discovered:** 2026-02-07

**Problem:** Changing the `font` attribute in the `_base` style in `styles.xml` does not affect the pushed document. The document retains its original font.

**Reproduction:**
1. Pull a document (default font is Arial)
2. Edit `styles.xml`: change `<style id="_base" font="Arial".../>` to `font="Georgia"`
3. Push - document still uses Arial

**Possible Causes:**
- `_base` style changes may not generate any API requests
- Font changes may require explicit `updateTextStyle` on all content
- The diff may not detect `_base` changes as actionable

**Workaround:** Apply font changes via explicit `class` attributes on individual elements rather than via `_base`.

---

## Partially Working Features

| Feature | Status | Notes |
|---------|--------|-------|
| Footnotes (push) | 🔄 Needs testing | Code exists, needs end-to-end verification |
| `<style>` wrapper element | 🔄 Needs testing | For applying class to multiple consecutive elements |
| Column breaks | 🔄 Needs testing | `<columnbreak/>` element |
| Alpha lists | ✅ Fixed | `type="alpha"` now uses `NUMBERED_UPPERALPHA_ALPHA_ROMAN` |
| Roman lists | ✅ Fixed | `type="roman"` now uses `NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL` |
| Page breaks | ✅ Fixed | Request ordering issue resolved |
| Headers/footers | ✅ Fixed | Type-only matching prevents creation errors |

---

## Not Implemented (API Limitations)

| Feature | Status | Notes |
|---------|--------|-------|
| Checkbox lists | ❌ API limitation | BULLET_CHECKBOX preset doesn't create real checkboxes |
| Autotext (page numbers) | ❌ Cannot implement | API doesn't support insertion |
| Images | ❌ Not implemented | Requires separate Drive upload flow |
| Person mentions | ❌ Cannot implement | Requires verified email + special API |
| Horizontal rules | ⚠️ Read-only | Cannot add/remove via API |

---

## Known Limitations

| Feature | Limitation | Workaround |
|---------|------------|------------|
| Checkbox lists | API creates bullets, not checkboxes | Use Unicode symbols ☐ ☑ ☒ |
| Autotext (page numbers) | Cannot insert via batchUpdate | Use placeholder `[PAGE]` |
| Person mentions | Requires specific personProperties | Insert as styled text |
| New tabs with content | Requires two-batch (create, then populate) | Documented behavior |
| Horizontal rules | Read-only in Google Docs API | Cannot add/remove, only modify adjacent content |
| Images | Requires separate upload to Drive | Not yet implemented |
| Table column changes | Changing column count on existing tables fails | Delete table, push, then add new table |
| Major rewrites | Diff algorithm scrambles content on large structural changes | Delete all content first, push, pull, then add new content |
| Base font changes | Changing `_base` font in styles.xml has no effect | Use explicit class on elements |

---

## Working Features (Verified)

| Feature | Status | Notes |
|---------|--------|-------|
| Title/Subtitle | ✅ | `<title>`, `<subtitle>` |
| Headings h1-h6 | ✅ | All levels work |
| Basic paragraphs | ✅ | `<p>` elements |
| Bold | ✅ | `<b>` tag |
| Italic | ✅ | `<i>` tag |
| Underline | ✅ | `<u>` tag |
| Strikethrough | ✅ | `<s>` tag |
| Subscript | ✅ | `<sub>` tag |
| Superscript | ✅ | `<sup>` tag |
| Hyperlinks | ✅ | `<a href="...">` |
| Combined formatting | ✅ | Nested tags like `<b><i>...</i></b>` |
| Bullet lists | ✅ | `type="bullet"` |
| Numbered lists | ✅ | `type="decimal"` |
| Alpha lists | ✅ | `type="alpha"` (fixed) |
| Roman lists | ✅ | `type="roman"` (fixed) |
| Page breaks | ✅ | `<pagebreak/>` (fixed) |
| Header/footer editing | ✅ | Modify existing headers/footers (fixed) |
| Custom paragraph styles | ✅ | `<p class="...">` with alignment, spacing (fixed) |
| Custom text styles | ✅ | `<p class="...">` with bg, color, font (fixed) |
| Tables preserved on edit | ✅ | Adding content around tables no longer destroys them |
| Bullet removal | ✅ | Converting `<li>` to `<p>` now correctly removes bullets (fixed) |
| Multiple inserts at same position | ✅ | Paragraphs no longer merge together (fixed) |

---

## Fixed Bugs (2026-02-07)

### Fixed: Table Delete Fails with `KeyError: 'startIndex'`

**Location:** `src/extradoc/diff_engine.py`, `_handle_table_change()` and `_generate_table_delete_requests()`

**Problem:** When a push attempted to delete a table (table exists in pristine but not in current), the diff engine crashed with `KeyError: 'startIndex'`.

**Root Cause:** `_generate_table_delete_requests()` tried to access `table_info["startIndex"]`, but `_parse_table_xml()` only returns `{"rows", "cols", "id"}`. The `startIndex` needed to come from the `pristine_table_indexes` dict.

**Fix:**
1. Modified `_handle_table_change()` to look up the table start index using `_get_table_start_index(change.container_path, pristine_table_indexes)` before calling the delete function
2. Updated `_generate_table_delete_requests()` to accept `table_start_index` as a parameter
3. Used `_calculate_nested_table_length()` to accurately calculate the table size from XML for the delete range

---

### Fixed: Index Calculation Error When Modifying and Adding Content

**Location:** `src/extradoc/diff_engine.py`, request reordering logic

**Problem:** When a push both modified existing content AND added new content, the API rejected requests with "Index XXXX must be less than the end index of the referenced segment". This happened because insert/update indexes were calculated assuming the original document size, but deletes run first and shrink the document.

**Root Cause:** The request reordering put all deletes first (sorted descending), then all inserts/updates. But insert indexes weren't adjusted to account for the document shrinkage caused by preceding deletes.

**Fix:** Added index adjustment logic after reordering:
1. Calculate delete ranges (start, length) for all `deleteContentRange` requests
2. For each insert/update request at index I, calculate adjustment as the sum of all delete lengths where `delete_end <= I`
3. Subtract the adjustment from the request's index

This ensures inserts target the correct position after all preceding deletes have been applied.

---

### Known Issue: Style Inheritance on Insert

**Status:** Documented, not fixed

**Problem:** When inserting text after a heading, the inserted paragraphs may inherit the heading style instead of becoming normal paragraphs. This is because Google Docs applies formatting from the insertion point to newly inserted text.

**Root Cause:** The code only generates `updateParagraphStyle` for non-NORMAL_TEXT paragraphs (headings). Normal paragraphs don't get explicit style updates, so they inherit from context.

**Workaround:** Manually fix paragraph styles in Google Docs after push, or ensure content is inserted before styled elements rather than after them.

**Note:** A fix was attempted (always apply NORMAL_TEXT style) but caused other issues. Further investigation needed.

---

### Fixed: Content Merging (Missing Newlines)

**Location:** `src/extradoc/diff_engine.py`, `_walk_segment_backwards()`, `_emit_content_ops()`

**Problem:** When multiple content blocks were inserted at the same position (e.g., adding several paragraphs to an empty document), ALL of them stripped their trailing newlines because they were all detected as "at segment end". This caused paragraphs to merge into a single line.

**Root Cause:** In the backwards walk, each change independently checked `at_segment_end(insert_idx)` using pristine indexes. When multiple ADDED changes had the same insert position, they all saw themselves at segment end and stripped their newlines.

**Fix:**
1. Added `segment_end_consumed` flag tracking in `_walk_segment_backwards()`
2. Modified `_emit_content_block()` and `_emit_content_ops()` to accept and return this flag
3. Only the FIRST change processed (which is the LAST in document order due to backwards walk) strips its trailing newline
4. Subsequent changes at the same position do NOT strip, preserving proper paragraph separation

---

### Fixed: Bullets Not Being Removed

**Location:** `src/extradoc/diff_engine.py`, `_emit_content_ops()`, `_generate_content_insert_requests()`

**Problem:** When converting from `<li>` to `<p>`, the bullet formatting persisted. Paragraphs that should be regular text remained as bullet items.

**Root Cause:** When content was deleted and new content inserted at the same position, the paragraph structure retained its bullet formatting. The new content inherited this formatting because `deleteParagraphBullets` was never called.

**Fix:**
1. Added `delete_existing_bullets` parameter to `_generate_content_insert_requests()`
2. For ADDED and MODIFIED changes, pass `delete_existing_bullets=True`
3. Generate `deleteParagraphBullets` requests for all non-bullet paragraphs in the inserted content
4. This safely removes bullet formatting regardless of whether it existed (no-op if not)

---

## Fixed Bugs (2026-02-06)

### Fixed: Base Style Corruption on Pull

**Location:** `src/extradoc/style_factorizer.py`

**Problem:** The `_base` style in `styles.xml` was incorrectly computed from the most frequently occurring text properties in the document. If styled text (e.g., yellow background) appeared frequently, those styles would be assigned to `_base`.

**Root Cause:** The `compute_base_style()` function iterated over all text runs and selected the most common value for each property, weighted by character count. This meant styled content could corrupt the base style.

**Fix:** Replaced frequency-based computation with extraction from `namedStyles.NORMAL_TEXT`:
```python
def extract_base_style_from_named_styles(document: dict[str, Any]) -> dict[str, str]:
    """Extract base style from the document's NORMAL_TEXT named style."""
    named_styles = document.get("namedStyles")
    # Find NORMAL_TEXT style
    for style in named_styles.get("styles", []):
        if style.get("namedStyleType") == "NORMAL_TEXT":
            text_style = style.get("textStyle", {})
            return extract_text_style(text_style)
    return {}
```

Now `_base` always reflects the document's defined NORMAL_TEXT defaults (typically `font="Arial" size="11pt"`), not computed from content.

---

### Fixed: List Items Merged With Headings

**Location:** `src/extradoc/diff_engine.py`

**Problem:** When pushing content with headings followed by lists, headings could become list items.

**Testing Results:** Extensive testing on 2026-02-06 could not reproduce this bug:
- Added h2 headings followed by bullet lists - headings preserved correctly
- Added h2 headings followed by decimal lists - headings preserved correctly
- Inserted headings between existing list items - headings preserved correctly
- Mixed bullet and decimal lists with headings - all preserved correctly

**Status:** Could not reproduce. Marking as resolved pending further reports.

---

### Fixed: Nested List Levels Incorrect

**Location:** `src/extradoc/diff_engine.py`

**Problem:** Nested lists sometimes had incorrect indentation levels after push.

**Testing Results:** Extensive testing on 2026-02-06 shows nested lists working correctly:
- Created 5-level nested bullet lists (levels 0, 1, 2, 1, 0)
- All nesting levels preserved correctly after push/pull cycle
- Tab-based indentation in insertText correctly translated to nesting levels

**Status:** Could not reproduce. Marking as resolved pending further reports.

---

### Fixed: Table Content Destroyed During Body Edits

**Location:** `src/extradoc/diff_engine.py`

**Problem:** When adding content to a document body that contains tables, the entire body was replaced with plain text, destroying the table structure.

**Root Cause:** The `_generate_merged_body_insert()` function was triggered when there were multiple body content changes. This function:
1. Deleted all body content (including tables)
2. Re-inserted body content via `_generate_content_insert_requests()` which doesn't handle tables
3. Tables were serialized as plain text in the insert

**Fix:** Added check to skip merged approach when the body contains tables:
```python
has_body_tables = any(
    c.block_type == BlockType.TABLE and "body" in str(c.container_path)
    for c in block_changes
)
# Also check pristine body for unchanged tables
if pristine_body:
    has_body_tables = has_body_tables or any(
        isinstance(elem, Table) for elem in pristine_body.content
    )

# Skip merged approach if tables present
if has_body_deletes and has_body_inserts and len(body_content_changes) > 1 and not has_body_tables:
    # Use merged approach only when safe
```

---

### Fixed: Custom Styles Not Applied on Push

**Location:** `src/extradoc/diff_engine.py`, function `_parse_content_block_xml()`

**Problem:** Custom styles defined in `styles.xml` were not applied when using `<p class="...">`.

**Root Cause:** The `_parse_content_block_xml()` function only extracted explicit paragraph attributes, but did not resolve `class` attributes to style properties from `styles.xml`.

**Fix:** Added class attribute resolution in paragraph parsing:
```python
class_name = para_elem.get("class")
if class_name and style_defs and class_name in style_defs:
    class_props = style_defs[class_name]
    # Map property names (alignment -> align)
    # Separate paragraph-level props (alignment) from text-level props (bg, color)
    # Apply paragraph props via updateParagraphStyle
    # Apply text props via updateTextStyle covering whole paragraph
```

Now `<p class="center">` applies alignment and `<p class="highlight">` applies background color.

---

### Fixed: Table Content Not Inserted Into Cells

**Location:** `src/extradoc/diff_engine.py`

**Problem:** When adding new tables with content, only the table structure was created. Cell content was not inserted.

**Root Cause:** `_generate_table_add_requests()` only created the `insertTable` request without populating cell content. The code path for cell content (`_generate_table_insert()`) was only used for nested tables.

**Fix:** Implemented two-phase approach in `_generate_table_add_requests()`:
1. Insert empty table structure with `insertTable`
2. Calculate each cell's content index (accounting for auto-inserted newline before table)
3. Use `_generate_content_insert_requests()` for each cell's content (same as body/header/footer)

**Key insight:** Table cell content is a ContentBlock, handled the same way as body content. No duplicate logic needed.

---

### Fixed: Invalid Bullet Presets for Alpha/Roman Lists

**Location:** `src/extradoc/diff_engine.py`, `src/extradoc/request_generators/content.py`

**Problem:** Invalid Google Docs API bullet preset values.

**Fix:** Updated presets:
- `alpha` → `NUMBERED_UPPERALPHA_ALPHA_ROMAN` (starts with A, B, C)
- `roman` → `NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL` (starts with I, II, III)

---

### Fixed: Request Ordering Issues (Page Break)

**Location:** `src/extradoc/diff_engine.py`

**Problem:** `insertPageBreak` requests were reordered before the text content.

**Fix:** Added `_skipReorder: True` marker to requests from `_generate_content_insert_requests()`:
- `insertText`
- `updateTextStyle`
- `insertPageBreak`
- `insertSectionBreak`

---

### Fixed: Header/Footer Creation Fails

**Location:** `src/extradoc/block_diff.py`

**Problem:** Header/footer with new ID detected as ADDED instead of MODIFIED.

**Fix:** Modified `child_key()` to match headers/footers by type only:
```python
if block.block_type in (BlockType.HEADER, BlockType.FOOTER):
    return (block.block_type.value, "")  # Match by type only
```

---

## Priority Fix Order

1. **Drastic rewrites scramble content** — The diff algorithm's "minimize changes" heuristic produces incorrect results when content is substantially different. Consider detecting "major structural change" and falling back to delete-all + insert-all approach.
2. **Table column operations fail** — `insertTableColumn`/`deleteTableColumn` requests need correct table start index. Blocks table structure changes.
3. **Phantom empty elements** — Investigate why empty `<h2>` and `<li>` elements appear after push. May be index calculation or request ordering issue.
4. **Base font changes ignored** — Changes to `_base` style font don't generate API requests. Need to propagate base style changes to content.

---

## Related Files

| File | Purpose |
|------|---------|
| `src/extradoc/diff_engine.py` | Main diff/request generation |
| `src/extradoc/request_generators/content.py` | Content request generation |
| `src/extradoc/block_diff.py` | Block-level diff detection |
| `src/extradoc/desugar.py` | XML to internal representation |
| `src/extradoc/xml_converter.py` | Google API to XML conversion |
| `src/extradoc/style_factorizer.py` | Style extraction and factorization |
| `docs/googledocs/lists.md` | List preset documentation |
