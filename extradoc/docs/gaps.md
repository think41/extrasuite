# ExtraDoc v2 — Known Bugs & Root Cause Analysis

**Last Updated:** 2026-02-08
**Test Method:** Created a comprehensive 21-section showcase document exercising all features, pushed via v2, re-pulled, and compared.

---

## Critical Bugs

### 1. Paragraph-Level Styles Bleed to Neighboring Paragraphs

**Severity:** Critical — affects alignment, lineSpacing, spacing, indentation
**Symptoms:** After push, paragraphs that should be left-aligned show as right-aligned or centered. `spaceAbove`/`spaceBelow` values from one paragraph appear on unrelated paragraphs throughout the document.

**Root Cause (Push):** When multiple content blocks are inserted at the same position (e.g., index 1 for a nearly empty document), `insertText` inherits paragraph styles from existing text at the insertion point. The v2 engine correctly generates `updateParagraphStyle` requests with proper ranges *within* each content block, but:

1. Content block A inserts text at index 1 and sets `alignment: END` on its range.
2. Content block B then inserts text at the same base index. The new text *inherits* `alignment: END` from content block A's paragraph at the insertion point.
3. Content block B's `updateParagraphStyle` with `namedStyleType: NORMAL_TEXT` does NOT clear explicitly-set properties like `alignment` — Google Docs treats named styles and explicit properties as separate layers.

This causes a cascading bleed: paragraph properties from earlier content blocks contaminate all subsequent content blocks inserted at the same or adjacent positions.

**Evidence:** Raw API response (`document.json`) after push showed `alignment: END` on paragraphs that should have been `alignment: START`, and `spaceBelow: {magnitude: 12}` on paragraphs that never requested spacing.

**Root Cause (Pull):** `xml_converter.py` does not extract paragraph-level properties (alignment, lineSpacing, spaceAbove, etc.) from the API response back into XML `class` attributes. The `style_factorizer.py` module HAS extraction code for these properties (lines 133-137), but `xml_converter.py` doesn't use it for paragraph-level style factorization. This means even if styles were correctly applied, they wouldn't survive a pull round-trip.

**Files:**
- `v2/generators/content.py:370-395` — generates `updateParagraphStyle` requests
- `xml_converter.py` — missing paragraph-level style extraction on pull

---

## Major Bugs

### 3. New Tables Missing Cell Styles

**Severity:** Major — cell background, padding, borders, vertical alignment all absent on new tables
**Symptoms:** A newly created table with `<td class="cell-hdr">` has no background color, no custom padding, no border styling.

**Root Cause:** In `v2/generators/table.py`, the `_add_table()` method (line 67) creates the table structure and populates cell content, but **never calls `_generate_cell_style_request()`**. Cell style generation only exists in `_phase_cell_mods_and_row_inserts()` (line 342-352), which is only invoked for MODIFIED tables via `_modify_table()`.

**File:** `v2/generators/table.py:67-142` — `_add_table()` missing cell style requests

---

### 4. New Tables Missing Column Widths

**Severity:** Major — `colwidths` attribute ignored on new tables
**Symptoms:** A table with `colwidths="30,70"` has equal-width columns after push.

**Root Cause:** `_phase_column_widths()` is only called from `_modify_table()` (line 182). The `_add_table()` method has no column width handling at all.

**File:** `v2/generators/table.py:67-142` — `_add_table()` missing column width requests

---

### 5. Footnotes Placed at End of Document

**Severity:** Major — footnotes are created but at the wrong position
**Symptoms:** A `<footnote>` referenced inline within a paragraph appears at the bottom of the document body, not at the inline reference point.

**Root Cause:** In `v2/generators/structural.py` line 74, added footnotes use `{"createFootnote": {"endOfSegmentLocation": {}}}` which places the footnote reference at the end of the document body instead of at the specific inline position where the `<footnote>` tag appears in the XML. Additionally, after creating the footnote, its content is not populated.

**File:** `v2/generators/structural.py:74` — uses `endOfSegmentLocation` instead of inline index

---

### 6. Merged Cells (colspan/rowspan) Not Applied

**Severity:** Major — tables always render as regular grids
**Symptoms:** A `<td colspan="2">` cell is not merged — the table shows individual cells.

**Root Cause:** The `_add_table()` method creates tables via `insertTable` which always creates a regular grid. There is no code anywhere in `table.py` to generate `mergeTableCells` requests for cells with `colspan` or `rowspan` attributes. The Google Docs API does support `MergeTableCellsRequest`, but it is never invoked.

**File:** `v2/generators/table.py` — no `mergeTableCells` API calls

---

### 7. Page Break Inherits Wrong Paragraph Style

**Severity:** Major — page breaks create paragraphs with wrong heading level
**Symptoms:** A `<pagebreak/>` between content inherits `HEADING_1` style from the preceding heading, creating a visible heading-styled empty paragraph.

**Root Cause:** In `v2/generators/content.py` lines 505-517, page-break-only paragraphs skip the `paragraph_styles.append(...)` call (they `continue` without setting `namedStyleType`). The `insertPageBreak` API call creates a new paragraph that inherits the named style from the text at the insertion point. If the preceding paragraph is a heading, the page break paragraph becomes a heading too.

**File:** `v2/generators/content.py:505-517` — page-break-only paragraphs skip namedStyleType

---

### 8. Mixed List Types Break Adjacent Content

**Severity:** Major — headings after mixed lists get absorbed into the list
**Symptoms:** A heading `<h2>` immediately after a list with mixed types (decimal at level 0, alpha at level 1) becomes a list item instead of a heading.

**Root Cause:** `createParagraphBullets` applies a bullet preset to a character range. When different presets are applied to adjacent paragraphs (e.g., decimal at level 0 followed by alpha at level 1), the Google Docs API may merge them into a single list, overriding the intended type differentiation. The range of the last `createParagraphBullets` request can extend past the list items and capture the following heading paragraph.

**Files:** `v2/generators/content.py` — `createParagraphBullets` range calculation

---

## API Limitations (Cannot Fix)

### 9. Checkbox Lists Create Regular Bullets

`type="checkbox"` list items become regular bullet items. The `BULLET_CHECKBOX` preset is accepted by the API but creates lists with `glyphType: GLYPH_TYPE_UNSPECIFIED`. Real checkboxes use a different internal mechanism not exposed via the Docs API.

**Workaround:** Use Unicode checkbox symbols manually (`☐ ☑ ☒`) in text content.

---

## Not Implemented

| Feature | Notes |
|---------|-------|
| Autotext (page numbers) | API doesn't support insertion |
| Images | Requires separate Drive upload flow |
| Person mentions | Requires verified email + special API |
| Horizontal rules | Read-only — cannot add/remove via API |

---

## Features Working Correctly

The following features were verified as working correctly through the round-trip test:

| Feature | Notes |
|---------|-------|
| Headings (h1-h6, title, subtitle) | All 8 heading types round-trip correctly |
| Basic paragraphs | Content preserved exactly |
| Bold, italic, underline, strikethrough | All inline formatting works |
| Superscript, subscript | Works correctly |
| Hyperlinks | URL and display text preserved |
| Text colors and backgrounds | All color/highlight styles applied |
| Font changes (family, size) | Custom fonts like Georgia, Courier New work |
| Simple bullet lists | Single-level bullets work |
| Simple numbered lists (decimal) | Single-type numbered lists work |
| Nested lists (same type) | Nesting via tab indentation works |
| Basic tables (no special styling) | Content in cells preserved |
| Multi-paragraph table cells | Multiple `<p>` in a `<td>` works |
| Headers and footers | Content in header/footer segments works |
| Document tabs | Add/delete tabs, edit content within tabs, `tabId` in all requests |
| `<style>` wrapper element | Transfers `class` to wrapped children correctly |
| Named styles on text spans | `class` attributes on `<span>` apply text styles |
| Unicode and special characters | Emoji, accented chars, symbols all preserved |
