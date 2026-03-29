# ExtraDoc End-to-End Testing — Historical Bugs & Limits

This file is historical. Several items below were fixed during the
`reconcile_v2` cutover. For the current release contract, use:

- `client/src/extrasuite/client/help/doc/README.md`
- `client/src/extrasuite/client/help/doc/troubleshooting.md`
- `extradoc/docs/release-checklist.md`

Test document: https://docs.google.com/document/d/1rVowMhvK4p8BCtWrGlIUGg96gE9huIPw2VfPNfcz02o
Testing date: 2026-03-03
Method: Using only `--help` documentation as the guide.

---

## BUG-1: `<sectionbreak>` deletion not documented as read-only

**Severity:** High (push fails)
**Symptom:** `Error: Section break deletion is not supported`
**How triggered:** Rewrote the full body of a tab, omitting the `<sectionbreak>` element from the original pulled document. Also triggered when creating a new tab without a `<sectionbreak>` as the first body element.
**Expected (per --help):** The critical rules section lists `<hr/>`, `<image/>`, `<autotext/>` as read-only. `<sectionbreak>` is not mentioned at all.
**Actual:** diff/push fails immediately.
**Fix needed:** Add `<sectionbreak>` to the critical rules section in `--help` as a read-only, non-removable element required in every tab body.

---

## BUG-2: `<footnote>` insertion fails at diff time

**Status:** Fixed in `reconcile_v2`

**Severity:** High (advertised feature completely non-functional)
**Symptom:** `Error: Cannot insert paragraph containing non-text elements (pageBreak, horizontalRule, inlineObject, footnoteReference). Use the appropriate API requests directly.`
**How triggered:** Added `<footnote>` inline inside a `<t>` element, as documented in `--help`.
**Expected (per --help):** `<footnote>` is listed as a supported block tag "(inline at the marker position)" and is not listed as read-only.
**Actual:** Fails at `diff` time before any API call is made.
**Fix needed:** Implement footnote insertion support or mark `<footnote>` as read-only in `--help`.

---

## BUG-3: `<pagebreak/>` insertion fails at diff time

**Status:** Fixed

**Severity:** High (advertised feature completely non-functional)
**Symptom:** `Error: Cannot insert paragraph containing non-text elements (pageBreak, horizontalRule, inlineObject, footnoteReference). Use the appropriate API requests directly.`
**How triggered:** Added `<pagebreak/>` as a block element between two headings.
**Expected (per --help):** `<pagebreak/>` is explicitly documented as "(can add/delete)".
**Actual:** Fails at `diff` time.
**Fix:** Implemented `InsertPageBreakRequest` support in `_generators.py`. Added `_is_pagebreak_paragraph()` helper, `_make_insert_page_break()` request builder, updated all three inner-gap loops and the trailing-gap handler to emit `insertPageBreak` instead of `insertText` for pagebreak paragraphs. Mock updated to actually insert the pagebreak element into the document structure. Pagebreaks in non-body segments (headers, footers, table cells) raise `ReconcileError`.
**Note:** Pagebreaks in the trailing gap with a non-sectionbreak left anchor insert at `_el_end(left_anchor) - 1` (same as table inserts). In the real workflow, both base and desired have a trailing empty paragraph (added by serde), so trailing-gap pagebreaks appear as inner-gap inserts. The edge case of inserting a pagebreak with no trailing empty paragraph in the base is not supported.

---

## BUG-4: Adding new bullet/list items at end of a tab body causes API 400

**Severity:** High (push fails)
**Symptom:** `API error (400): Invalid requests[1].updateParagraphStyle: Index N must be less than the end index of the referenced segment, N.`
**How triggered:** Added a new section containing `<li type="bullet">` items at the end of any tab's body. Tested in:
- Tab_1 (first tab) — fails
- Appendix (second tab) — same error
Tested with mixed list types (bullet + decimal), bullet-only — always fails.
**Root cause:** The reconciler generates an `updateParagraphStyle` request with `startIndex == endIndex` (zero-length range), which the Google Docs API rejects.
**Workaround:** To add new list items, append `<li parent="kix.xxx">` to an **existing list** (using an existing parent list ID). New top-level sections with lists fail. Alternatively, place a non-list element after the list so it's not at the end of the tab body.
**Fix needed:** Fix index calculation in the reconciler when inserting list items at the end of a tab's body segment.

---

## BUG-5: Mixed inline content in `<t>` silently drops surrounding plain text (DATA LOSS)

**Severity:** Critical (silent data corruption, no error raised)
**Symptom:** Surrounding plain text is dropped; only the inline-formatted portion survives.
**How triggered:** Wrote inline formatting mixed with plain text inside a single `<t>` element, as shown in `--help`:
```xml
<p><t>ExtraSuite is an <b>open-source</b> CLI tool designed for AI agents...</t></p>
```
**Expected (per --help):** The `--help` explicitly shows this syntax as valid:
```
<p>A paragraph with <b>bold</b> and <i>italic</i> text.</p>
```
**Actual after push + re-pull:**
```xml
<p><t><b>open-source</b></t></p>
```
The entire sentence was destroyed — only the bold text survived.
**Confirmed in multiple locations:** Any `<b>`, `<i>`, or other inline element mixed with plain text in a single `<t>` drops all surrounding plain text.
**Workaround (confirmed working):** Use separate `<t>` elements — one per text run:
```xml
<p>
  <t>ExtraSuite is an </t>
  <t><b>open-source</b></t>
  <t> CLI tool designed for AI agents...</t>
</p>
```
This is also the format that pull produces and round-trips correctly.
**Fix needed:** The reconciler must split mixed-content `<t>` nodes into separate runs, or raise a parse error. The `--help` example is also misleading and must show the multi-`<t>` pattern.

---

## BUG-6: Hyperlinks `<a href="...">` are silently dropped (DATA LOSS)

**Severity:** Critical (silent data loss, no error raised)
**Symptom:** The hyperlink element and its text are completely absent from the re-pulled document.
**How triggered:** Added a hyperlink inside a `<t>` element mixed with other text:
```xml
<t>Project: <a href="https://github.com/think41/extrasuite">github.com/think41/extrasuite</a>.</t>
```
**Expected (per --help):** `<a href="...">` is listed as a supported inline element.
**Actual:** After push and re-pull, both the hyperlink and surrounding text are entirely gone. No error raised.
**Note:** Likely a consequence of BUG-5 (mixed inline content). Isolated hyperlink testing (`<t><a href="...">link text</a></t>`) was not completed.
**Fix needed:** Fix BUG-5 first; then test isolated hyperlinks to confirm they work.

---

## BUG-7: Adding a new tab requires `styles.xml` — not documented

**Severity:** Medium (diff fails until worked around)
**Symptom:** `Error: [Errno 2] No such file or directory: '.../NewTab/styles.xml'`
**How triggered:** Added a new tab to `index.xml` and created `NewTab/document.xml` as documented in `--help`, but did not create `styles.xml`.
**Expected (per --help):** No mention of needing a `styles.xml` in the new tab folder.
**Actual:** diff fails immediately.
**Workaround:** Create an empty `styles.xml` (`<styles />`) in the new tab folder alongside `document.xml`.
**Fix needed:** Document the requirement, or automatically create `styles.xml` with defaults when a new tab folder is detected.

---

## BUG-8: Header/footer on a new tab get created on the wrong (existing) tab

**Status:** Explicitly rejected in `reconcile_v2`; still a Docs API limitation

**Severity:** High (header/footer created on wrong tab, push partially fails)
**Symptom:** API 400 `Segment with ID kix.xxx was not found`; header/footer content not applied.
**How triggered:** Added `<header>` and `<footer>` elements to a new tab's `document.xml` when pushing simultaneously with other changes.
**Actual end state:**
- New tab (Appendix) was created successfully ✅
- `createHeader`/`createFooter` were associated with the existing Tab_1 instead of Appendix ❌
- Tab_1 has unintended empty header/footer ❌
- Appendix has no header/footer ❌
- Batch 2 (write header/footer content) fails with "Segment ID not found" ❌

**Root cause analysis (2026-03-03):**

Headers and footers are **per-tab** objects in the Google Docs data model. The `DocumentTab` type has its own `headers` and `footers` dicts, and its own `documentStyle.defaultHeaderId`/`defaultFooterId`. Each tab independently owns its header/footer segments.

The `CreateHeaderRequest` (`docs/googledocs/api/CreateHeaderRequest.md`) takes two fields:
- `type` — the header type (DEFAULT, FIRST_PAGE, EVEN_PAGE)
- `sectionBreakLocation` — a `Location` (which includes `tabId`) identifying the section break that begins the target section

To create a header for a specific tab, you must pass `sectionBreakLocation.tabId`. However, the reconciler deliberately omits `sectionBreakLocation` because **specifying it (even with a valid index) causes a Google Docs API 500 error**. Without `sectionBreakLocation`, `createHeader` applies to the DocumentStyle of the **first tab**, not the newly-created tab.

The consequence: `createHeader` always creates the header on Tab_1. Then `_reconcile_new_segment` tries to populate the header's content using `tab_id = DeferredID("new_tab")` — but the header belongs to Tab_1, so the API can't find the segment and returns 400.

**Why there is no simple fix:**
The `sectionBreakLocation` 500-error is a Google Docs API bug. Until it is resolved, there is no reliable way to create a header specifically for a newly-added tab when other tabs already exist. The correct handling depends on:
- **Base has no tabs (first tab ever):** `createHeader` with no `sectionBreakLocation` correctly targets the new tab → safe
- **Base has existing tabs + new tab wants header:** `createHeader` goes to Tab_1 → wrong tab, no clean workaround

**Fix needed:** Raise `ReconcileError` when a new tab (added to a document that already has existing tabs) includes a `<header>` or `<footer>`. This converts the silent wrong-tab corruption into an explicit error with a clear workaround message. The error should direct users to: (1) push the new tab first without header/footer, (2) re-pull, (3) add the header/footer in a second push.

**References:**
- `docs/googledocs/api/CreateHeaderRequest.md` — no `tabId` field; only `sectionBreakLocation.tabId` targets a specific tab
- `docs/googledocs/api/CreateFooterRequest.md` — same structure
- `docs/googledocs/api/DocumentTab.md` — `headers` and `footers` are per-tab fields
- `docs/googledocs/api/DocumentStyle.md` — `defaultHeaderId`/`defaultFooterId` are per-tab (live on `DocumentTab.documentStyle`)

---

## BUG-9: Editing a list item to replace text with multi-run content fails when combined with other changes

**Severity:** Medium (push fails when combined with header/footer or other changes)
**Symptom:** `API error (400): Invalid requests[N].deleteContentRange: Invalid deletion range. Cannot delete the requested range.`
**How triggered:** In a single push that included:
  1. Editing a list item text with inline formatting (multi-run `<t>`)
  2. Header/footer content (re-appearing in diff due to stale pristine)
  3. Appendix content
**Note:** When the same list item edit was pushed IN ISOLATION (no other changes), it succeeded (1 change applied).
**Root cause:** Index management error in the reconciler when header/footer insertText is combined with body deleteContentRange in the same batch.
**Workaround:** Push inline-formatting list item edits without other concurrent changes.

---

## BUG-10: `<span class="...">` text content is silently dropped (DATA LOSS)

**Severity:** Critical (silent data loss, no error raised)
**Symptom:** The span's text content is absent from the re-pulled document; surrounding text survives but span text is lost.
**How triggered:** Added a `<span class="code">` element in its own `<t>` element:
```xml
<t><span class="code">extrasuite &lt;module&gt; &lt;command&gt; [args]</span></t>
```
**Expected (per --help):** `<span class="...">` is listed as a supported inline element.
**Actual:** After push + re-pull, the span run is entirely absent. The preceding plain text `<t>` survived, but the span text did not.
**Fix needed:** Implement `<span class>` insertion or raise an error instead of silently dropping the content.

---

## VERIFIED WORKING

The following operations were tested and confirmed to work correctly:

| Operation | Details |
|-----------|---------|
| `extrasuite doc create` | Creates document and shares with service account ✅ |
| `extrasuite doc pull` | Downloads and converts to local folder ✅ |
| `extrasuite doc push` | Applies changes; reports "Applied N document changes" ✅ |
| `extrasuite doc push --verify` | Pushes and auto-re-pulls to confirm ✅ |
| `extrasuite doc diff` | Offline, no auth required ✅ |
| Initial large push | 535 changes applied (full 13-section document with tables, lists, headings) ✅ |
| Subtitle text edit | Plain text change in `<subtitle>` ✅ |
| Heading text rename | Changed `<h1>` text ✅ |
| Paragraph text edit | Changed `<p><t>` content ✅ |
| New paragraph (plain text) | Added `<p><t>text</t></p>` ✅ |
| New paragraph (multi-run) | `<t>plain </t><t><b>bold</b></t><t> plain</t>` round-trips correctly ✅ |
| **Bold** `<t><b>text</b></t>` | Works when bold is sole content of `<t>` ✅ |
| **Italic** `<t><i>text</i></t>` | Works ✅ |
| **Strikethrough** `<t><s>text</s></t>` | Works ✅ |
| **Underline** `<t><u>text</u></t>` | Works ✅ |
| Inline style applied to existing list item | Changed `<li>` to multi-run format — works ✅ |
| New list item on existing list | Append `<li parent="kix.xxx">` to existing list ✅ |
| New table row | Added row to existing table ✅ |
| Table cell content edit | Changed cell text ✅ |
| New `<h1>`/`<h2>`/`<p>` section | New section with only headings and paragraphs ✅ |
| Multi-tab: new tab creation | Add entry to `index.xml` + create folder with `document.xml` + `styles.xml` ✅ |
| Header content | Filled content into an existing empty header ✅ |
| Footer content | Filled content into an existing empty footer ✅ |

---

## KNOWN LIMITATIONS (by design)

- **No new top-level comments:** Google Docs API does not support adding top-level comments. Only replies to existing comments can be added via `comments.xml`.
- **Read-only elements:** `<hr/>`, `<image/>`, `<autotext/>`, `<sectionbreak>` cannot be added or removed.

---

## UNTESTED

- `extrasuite doc create --copy-from`
- `extrasuite doc share`
- Deleting an existing `<li>` item (removal)
- Deleting an existing paragraph
- Hyperlink `<a href>` in isolation (not mixed with plain text)
- `<span class>` with custom class defined in `styles.xml`
- Checkbox list type (`type="checkbox"`)
- Alpha/roman list types
- Nested list levels beyond level 1
- `extrasuite doc help` reference topics

---

## ROOT CAUSE ANALYSIS

### Cluster 1 — TNode model too narrow: the silent data-loss root (BUG-5, BUG-6, BUG-10)

These three bugs share one root cause: the `<t>` parser in `serde/_models.py:_inlines_from_element`.

`TNode` models a single text run: `text + optional_class + optional_sugar_tag`. The parser for `<t>` element content was:

```python
sugar_tag, text = None, child.text or ""
for sub in child:
    if sub.tag in _SUGAR_TAGS:
        sugar_tag = sub.tag
        text = sub.text or ""   # OVERWRITES text
        break
inlines.append(TNode(text=text, …))
```

For `<t>ExtraSuite is an <b>open-source</b> CLI tool</t>`:
- `child.text = "ExtraSuite is an "` → stored in `text`
- Loop finds `<b>` → **overwrites** `text` with `"open-source"`, sets `sugar_tag = "b"`
- All surrounding text is gone. No error raised. (BUG-5)

For `<t><span class="code">text</span></t>`: `span` is not in `_SUGAR_TAGS`, so the loop passes it and the TNode gets `text = ""`. The span content is gone. (BUG-10)

For `<t><a href="...">link</a></t>`: same — `a` not in `_SUGAR_TAGS`, link silently dropped. (BUG-6)

Additionally, the `<a>` parser at `<p>` level only accepted `<t>` child nodes (`child.findall("t")`), so `<a href="...">plain text</a>` produced a LinkNode with no children → no text runs → dropped content.

**Fix applied (2026-03-03):** `_inlines_from_element` now handles mixed content inside `<t>` by splitting into multiple TNodes (preserving leading text, child-element content, and tails). A new `_t_child_to_inlines` helper handles sugar tags, `<span>`, and `<a>` children. The `<a>` parser now also accepts plain text children at `<p>` level.

The canonical multi-`<t>` form that `pull` produces continues to work identically.

### Cluster 2 — Unimplemented features in reconciler (BUG-2, BUG-3)

The reconciler inserts new paragraphs via `insertText(\n) → updateParagraphStyle`. The Google Docs API explicitly rejects `insertText` for paragraphs containing non-text elements: `pageBreak`, `footnoteReference`, `inlineObject`, `horizontalRule`.

**BUG-3 (`<pagebreak/>`):** `<pagebreak/>` is correctly parsed and deserialized into a `{pageBreak: {}}` paragraph element. The reconciler now detects such paragraphs via `_is_pagebreak_paragraph()` and emits `InsertPageBreakRequest` (2 chars: pageBreak element + `\n`) instead of `insertText`. Fixed 2026-03-03.

**BUG-2 (`<footnote>`):** Footnote insertion requires `createFootnoteRequest` (multi-batch with DeferredID), similar to how tab creation works. It's a planned future feature (`extradoc/CLAUDE.md` notes "Phase 4+"). Until implemented, `<footnote>` should be removed from the supported block tags in `--help`.

### Cluster 3 — Reconciler edge cases (BUG-4, BUG-8, BUG-9)

**BUG-4 (list at end of segment):** Off-by-one in `_generators.py`. When inserting list items at the very end of a body segment, `updateParagraphStyle` gets `startIndex == endIndex` (zero-length range), which the API rejects. The end-of-segment boundary case needs a specific fix and test.

**BUG-8 (header/footer on wrong tab):** `createHeader/createFooter` is document-level — the API has no `tabId` field on these requests. In `_reconcile_new_segment`, the code passes `tab_id = DeferredID("tab_1")` into `_make_create_header`. The API ignores/misroutes this and creates the header on the existing first tab. Fix: never pass `tabId` to `createHeader`/`createFooter` calls.

**BUG-9 (multi-change batch):** Cross-segment index ordering. The reconciler accumulates body changes and header/footer content changes into the same batch. When combined with stale pristine state (causing header re-diffs), the request ordering within a batch can put a header `insertText` before a body `deleteContentRange`, invalidating the body's target index. Fix: either isolate segment content changes into separate batches, or strictly order: all deletions before insertions, all higher indices first.

### Cluster 4 — Documentation gaps (BUG-1, BUG-7)

**BUG-1 (`<sectionbreak>`):** Already fully documented in `extradoc/CLAUDE.md` (developer notes) but absent from user-facing `--help`. The better fix is to make `<sectionbreak>` invisible to agents entirely: strip on serialize if it's the mandatory first element, inject synthetically on deserialize. Until then, it must appear in `--help` critical rules.

**BUG-7 (`styles.xml` required):** The deserializer unconditionally reads `styles.xml`. Fix: auto-generate a minimal valid `styles.xml` when the file is missing for a new tab folder, rather than raising `FileNotFoundError`.

---

## PRIORITIZATION

| Priority | Bug | Fix Type | Status |
|----------|-----|----------|--------|
| **P0 — Critical (data loss, silent)** | | | |
| BUG-5 Mixed `<t>` content | Parser fix in `_models.py` | ✅ Fixed 2026-03-03 |
| BUG-10 `<span>` in `<t>` | Same fix | ✅ Fixed 2026-03-03 |
| BUG-6 Hyperlinks dropped | Parser fix + `<a>` plain text | ✅ Fixed 2026-03-03 |
| **P1 — High (advertised but broken)** | | | |
| BUG-3 `<pagebreak/>` insert | Wire up `InsertPageBreakRequest` | ✅ Fixed 2026-03-03 |
| BUG-4 List at end of segment | Off-by-one in `_generators.py` | ✅ Fixed 2026-03-03 |
| BUG-8 Header on wrong tab | API limitation — `sectionBreakLocation` 500s; raise ReconcileError instead | 🔬 Analysed — parked (API bug) |
| **P2 — Medium (workarounds exist)** | | | |
| BUG-9 Multi-change batch ordering | Batch isolation for segments | ⬜ Open |
| BUG-7 `styles.xml` not auto-generated | Auto-generate on missing file | ✅ Fixed 2026-03-03 |
| BUG-1 `<sectionbreak>` docs | Add to `--help` critical rules | ✅ Fixed 2026-03-03 |
| **P3 — Defer (high complexity)** | | | |
| BUG-2 `<footnote>` insertion | Multi-batch DeferredID pattern (Phase 4+) | 📋 Deferred — removed from `--help` |
