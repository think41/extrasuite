# Troubleshooting

Common issues and fixes for extradoc push.

## Common Errors

### "Changes not applied after push"

Always re-pull after push before making more edits:
  extrasuite doc push <folder>
  extrasuite doc pull <url> <folder>

### Push produces unexpected results

The .pristine/ state is stale. Re-pull to get a fresh copy:
  extrasuite doc pull <url> <folder>
  # Make your edits again on the fresh copy
  extrasuite doc push <folder>

### "Horizontal rule count changed" error

You added or removed an <hr/> element. The Google Docs API cannot add or
remove horizontal rules. Revert any <hr/> changes.

### Push fails on table changes

Most common causes:
- Missing <p> inside a <td>: every cell needs at least one <p>, even if empty
- Removed a physical <td> for a merged cell: colspan/rowspan are visual metadata
  only - all physical <td> elements must remain in the XML

### Style changes not applying

1. Verify the class ID in document.xml matches an id in styles.xml
2. Verify the style has the correct properties defined
3. For new styles: add the <style> element to styles.xml first

---

## API Limitations

Cannot add or remove: <hr/>, <image/>, <autotext/>, <columnbreak/>

Everything else in the supported tags list is editable.

---

## Table Cell Structure

Each row must have the same number of <td> elements regardless of merging.
colspan/rowspan are visual-only - merged cells still exist as physical <td> elements.

Example: 3-column table where first cell spans 2 columns:
```xml
<tr id="row1">
  <td id="c1" colspan="2"><p>Merged cell (columns 1-2)</p></td>
  <td id="c2"><p></p></td>    <!-- Physical cell covered by merge - required -->
  <td id="c3"><p>Column 3</p></td>
</tr>
```

---

## Diagnostic Checklist

When push doesn't work as expected:

1. Did you re-pull before editing? (stale pristine is the #1 cause)
2. Is the XML valid? Check for unescaped & < > " characters
3. Does every <td> contain a <p>? (even empty cells)
4. Are all physical table cells present? (even merged ones)
5. Did you add/remove an <hr/>? (not supported)
6. Does your class reference a style defined in styles.xml?
7. Run diff to preview what will be pushed: extrasuite doc diff <folder>

---

## XML Escaping

  & → &amp;
  < → &lt;
  > → &gt;  (optional but recommended)
  " → &quot; (only in attributes)
