# ExtraDoc Implementation Gaps

This document tracks bugs, limitations, and implementation gaps discovered during testing.

**Last Updated:** 2026-02-06

---

## Summary

| Category | Count |
|----------|-------|
| Critical Bugs (Open) | 0 |
| Major Bugs (Open) | 3 |
| Fixed Bugs | 8 |
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

## Major Bugs (Open)

### 1. List Items Merged With Headings

**Status:** 🟠 Open
**Severity:** Major - Document structure corrupted
**Location:** `src/extradoc/diff_engine.py`

**Problem:** When pushing content with headings followed by lists, the headings can become list items.

**Observed:**
```xml
<!-- Before push -->
<h2>4.3 Additional Bullet Styles</h2>
<li type="bullet" level="0">Item A</li>

<!-- After push -->
<li type="decimal" level="0">4.3 Additional Bullet Styles</li>
<li type="bullet" level="0">Item A</li>
```

**Likely Cause:** Bullet creation requests applying to wrong paragraph ranges.

---

### 2. Base Style Corruption on Pull

**Status:** 🟠 Open
**Severity:** Major - Document styling corrupted
**Location:** `src/extradoc/style_factorizer.py`

**Problem:** After push, the `_base` style in `styles.xml` gets corrupted with unexpected properties.

**Before:**
```xml
<style id="_base" font="Arial" size="11pt" color="#000000"/>
```

**After:**
```xml
<style id="_base" bg="#FFFF00" bold="1" color="#0B8043" font="Courier New"
       italic="1" size="10pt" strikethrough="1" underline="1"/>
```

**Root Cause:** Style factorization on pull assigns styled paragraph properties to the base style.

---

### 3. Nested List Levels Incorrect

**Status:** 🟠 Open
**Severity:** Major - Feature partially broken
**Location:** `src/extradoc/diff_engine.py`

**Problem:** Nested lists sometimes have incorrect indentation levels after push.

**Observed:** Level 1 and level 2 items may shift or merge incorrectly.

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

## Fixed Bugs (2026-02-06)

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

| Priority | Issue | Status |
|----------|-------|--------|
| 1 | List/heading merge | 🟠 Open - Needs investigation |
| 2 | Base style corruption | 🟠 Open - Needs investigation |
| 3 | Nested list levels | 🟠 Open - Needs investigation |

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
