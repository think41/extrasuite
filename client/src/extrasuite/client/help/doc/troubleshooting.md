# Troubleshooting

Common issues and fixes for extradoc push.

## Common Errors

### "Changes not applied after push"

Always re-pull after push before making more edits:
  extrasuite docs push <folder>
  extrasuite docs pull <url> <folder>

### Push produces unexpected results

The .extrasuite/pristine.zip snapshot is stale. Re-pull to get a fresh copy:
  extrasuite docs pull <url> <folder>
  # Make your edits again on the fresh copy
  extrasuite docs push <folder>

### Heading after a list becomes a list item

If you place a heading directly after a list with no separator, Google Docs
absorbs the heading into the list and strips its heading style:

```markdown
<!-- Wrong -->
- Last item
## Next Section

<!-- Correct: blank line creates a paragraph break -->
- Last item

## Next Section
```

This applies after both bullet and numbered lists. Push succeeds silently —
re-pull to verify headings rendered correctly.

### Horizontal rule cannot be added or removed

The Google Docs API does not support inserting or deleting horizontal rules.
Revert any `---` additions or removals.

### New tab header/footer not appearing

Creating a header/footer for a new tab in an existing multi-tab doc is not
supported in the same push. Create the tab first, re-pull, then add the
header/footer.

---

## API Limitations

Cannot add or remove via push:
- Horizontal rules (`---`)
- Images
- Auto-text fields (page numbers, date, etc.)
- Column breaks

Also read-only:
- Section breaks
- Table of contents blocks
- Opaque "pulled-only" blocks

Everything else in the supported markdown and frontmatter is editable.

---

## Diagnostic Checklist

When push doesn't work as expected:

1. Did you re-pull before editing? (stale .extrasuite/pristine.zip is the #1 cause)
2. Does every table cell have content? (empty cells need at least a blank line)
3. Did you add or remove a horizontal rule `---`? (not supported)
4. Did you modify YAML frontmatter in a tab file? (id and title fields are read-only)
5. Use --verify to auto-confirm: extrasuite docs push --verify <folder>
