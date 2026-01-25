# ExtraSheet

A file format and library for representing Google Sheets as local files that can be edited by AI agents and synced back to Google Sheets.

> **Status**: Specification complete. Implementation pending.

## Overview

ExtraSheet enables AI agents (like Claude Code or GPT) to read and edit Google Sheets through simple, human-readable files:

- **TSV files** for cell data - universally understood, easy to edit
- **JSON files** for formulas, formatting, and features - structured but readable
- **Directory structure** per spreadsheet - organized and git-friendly

## Documentation

| Document | Description |
|----------|-------------|
| [File Format Specification](docs/file-format-spec.md) | Complete specification of the ExtraSheet format |
| [LLM Instructions](docs/llm-instructions.md) | How AI agents should work with ExtraSheet files |
| [Diff & Reconciliation](docs/diff-reconciliation-spec.md) | How changes are detected and synced to Google Sheets |
| [Design Decisions](docs/design-decisions.md) | Rationale behind key design choices |

## Quick Example

A Google Sheet is represented as a directory:

```
my-budget/
├── manifest.json           # Spreadsheet metadata
└── sheets/
    └── Budget/
        ├── data.tsv        # Cell values
        ├── formulas.json   # Cell formulas
        └── format.json     # Cell formatting
```

### data.tsv

```tsv
Category	Budget	Actual	Difference
Housing	2000	1950	50
Food	600	720	-120
Total	2600	2670	-70
```

### formulas.json

```json
{
  "D2": "=B2-C2",
  "D3": "=B3-C3",
  "B4": "=SUM(B2:B3)",
  "C4": "=SUM(C2:C3)",
  "D4": "=B4-C4"
}
```

### format.json

```json
{
  "dimensions": {
    "columnWidths": {"A": 120, "B": 100, "C": 100, "D": 100}
  },
  "rules": [
    {
      "range": "A1:D1",
      "format": {"bold": true, "backgroundColor": "#4285f4", "textColor": "#ffffff"}
    },
    {
      "range": "B2:D4",
      "format": {"numberFormat": {"type": "CURRENCY", "pattern": "$#,##0"}}
    }
  ]
}
```

## Design Principles

1. **Separation of Concerns**: Data, formulas, formatting, and features in separate files
2. **Human Readable**: Anyone can understand the files without documentation
3. **Git Friendly**: Clean, meaningful diffs for version control
4. **AI Agent Friendly**: Simple text files that LLMs can read and write
5. **Lossless Round-Trip**: Full fidelity when syncing with Google Sheets

## Comparison with Extraslide

| Aspect | Extraslide (Slides) | ExtraSheet (Sheets) |
|--------|---------------------|---------------------|
| Primary format | XML (SML) | TSV + JSON |
| Content model | Hierarchical (slides → elements) | Tabular (rows × columns) |
| Styling | Tailwind-style classes | Range-based rules |
| Scale | Dozens of elements | Thousands of cells |

Both follow the same pull → edit → diff → push workflow.

## Workflow

```
┌─────────────────┐
│  Google Sheets  │
└────────┬────────┘
         │ PULL
         ▼
┌─────────────────┐
│  ExtraSheet     │
│  Directory      │◄──── AI Agent edits files
└────────┬────────┘
         │ DIFF
         ▼
┌─────────────────┐
│  Change Set     │
└────────┬────────┘
         │ PUSH (batchUpdate)
         ▼
┌─────────────────┐
│  Google Sheets  │
└─────────────────┘
```

## Features Supported

- ✅ Cell values (text, numbers, dates, booleans)
- ✅ Formulas (including cross-sheet references)
- ✅ Cell formatting (fonts, colors, borders, alignment)
- ✅ Number formats (currency, percent, date, etc.)
- ✅ Merged cells
- ✅ Row heights and column widths
- ✅ Frozen rows and columns
- ✅ Charts (all types)
- ✅ Pivot tables
- ✅ Conditional formatting
- ✅ Data validation (dropdowns, etc.)
- ✅ Filters and filter views
- ✅ Protected ranges
- ✅ Banded ranges (alternating colors)
- ✅ Named ranges
- ✅ Multiple sheets

## Future Work

- [ ] Python library implementation (`extrasheet` package)
- [ ] CLI for pull/push operations
- [ ] VS Code extension for preview
- [ ] Local formula evaluation
- [ ] SQLite option for large data sheets
- [ ] Conflict resolution UI

## Related Projects

- [Extraslide](../extraslide/) - Similar format for Google Slides
- [ExtraSuite](../) - Parent project for Google Workspace AI integration

## License

MIT
