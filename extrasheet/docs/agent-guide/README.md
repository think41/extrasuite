# ExtraSheet Agent Guide

Quick reference for LLM agents modifying Google Sheets via extrasheet.

## Workflow

```bash
extrasheet pull <url>      # Download to local folder
# ... edit files ...
extrasheet diff <folder>   # Preview changes (dry run)
extrasheet push <folder>   # Apply changes
```

**After push, always re-pull before making more changes** - the pristine state is not auto-updated.

## Directory Structure

```
<spreadsheet_id>/
  spreadsheet.json          # START HERE - metadata + previews
  <sheet_name>/
    data.tsv                # Cell values (tab-separated)
    formula.json            # Formulas (flat dict)
    format.json             # Formatting + conditional formats
    charts.json             # Charts (if any)
    data-validation.json    # Dropdowns, checkboxes (if any)
    ...                     # Other feature files
  .pristine/                # DO NOT TOUCH - used by diff
  .raw/                     # Raw API responses (read-only reference)
```

## Reading Strategy

1. **Always start with `spreadsheet.json`** - contains sheet list and data previews (first 5 + last 3 rows of each sheet)
2. **Only read specific sheet files when needed** - don't read all data.tsv files upfront
3. **Skip `.pristine/` and `.raw/`** - internal use only

## File Quick Reference

| File | Format | When to Edit |
|------|--------|--------------|
| `spreadsheet.json` | JSON | Change titles, frozen rows/cols, add new sheets |
| `data.tsv` | TSV | Change cell values, insert/delete rows/cols |
| `formula.json` | Flat dict `{"A1": "=B1+C1"}` | Add/modify formulas |
| `format.json` | See [formatting.md](formatting.md) | Colors, fonts, conditional formats |
| `charts.json` | JSON | Add/modify charts |
| `data-validation.json` | JSON | Dropdowns, checkboxes |
| `dimension.json` | JSON | Row heights, column widths |

## Key Gotchas

| Issue | Solution |
|-------|----------|
| Color format errors | Use hex (`"#FF0000"`) in formatRules, RGB dicts in conditionalFormats |
| "Sheet already exists" after push | Re-pull before making more changes |
| Sheet IDs changed | Google reassigns IDs - re-pull to get actual IDs |
| Unhelpful `'dict' object has no attribute 'lstrip'` | Wrong JSON structure - check formula.json is flat, format.json uses formatRules array |

## Common Edits

### Change Cell Values
Edit `data.tsv` directly. Values are tab-separated, special chars escaped (`\t`, `\n`, `\\`).

### Add Formulas
Edit `formula.json` - must be a **flat dictionary**:
```json
{
  "C2": "=A2+B2",
  "D2:D100": "=B2*C2"
}
```
Range keys (like `"D2:D100"`) auto-fill with relative references.

### Create New Sheet
1. Create folder: `<spreadsheet_id>/NewSheet/`
2. Add `data.tsv` with content
3. Add entry to `spreadsheet.json` → `sheets[]`:
   ```json
   {"title": "NewSheet", "folder": "NewSheet", "sheetType": "GRID"}
   ```
4. Run `extrasheet push`

### Delete Sheet
Remove the sheet's folder from disk, then push.

## Detailed Guides

- [formatting.md](formatting.md) - Colors, fonts, conditional formatting, merges
- [formulas.md](formulas.md) - Formula syntax, ranges, compression
- [features.md](features.md) - Charts, pivot tables, filters, data validation
- [structural-changes.md](structural-changes.md) - Insert/delete rows/columns, batchUpdate
- [batchupdate-reference.md](batchupdate-reference.md) - All batchUpdate request types
