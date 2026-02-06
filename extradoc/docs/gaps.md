# ExtraDoc Implementation Gaps

This document tracks bugs, limitations, and implementation gaps discovered during testing.

**Last Updated:** 2026-02-07

---

## Summary

| Category | Count |
|----------|-------|
| Critical Bugs (Open) | 0 |
| Major Bugs (Open) | 0 |
| Fixed Bugs | 13 |
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

*No open major bugs at this time.*

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

1. **Merged body insert bullet index bug** — Blocks the most common workflow (adding lists to existing documents). Fix the content length calculation in `_generate_content_insert_requests()` or avoid triggering the merged approach unnecessarily.
2. **Table delete `startIndex` bug** — Blocks table deletion via diff/push. Requires passing the table's document index into the delete function.

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
