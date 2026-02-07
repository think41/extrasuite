# ExtraDoc Diff Specification Review

This document identifies potential risks, functional gaps, and specification errors in `@docs/extradoc-diff-specification.md`.

## 1. Critical Risks (Data Corruption / Index Errors)

### 1.1 Table Index Drift (The "Mixed State" Bug)
**Severity: Critical**
**Location:** Section 10.4 and Section 11

The specification defines an execution order for table modifications where **Cell Content Modifications** (Phase 2/3) occur *before* **Row/Column Insertions** (Phase 3/4) in the batch request.

*   **The Problem:**
    *   Content modifications (Phase 2) change the length of the document (adding/removing text).
    *   Structural insertions (Phase 4) insert empty cells, which must then be populated.
    *   Section 10.4 states: *"Compute the cell content start ... treating existing cells as their **pristine length** and new cells as length 1"*.
    *   **This is incorrect.** By the time Phase 4 executes, the "existing cells" preceding the new row may have already been modified in Phase 2, changing their length. Using the "pristine length" ignores these changes, causing the calculated index for the new cells to be wrong. This will lead to writing content into the wrong location or API errors.

*   **Example:**
    1.  Table has 1 row. Cell (0,0) length is 5.
    2.  Diff: Modify Cell (0,0) (add 100 chars) AND Insert Row 1.
    3.  Execution Order:
        *   Modify Cell (0,0) -> Length becomes 105.
        *   Insert Row 1 -> Inserts empty row at end.
        *   Populate Row 1 -> Needs index. Spec says: `table_start + row_0_pristine_len (5) + ...`. Calculated Index: `Start + 5`. Actual Target: `Start + 105`.
    4.  Result: The insert targets `Start + 5`, which is now inside the expanded Cell (0,0). Corruption.

*   **Recommendation:** The request generator must track the *accumulated length delta* caused by Phase 2 modifications and apply it when calculating indexes for Phase 3/4 content insertions. A static "pristine" view is insufficient for operations scheduled *after* modifications.

### 1.2 Footnote Reference Location
**Severity: High**
**Location:** Section 12.1

The spec states: *"Adding a footnote: `createFootnote` at `endOfSegmentLocation`"*.

*   **The Problem:** `createFootnote` inserts a footnote *reference* into the document text. Using `endOfSegmentLocation` would place every new footnote reference at the very end of the document body (or segment), regardless of where the user actually added the `<footnote>` tag in the XML.
*   **Recommendation:** `createFootnote` should be treated like any other inline element insertion. It must be inserted at the `pristine_start` (or current insertion point) within the content flow of the ContentBlock, just like text.

## 2. Functional Gaps (Data Loss / UX Issues)

### 2.1 Loss of Comments and Suggestions
**Severity: High**
**Location:** Section 9.3 (MODIFIED ContentBlock)

The spec handles modification by **Deleting** the old content and **Inserting** new content.

*   **The Problem:** Deleting content removes all associated metadata, including **Comments** and **Suggested Edits**.
*   **Impact:** In a collaborative environment, if a user fixes a typo in a paragraph that has a comment attached to a different word, the entire paragraph is replaced, and the comment is lost.
*   **Recommendation:** This might be an acceptable trade-off for "declarative to imperative" simplicity, but it must be documented as a known limitation. Ideally, the diff engine would use finer-grained diffs (text-only insertions/deletions) to preserve anchors where possible, but that adds significant complexity.

### 2.2 List Continuity Breaking
**Severity: Medium**
**Location:** Section 9.2 Step 5

The spec uses `createParagraphBullets` with a `bulletPreset` when inserting/modifying list items.

*   **The Problem:** If a user modifies the text of an item in the middle of a list, the item is deleted and re-inserted. Applying `createParagraphBullets` creates a **new list** (new `listId`).
*   **Impact:** The list will likely break visually or structurally (e.g., numbering resets: 1, 2, 1, 4).
*   **Recommendation:** The logic needs to handle `listId` preservation. If the item is adjacent to an existing list, the API *might* auto-merge, but explicit handling (using `createParagraphBullets` is destructive to existing membership) is risky. Consider if `updateParagraphStyle` can be used to join lists or if `createParagraphBullets` behavior needs verification.

### 2.3 Missing Image Support
**Severity: Medium**
**Location:** Section 9.2 (ADDED ContentBlock)

The spec explicitly mentions `insertPageBreak` and `insertSectionBreak` in Step 3, but omits **Images**.

*   **The Problem:** If the XML contains `<img ...>`, the spec provides no instruction on how to generate the `InsertInlineImageRequest`.
*   **Impact:** Images added in XML will likely be ignored or cause the diff engine to crash/fail if it encounters an unknown element type.
*   **Recommendation:** Add `insertInlineImage` to the supported operations in Section 9.2. Note that this requires handling image source URIs (fetching/uploading), which is a non-trivial subsystem.

## 3. Ambiguities & Minor Issues

### 3.1 Horizontal Rule Handling
**Location:** Section 12.2

The spec says HRs are read-only and changes involving them should be skipped.
*   **Ambiguity:** If a user *deletes* an `<hr/>` in the XML, the diff ignores it. The HR remains in the live doc. This "zombie element" behavior might confuse users who think they removed it.
*   **Recommendation:** Clearly log a warning to the user: "Skipping deletion of Horizontal Rule (API limitation)."

### 3.2 Complex Nested Table Indexing
**Location:** Section 10.3 / 10.4

While "recursive descent" is mentioned, the **Table Index Drift** bug (1.1) becomes exponentially harder to track with nested tables.
*   **Risk:** If a nested table changes size, the "length" of the parent cell changes. This confirms that a simple "pristine length" lookup is impossible. The length of a cell is dynamic and depends on the diff of its children.

## Summary

The "Backwards Walk" strategy is generally sound for *independent* operations, but the **Table Modification** section introduces a dependency (Modifications affect Indices for subsequent Inserts) that breaks the "pristine index" invariant. This must be addressed before implementation to avoid data corruption.
