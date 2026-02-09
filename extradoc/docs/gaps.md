# ExtraDoc — Known Bugs & Root Cause Analysis

**Last Updated:** 2026-02-09
**Test Document:** https://docs.google.com/document/d/1JgCnmlnTuV7SUwuF0_xXIi101gmK5vfmjkUKuGdrams/edit
**Test Method:** Created a comprehensive document exercising all features (title/subtitle, h1-h6, inline formatting, 5 tables with cell styles/column widths/colspan, 6 list types with nesting, footnotes, header/footer, 2 tabs, page break, column break, code block, unicode/emoji). Pushed via extradoc, re-pulled, and compared.

---

## Critical Bugs

### 1. Paragraph-Level Styles Bleed to Neighboring Paragraphs

**Severity:** Critical — affects alignment, lineSpacing, spacing, indentation
**Symptoms:** After push, paragraphs that should be left-aligned show as right-aligned or centered. `spaceAbove`/`spaceBelow` values from one paragraph appear on unrelated paragraphs throughout the document.

**Root Cause (Push):** When multiple content blocks are inserted at the same position (e.g., index 1 for a nearly empty document), `insertText` inherits paragraph styles from existing text at the insertion point. The engine correctly generates `updateParagraphStyle` requests with proper ranges *within* each content block, but:

1. Content block A inserts text at index 1 and sets `alignment: END` on its range.
2. Content block B then inserts text at the same base index. The new text *inherits* `alignment: END` from content block A's paragraph at the insertion point.
3. Content block B's `updateParagraphStyle` with `namedStyleType: NORMAL_TEXT` does NOT clear explicitly-set properties like `alignment` — Google Docs treats named styles and explicit properties as separate layers.

This causes a cascading bleed: paragraph properties from earlier content blocks contaminate all subsequent content blocks inserted at the same or adjacent positions.

**Root Cause (Pull):** `xml_converter.py` does not extract paragraph-level properties (alignment, lineSpacing, spaceAbove, etc.) from the API response back into XML `class` attributes. The `style_factorizer.py` module HAS extraction code for these properties (lines 133-137), but `xml_converter.py` doesn't use it for paragraph-level style factorization. This means even if styles were correctly applied, they wouldn't survive a pull round-trip.

**Files:**
- `generators/content.py` — generates `updateParagraphStyle` requests
- `xml_converter.py` — missing paragraph-level style extraction on pull

---

## Major Bugs

### 2. Header/Footer Content Not Populated

**Severity:** Major — headers/footers are created but always empty
**Symptoms:** After push, a `<header>` or `<footer>` with text content is created (gets a real Google ID) but contains only an empty `<p></p>`. The `class` attribute is also ignored (shows `_base`).

**Sent:**
```xml
<header id="kix.hdr1" class="hdr-s"><p>Acme Corp — CONFIDENTIAL</p></header>
<footer id="kix.ftr1" class="ftr-s"><p>Acme Corp Q4 2025 Annual Report — Confidential</p></footer>
```

**Got:**
```xml
<header id="kix.d4r8p7ib84y7" class="_base"><p></p></header>
<footer id="kix.bm560lpnwvvd" class="_base"><p></p></footer>
```

**Root Cause:** The 3-batch push strategy creates headers/footers in batch 1 and captures their real IDs. But batch 2 (main body content) apparently does not include insertText requests targeting the header/footer segment IDs. The content insertion for these segments is either not generated or uses the wrong segment ID.

**Files:** `push.py` (3-batch orchestration), `generators/structural.py` (header/footer handling)

---

### 3. New Tab Body Content Not Populated

**Severity:** Major — new tabs are created but always empty
**Symptoms:** A second tab with `<h1>`, `<table>`, and `<p>` content is created with the correct title, but its body contains only `<p></p>`.

**Sent:**
```xml
<tab id="t.new1" title="Raw Data" class="_base">
  <body>
    <h1>Supporting Data</h1>
    <table id="t4">...</table>
    <p>This tab contains supplementary data.</p>
  </body>
</tab>
```

**Got:**
```xml
<tab id="t.9247hqsf0nbn" title="Raw Data" class="_base">
  <body><p></p></body>
</tab>
```

**Root Cause:** `addDocumentTab` creates the tab, but the subsequent content insertion requests for the new tab's body are either not generated or use the wrong `tabId`. The real tab ID assigned by Google (e.g., `t.9247hqsf0nbn`) may not be mapped back to the placeholder ID (`t.new1`) used in content generation.

**Files:** `push.py`, `walker.py` or `generators/` — tab ID rewriting for new tabs

---

### 4. New Tables Missing Cell Styles

**Severity:** Major — cell background, padding, borders, vertical alignment all absent on new tables
**Symptoms:** A newly created table with `<td class="cell-hdr">` (bg=#1A237E) has no background color. All cells show only default padding (`cell-Iv00x`).

**Sent:** `cell-hdr` (dark blue), `cell-alt` (gray), `cell-tot` (yellow), `cell-dk` (dark gray)
**Got:** All cells → `cell-Iv00x` (default 5pt padding only)

**Root Cause:** In `generators/table.py`, the `_add_table()` method creates the table structure and populates cell content, but **never calls `_generate_cell_style_request()`**. Cell style generation only exists in `_phase_cell_mods_and_row_inserts()`, which is only invoked for MODIFIED tables via `_modify_table()`.

**File:** `generators/table.py` — `_add_table()` missing cell style requests

---

### ~~5. Footnote Content Lost~~ (FIXED)

**Status:** Fixed — footnote content is now populated correctly.

**Previous issue:** `createFootnote` created the footnote reference but the footnote body was never populated (contained only a space character).

**Root causes fixed:**
1. `walker.py` — `_walk_segment()` now calls `_emit_new_segment_content()` for ADDED footnotes, generating content insertion requests targeting the footnote's segment ID.
2. `push.py` — Reordered batch separation: placeholder footnote IDs are extracted first, then used to separate footnote content requests into batch 3. Also fixed batch 3 cleanup: `deleteContentRange` was missing `tabId` and used `endIndex: 2` which tried to delete the segment-end newline. `createFootnote` creates " \n" (space + newline); only the space (index 0-1) should be deleted.
3. `desugar.py` — Changed `tab.findall("footnote")` to `tab.iter("footnote")` so footnotes nested inside `<body><p>` are discovered.

**Note:** Footnote position shift (off-by-one) is a separate issue not addressed here.

---

### 6. Merged Cells (colspan/rowspan) Not Applied

**Severity:** Major — tables always render as regular grids
**Symptoms:** A `<td colspan="2">` cell is not visually merged — the table shows individual cells.

**Root Cause:** The `_add_table()` method creates tables via `insertTable` which always creates a regular grid. There is no code to generate `mergeTableCells` requests for cells with `colspan` or `rowspan` attributes. The Google Docs API does support `MergeTableCellsRequest`, but it is never invoked.

**Note:** The colspan attribute round-trips through pull (Google reports covered cells), but the visual merge is not applied during push.

**File:** `generators/table.py` — no `mergeTableCells` API calls

---

### 7. Mixed List Types Collapse to Parent Type

**Severity:** Major — nested sub-items lose their intended list type
**Symptoms:**
- `<li type="bullet" level="1">` nested under decimal level 0 → becomes `type="decimal" level="1"`
- `<li type="alpha" level="1">` nested under decimal level 0 → becomes `type="decimal" level="1"`

**Root Cause:** `createParagraphBullets` applies a single bullet preset to a character range. When different presets are applied to adjacent paragraphs (e.g., `NUMBERED_DECIMAL_NESTED` for level 0, then `BULLET_DISC_CIRCLE_SQUARE` for level 1), Google Docs merges them into a single list, overriding the sub-item's intended type with the parent list's type.

**Files:** `generators/content.py` — `createParagraphBullets` range calculation and preset selection

---

### 8. Spurious Empty Paragraphs Inserted

**Severity:** Major — document is littered with blank lines
**Symptoms:** After push, empty `<p></p>` elements appear before/after title, subtitle, every heading, after tables, etc. Roughly 15+ spurious empty paragraphs in a 4-page document.

**Example:** Between subtitle and h1:
```xml
<subtitle>Board-Confidential Draft · Prepared January 2026</subtitle>
<p></p>
<h1 spaceAbove="24pt" spaceBelow="12pt">Executive Summary</h1>
```

**Root Cause:** Likely caused by `insertText` including extra `\n` characters, or by content block boundaries generating an extra paragraph break at the seam between blocks.

**Files:** `generators/content.py` — text insertion with newlines

---

### 9. H2+ Heading Spacing via Class Not Applied

**Severity:** Major — paragraph styles from class ignored on some heading types
**Symptoms:** `<h2 class="h2-sp">` where h2-sp has `spaceAbove="18pt" spaceBelow="6pt"` is pushed without any spacing. The re-pulled h2 shows no spacing attributes. Meanwhile, h1 elements with the same pattern (`<h1 class="h1-sp">`) DO retain spacing.

**Root Cause:** The paragraph style from the `class` attribute is either not resolved for h2+ headings, or is overwritten by the `updateParagraphStyle` that sets `namedStyleType: HEADING_2`. This could be the same paragraph-style-bleed issue (#1) — setting `namedStyleType` may clear explicit spacing properties, or the spacing requests may be generated but then overridden.

**Files:** `generators/content.py` — heading paragraph style generation, class resolution for non-h1 headings

---

### 10. indentFirstLine Lost

**Severity:** Moderate — first-line indent is silently dropped
**Symptoms:** A paragraph with `class="indent"` (indentLeft="18pt" indentFirstLine="36pt") comes back with only `indentLeft="18pt"`. The `indentFirstLine` is lost.

**Root Cause:** Either the `indentFirstLine` property is not included in `updateParagraphStyle` field mask, or it's being overwritten. The Google Docs API field name is `indentFirstLine` in the paragraph style.

**Files:** `generators/content.py` — paragraph style field mask, `style_converter.py` — property mapping

---

### 11. Column Break Cannot Round-Trip

**Severity:** Moderate — column breaks are silently lost on push and pull

**Symptoms:** `<p>text before<columnbreak/>text after</p>` pushed via `insertSectionBreak(CONTINUOUS)` creates a section break (different from a column break), which splits the paragraph. On re-pull, `sectionBreak` elements are skipped entirely (`xml_converter.py:234`), so the column break disappears.

**Root Cause:** Two issues:
1. **No insertColumnBreak API:** Google Docs API has no request type for inserting inline column breaks. `insertSectionBreak(CONTINUOUS)` creates a *section* break (body-level element between paragraphs), not a *column* break (inline element within a paragraph). These are fundamentally different element types.
2. **Section breaks skipped on pull:** `xml_converter.py:234-235` skips all `sectionBreak` elements with `continue`, so even the resulting section break is lost.

**Impact:** Column breaks should be reclassified as read-only (like `<hr/>` and `<image/>`). They can be read from existing documents but cannot be added via the API.

**Files:** `generators/content.py` — special element handling, `xml_converter.py:234` — sectionBreak skip

---

### 12. Tab Rename Not Applied

**Severity:** Moderate — changing tab title has no effect
**Symptoms:** Changing `title="Tab 1"` to `title="Main Report"` on an existing tab is ignored.

**Root Cause:** The diff engine either does not detect tab title changes, or there is no code to generate `updateDocumentTab` requests for title changes.

**Files:** `walker.py` or `differ.py` — tab property change detection

---

### 13. Meta Title Change Not Applied

**Severity:** Minor — document title in Google Drive unchanged
**Symptoms:** Changing `<title>` in `<meta>` has no effect on the Google Docs document title.

**Root Cause:** The Google Docs `batchUpdate` API does not support changing the document title. Title changes require `documents.patch()` or the Drive API. This is likely a missing feature rather than a bug.

**Files:** `push.py` — no title update API call

---

### 14. Muted Text Style Bleeds Across Paragraph Boundary

**Severity:** Moderate — inline text style range is miscalculated
**Symptoms:** The muted style (9pt gray) applied to the last paragraph leaks. The span wraps most of the text but misses the last 2 characters: `<span class="I5tq1">...renderin</span>g.`

**Root Cause:** The text style range end index is off by a small amount, likely related to UTF-16 index calculation for surrounding content or an off-by-one in the text run range.

**Files:** `generators/content.py` — `updateTextStyle` range calculation

---

### 15. Page Break Inherits Wrong Paragraph Style

**Severity:** Major — page breaks create paragraphs with wrong heading level
**Symptoms:** A `<pagebreak/>` after a heading inherits the heading's `namedStyleType`, creating a visible heading-styled empty paragraph.

**Root Cause:** Page-break-only paragraphs skip the `namedStyleType` setting. The `insertPageBreak` API call creates a new paragraph that inherits the named style from the text at the insertion point. If the preceding paragraph is a heading, the page break paragraph becomes a heading too.

**Files:** `generators/content.py` — page-break-only paragraphs skip namedStyleType

---

### 16. Multiple Deletes in Same Segment Can Hit Segment-End Constraint

**Severity:** Major — push fails with API 400 error

**Symptoms:** When a push modifies content that includes a footnote reference deletion plus other content changes in the same segment, the API returns: `"The range cannot include the newline character at the end of the segment."`

**Root Cause:** When the diff produces multiple `deleteContentRange` requests within the same segment, they are ordered from highest to lowest index. Each delete shrinks the document. A lower-index delete's `endIndex` (computed against pristine) can become the new segment end after higher-index deletes execute, causing it to include the segment-end newline.

Example: pristine segment is 157 chars. Delete 127-156 (clamped for segment end) + delete 108-109 (footnote ref) reduces segment to 127 chars. Then delete 23-127 now reaches the segment end.

**Files:** `generators/content.py` — `_modify()` delete range calculation, `walker.py` — request ordering

---

## API Limitations (Cannot Fix)

### Checkbox Lists Create Regular Bullets

`type="checkbox"` list items become regular bullet items. The `BULLET_CHECKBOX` preset is accepted by the API but creates lists with `glyphType: GLYPH_TYPE_UNSPECIFIED`. Real checkboxes use a different internal mechanism not exposed via the Docs API.

**Workaround:** Use Unicode checkbox symbols manually (`☐ ☑ ☒`) in text content.

---

## Not Implemented

| Feature | API Available? | Notes |
|---------|---------------|-------|
| Images | Yes — `insertInlineImage` | Takes a public URI. Not yet implemented in extradoc. |
| Person mentions | Yes — `insertPerson` | Takes `personProperties`. Not yet implemented in extradoc. |
| Date elements | Yes — `insertDate` | Takes `dateElementProperties`. Not yet implemented in extradoc. |
| Autotext (page numbers) | No | No `insertAutoText` API exists |
| Horizontal rules | No | No `insertHorizontalRule` API exists — read-only |
| Column breaks | No | No `insertColumnBreak` API exists — `insertSectionBreak` is different (see bug #11) |

---

## Features Working Correctly

The following features were verified as working correctly through the round-trip test:

| Feature | Notes |
|---------|-------|
| Headings (h1-h6, title, subtitle) | All 8 heading types round-trip correctly |
| H1 spacing (spaceAbove/spaceBelow) | Direct attributes on h1 preserved |
| Basic paragraphs | Content preserved exactly |
| Bold, italic, underline, strikethrough | All inline formatting works |
| Superscript, subscript | Works correctly |
| Hyperlinks | URL and display text preserved |
| Text colors and backgrounds | All color/highlight styles applied via `<span>` |
| Font changes (family, size) | Custom fonts like Georgia, Courier New work |
| Simple bullet lists | Single-level bullets work |
| Simple numbered lists (decimal) | Single-type numbered lists work |
| Roman numeral lists | `type="roman"` works correctly |
| Nested lists (same type) | 4-level deep nesting works |
| Basic tables (no cell styling) | Content in cells preserved |
| Table column widths on new tables | `<col>` width attributes applied correctly |
| Multi-paragraph table cells | Multiple `<p>` in a `<td>` works |
| Lists inside table cells | `<li>` within `<td>` works |
| Colspan attribute round-trip | `colspan` preserved through pull (visual merge not applied) |
| `<style>` wrapper element | Transfers `class` to wrapped children correctly |
| Named styles on text spans | `class` attributes on `<span>` apply text styles |
| Paragraph alignment (END, JUSTIFIED, CENTER) | Applied correctly on individual paragraphs |
| Line spacing (150%, 200%) | Applied correctly on individual paragraphs |
| Indent left | Applied correctly on individual paragraphs |
| Page break | `<pagebreak/>` inserted correctly (but see bug #15 for style) |
| Tab creation | `addDocumentTab` creates tab with title (but see bug #3 for content) |
| Header/footer creation | Structure created (but see bug #2 for content) |
| Footnote creation | Reference created (but see bugs #5 for content/position) |
| Unicode and special characters | Emoji (🚀📈✅), ™, ©, ¥, €, £, smart quotes, em/en-dash, ellipsis all preserved |
| Code block via style wrapper | Courier New + background via `<style class="code">` works |
| Block quote via style wrapper | Italic + indent + color via `<style class="quote">` works |
