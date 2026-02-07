# ExtraDoc Implementation Gaps

This document tracks bugs, limitations, and implementation gaps discovered during testing.

**Last Updated:** 2026-02-07

---

## Critical Bugs

### Massive Content Scrambling During Wholesale Rewrite

**Status:** Open
**Discovered:** 2026-02-07

When making major structural changes (replacing entire body with completely different content), the diff algorithm produces severely disordered output. Paragraphs, bullet points, and sections are mixed up and placed at wrong locations throughout the document. Push reports success (214 requests applied) but the resulting document is garbled.

**Reproduction:**
1. Pull a document with a full resume (headings, paragraphs, bullet lists)
2. Replace entire body with a completely different person's resume in a different format (different headings, different structure, tables added, different list types)
3. Push succeeds, but re-pull reveals content scrambled

**Specific symptoms observed:**
- Title/subtitle placed near bottom of document instead of top
- Heading text split across two elements (`<h1>E</h1>` and `<h1>xperience</h1>` from `<h1>Experience</h1>`)
- Job descriptions mixed between wrong employer headings
- Awards section content scattered into Experience section
- Numbered list items from one section appearing under unrelated headings

**Root Cause:** The LCS-based diff alignment produces incorrect paragraph mappings when nearly every paragraph changes. The backwards walk invariant may break when there are many overlapping add/delete operations from a poor diff match.

**Workaround:** For major rewrites, perform in two steps:
1. Delete all content, push
2. Pull fresh, add new content, push

---

## Major Bugs

### Paragraph Order Swapped Near Headings

**Status:** Open
**Discovered:** 2026-02-07

When inserting content into an empty document, paragraphs adjacent to headings can appear in the wrong order. Specifically, a `<p>` written immediately after an `<h1>` appeared before the `<h1>` after push+pull.

**Reproduction:**
1. Start with an empty document (body contains only `<p></p>`)
2. Write `<h1>SARAH CHEN</h1>` followed by `<p><b>Senior Software Engineer</b></p>`
3. Push, then pull
4. The `<p>Senior Software Engineer</p>` appears BEFORE `<h1>SARAH CHEN</h1>`

---

### Tab Creation Silently Fails

**Status:** Open
**Discovered:** 2026-02-07

Adding a `<tab>` element with content to the document XML results in the tab being completely absent after push. No error is reported during push — all requests are reported as "successfully applied" — but the tab and its content are simply lost.

**Reproduction:**
1. Pull a single-tab document
2. Add `<tab id="t.cover" title="Cover Letter" class="_base"><body>...content...</body></tab>`
3. Push (reports success, e.g., "177 changes applied")
4. Pull — the tab is completely missing

---

### Table Column Operations Fail

**Status:** Open
**Discovered:** 2026-02-07

Changing the number of columns in an existing table fails with API error:
```
Invalid requests[33].insertTableColumn: Invalid table start location.
Must specify the start index of the table.
```

**Workaround:** Delete the entire table and create a new one with the desired column count in two separate push operations.

---

### Phantom Empty Elements After Push

**Status:** Open
**Discovered:** 2026-02-07

After a push operation, re-pulling the document reveals empty elements that were not in the source XML (empty headings `<h2></h2>`, empty list items). May be related to index calculation errors leaving orphan newlines, or request ordering issues creating empty paragraphs that inherit styles.

**Workaround:** Manually delete empty elements after push, or ignore them if they don't affect document appearance.

---

### Base Font Style Changes Not Applied

**Status:** Open
**Discovered:** 2026-02-07

Changing the `font` attribute in the `_base` style in `styles.xml` does not affect the pushed document. The document retains its original font.

**Workaround:** Apply font changes via explicit `class` attributes on individual elements rather than via `_base`.

---

### Decimal Lists Converted to Bullet Lists

**Status:** Open
**Discovered:** 2026-02-07

Some items written as `type="decimal"` round-trip as `type="bullet"` after push+pull. Observed in the Awards section during the wholesale rewrite test. May be a symptom of the content scrambling bug rather than an independent issue.

---

## API Limitations (Cannot Fix)

### Checkbox Lists Do Not Work

`type="checkbox"` list items become regular bullet items instead of checkboxes. The `BULLET_CHECKBOX` preset is accepted by the API but creates lists with `glyphType: "GLYPH_TYPE_UNSPECIFIED"`. Real checkboxes use a different internal mechanism not exposed via the API.

**Workaround:** Use Unicode checkbox symbols manually (☐ ☑ ☒) in text content.

---

## Not Implemented

| Feature | Notes |
|---------|-------|
| Checkbox lists | API limitation — BULLET_CHECKBOX preset doesn't create real checkboxes |
| Autotext (page numbers) | API doesn't support insertion |
| Images | Requires separate Drive upload flow |
| Person mentions | Requires verified email + special API |
| Horizontal rules | Read-only — cannot add/remove via API |

---

## Partially Working Features

| Feature | Status | Notes |
|---------|--------|-------|
| Footnotes (push) | Needs testing | Code exists, needs end-to-end verification |
| `<style>` wrapper element | Needs testing | For applying class to multiple consecutive elements |
| Column breaks | Needs testing | `<columnbreak/>` element |

---

## Observations

| Observation | Details |
|------------|---------|
| Bold/italic text gets wrapped in span+class on round-trip | `<b>text</b>` round-trips as `<span class="JF4QL"><b>text</b></span>`. Style factorizer creates classes for bold/italic properties. Not a functional bug but makes the XML noisier. |
| Quotes get XML-escaped on round-trip | `"text"` becomes `&quot;text&quot;`, apostrophes become `&#x27;`. Standard XML behavior. |
| Tables gain IDs and cell classes on round-trip | After push, table elements get Google-assigned IDs and cell classes. Expected behavior. |

---

## Fixed Bugs

### Fixed: Table Delete Fails with `KeyError: 'startIndex'`

`_generate_table_delete_requests()` tried to access `table_info["startIndex"]`, but `_parse_table_xml()` only returns `{"rows", "cols", "id"}`. Fixed to look up the table start index from `pristine_table_indexes`.

### Fixed: Index Calculation Error When Modifying and Adding Content

Insert indexes weren't adjusted to account for document shrinkage caused by preceding deletes. Fixed by adding index adjustment logic after reordering.

### Fixed: Content Merging (Missing Newlines)

When multiple content blocks were inserted at the same position, all stripped trailing newlines because they all detected themselves as "at segment end". Fixed with `segment_end_consumed` flag tracking.

### Fixed: Bullets Not Being Removed

Converting from `<li>` to `<p>` left bullet formatting. Fixed by generating `deleteParagraphBullets` requests for non-bullet paragraphs.

### Fixed: Table Content Destroyed During Body Edits

Adding content to a body containing tables destroyed table structure. Fixed by skipping merged approach when tables are present.

### Fixed: Table Content Not Inserted Into Cells

New tables were created empty. Fixed with two-phase approach: insert table structure, then populate cells.

### Fixed: Custom Styles Not Applied on Push

`class` attributes on paragraphs weren't resolved to style properties. Fixed by adding class attribute resolution in paragraph parsing.

### Fixed: Invalid Bullet Presets for Alpha/Roman Lists

Updated `alpha` to `NUMBERED_UPPERALPHA_ALPHA_ROMAN` and `roman` to `NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL`.

### Fixed: Request Ordering Issues (Page Break)

`insertPageBreak` requests were reordered before text content. Fixed with `_skipReorder` marker.

### Fixed: Header/Footer Creation Fails

Headers/footers with new IDs detected as ADDED instead of MODIFIED. Fixed by matching headers/footers by type only.

### Fixed: Base Style Corruption on Pull

`_base` style was computed from most frequent text properties instead of `NORMAL_TEXT` named style. Fixed to extract from `namedStyles.NORMAL_TEXT`.

### Fixed: List Items Merged With Headings

Could not reproduce on 2026-02-06. Marking as resolved pending further reports.

### Fixed: Nested List Levels Incorrect

Could not reproduce on 2026-02-06. All nesting levels preserved correctly after push/pull cycle.
