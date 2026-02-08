# Troubleshooting

Common issues, API limitations, and debugging tips for extradoc.

---

## Common Errors

### "Changes not applied after push"

**Cause:** You edited files after a push without re-pulling first.

**Fix:** Always re-pull after push:
```bash
uv run python -m extradoc push <folder>
uv run python -m extradoc pull <url> <folder>    # Re-pull to refresh pristine state
# Now safe to edit again
```

### Push produces unexpected results

**Cause:** The `.pristine/` state is stale — it doesn't match what's currently in Google Docs.

**Fix:** Re-pull to get a fresh copy:
```bash
uv run python -m extradoc pull <url> <folder>
# Make your edits again on the fresh copy
uv run python -m extradoc push <folder>
```

### "Horizontal rule count changed" error

**Cause:** You added or removed an `<hr/>` element. The Google Docs API does not support adding or removing horizontal rules.

**Fix:** Revert any `<hr/>` additions or deletions. You can only modify content around existing horizontal rules.

### Push fails with API error on table changes

**Cause:** Table structure is invalid — missing `<p>` inside a `<td>`, or merged cell physical `<td>` elements were removed.

**Fix:** Ensure every `<td>` contains at least one `<p>` (even empty cells). For merged cells, keep all physical `<td>` elements — `colspan`/`rowspan` are visual metadata only.

### Style changes not applying

**Cause:** Missing style definition in `styles.xml`, or the `class` attribute references a non-existent style ID.

**Fix:** Verify:
1. The style ID in `document.xml` matches an `id` in `styles.xml`
2. The style has the correct properties defined
3. For new styles, you've added a `<style>` element to `styles.xml`

---

## API Limitations

These are hard limits of the Google Docs API. No workaround is available.

| Feature | Limitation |
|---------|------------|
| **Horizontal rules** | Cannot add or remove. Read-only. |
| **Images** | Cannot insert via this workflow. Requires Google Drive upload flow. |
| **Person mentions** | Cannot insert. Requires verified email and special API properties. |
| **Autotext** | Cannot insert page numbers, page count, or other auto-text elements. |
| **Document-level styles** | Page margins, page size, orientation are not yet supported. |

### What You CAN Do

| Operation | Supported |
|-----------|-----------|
| Add/edit/delete paragraphs | Yes |
| Add/edit/delete headings | Yes |
| Add/edit/delete list items | Yes |
| Add/edit/delete tables | Yes |
| Add/delete table rows | Yes |
| Add/delete table columns | Yes |
| Edit table cell content | Yes |
| Style table cells (background, borders, padding) | Yes |
| Set column widths | Yes |
| Apply text formatting (bold, italic, etc.) | Yes |
| Apply paragraph styles (alignment, spacing, indent) | Yes |
| Apply custom text styles (font, color, background) | Yes |
| Edit header/footer content | Yes |
| Add new headers/footers | Yes |
| Add page breaks | Yes |
| Add column breaks | Yes |
| Edit footnote content | Yes |
| Add/delete document tabs | Yes |

---

## Debugging with Diff

Use `diff` as a dry run to preview what push will do:

```bash
uv run python -m extradoc diff <folder>
```

This outputs the `batchUpdate` JSON that would be sent to the API. Review it to verify:
- The correct elements are being modified
- No unintended deletions or insertions
- Style changes target the right ranges

Save diff output for comparison:
```bash
uv run python -m extradoc diff <folder> > diff-output.json
```

---

## Table Physical Cell Structure

This is the most common source of confusion with tables.

### The Rule

Each row must have the same number of `<td>` elements, regardless of merging. The `colspan` and `rowspan` attributes are **visual metadata only** — they don't reduce the number of physical cells.

### Example: 3-column table with a merged cell

If you have a 3-column table and the first cell spans 2 columns:

```xml
<table id="abc123">
  <tr id="row1">
    <td id="c1" colspan="2"><p>Merged cell spanning columns 1-2</p></td>
    <td id="c2"><p></p></td>    <!-- Physical cell covered by merge (empty but required) -->
    <td id="c3"><p>Column 3</p></td>
  </tr>
</table>
```

All 3 `<td>` elements must be present. The second `<td>` is empty because it's "covered" by the `colspan="2"` on the first cell, but it must still exist in the XML.

### Why This Matters

Google Docs internally tracks every cell as a separate entity with its own index. If you omit the physical cells, the push will produce incorrect results or fail.

---

## Footnote Gotchas

### Inline Model

Footnotes use an **inline model** — the `<footnote>` tag appears at the exact position where the footnote reference marker (superscript number) should appear:

```xml
<p>See the study results<footnote id="kix.fn1"><p>Smith et al., 2024.</p></footnote> for more details.</p>
```

The text "See the study results" is followed by the footnote marker, then "for more details." continues.

### Footnote Content

Footnote content is structured like a table cell — it contains `<p>` elements:

```xml
<footnote id="kix.fn1">
  <p>First paragraph of footnote.</p>
  <p>Second paragraph of footnote.</p>
</footnote>
```

### Editing Footnote Content

To change footnote content, modify the `<p>` elements inside the `<footnote>` tag. The position of the `<footnote>` in the parent `<p>` determines where the reference marker appears.

---

## Nested List Nesting Behavior

### How Nesting Works

When you push list items, the `level` attribute determines nesting depth:

```xml
<li type="bullet" level="0">Top level item</li>
<li type="bullet" level="1">Nested item</li>
<li type="bullet" level="2">Deeply nested item</li>
```

### Known Limitation: Inserting into existing lists

When inserting new list items in the **middle** of an existing list, the nesting levels may not be applied correctly. This is a Google Docs API limitation — when new paragraphs are merged into an adjacent existing list, the API inherits nesting from context rather than processing the specified levels.

**Workarounds:**
- Add items at the end of a list (works correctly)
- Modify existing items (delete + re-insert works correctly)
- If inserting in the middle, accept that nesting may need manual adjustment in Google Docs

---

## XML Validity

### Common XML Mistakes

| Mistake | Fix |
|---------|-----|
| Unescaped `&` in text | Use `&amp;` |
| Unescaped `<` in text | Use `&lt;` |
| Unescaped `>` in text | Use `&gt;` (optional but recommended) |
| Unescaped `"` in attributes | Use `&quot;` |
| Missing closing tag | Every `<p>` needs `</p>`, every `<b>` needs `</b>` |
| Self-closing tags with content | `<p/>` is empty; use `<p>text</p>` |

### Special Characters in Text

XML requires escaping these characters in text content:

```xml
<!-- Correct -->
<p>Revenue &amp; Expenses</p>
<p>If x &lt; 10 then stop</p>
<p>Use the &quot;quotes&quot; feature</p>

<!-- Incorrect (will break XML parsing) -->
<p>Revenue & Expenses</p>
<p>If x < 10 then stop</p>
```

---

## Quick Diagnostic Checklist

When push doesn't work as expected:

1. **Did you re-pull before editing?** Stale pristine state is the #1 cause of issues.
2. **Is the XML valid?** Check for unescaped special characters or missing closing tags.
3. **Does every `<td>` contain a `<p>`?** Even empty cells need `<td><p></p></td>`.
4. **Are all table cells present?** Even merged cells need physical `<td>` elements.
5. **Did you add/remove an `<hr/>`?** This is not supported.
6. **Does your style exist?** Check that the `class` value maps to a `<style>` in `styles.xml`.
7. **Run `uv run python -m extradoc diff`** to preview what will be pushed and look for unexpected changes.
