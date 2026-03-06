## Overview

Python library that implements the Google Sheets pull/diff/push workflow used by
`extrasuite sheet`.

The current on-disk model is split by concern:
- `spreadsheet.json` for spreadsheet metadata, sheet list, previews, and
  truncation hints
- `data.tsv` for cell values
- `formula.json` for formulas
- `format.json` for cell formatting, merges, notes, and text format runs
- Separate feature files such as `charts.json`, `filters.json`,
  `pivot-tables.json`, and `data-validation.json`
- Optional per-sheet `comments.json` files fetched via Drive comments

Do not describe the current format as `feature.json`-based except when talking
about backward compatibility in the diff engine.

## Key Files

| File | Purpose |
|------|---------|
| `src/extrasheet/client.py` | `SheetsClient` orchestration for `pull()`, `diff()`, `push()` |
| `src/extrasheet/transport.py` | Transport abstraction plus Google/local transports |
| `src/extrasheet/transformer.py` | API response -> on-disk format |
| `src/extrasheet/writer.py` | Disk writes |
| `src/extrasheet/diff.py` | Pristine/current diff engine |
| `src/extrasheet/request_generator.py` | Diff -> Sheets `batchUpdate` requests |
| `src/extrasheet/comments.py` | `comments.json` conversion and comment diffing |
| `src/extrasheet/file_reader.py` | Reads editable files from disk |
| `src/extrasheet/structural_validation.py` | Validation for row/column and sheet structure changes |

## Documentation

- `docs/on-disk-format.md` - Canonical file layout and field reference
- `docs/architecture.md` - System overview
- `docs/diff-push-spec.md` - What push currently supports
- `docs/gaps.md` - Pull-only and partially supported areas

## Key Gotchas

- `extrasheet` is a library package. The CLI is `extrasuite sheet ...`, not a
  standalone `extrasheet` command.
- `spreadsheet.json` is the entry point for agents. It includes previews and, if
  a pull was row-limited, `_truncationWarning` plus per-sheet `truncation`.
- Empty GRID sheets still get an empty `data.tsv` and `{}` `formula.json`.
- `comments.json` is per-sheet. Only replies and resolution are supported; new
  top-level comments are not.
- Several files are pull-only today: `theme.json`,
  `developer_metadata.json`, `data_sources.json`, `protection.json`, and the
  grouping/developer-metadata sections inside `dimension.json`.
- Spreadsheet push only honors `properties.title` at the spreadsheet level.
  `locale`, `autoRecalc`, and `timeZone` are informational.
- Sheet push currently honors title, hidden, right-to-left, tab color, and
  frozen row/column counts from `spreadsheet.json`.
- Re-pull after every push. `.pristine/spreadsheet.zip` is not auto-updated.

## CLI Workflow

```bash
uv run --project client extrasuite sheet pull <url> [output_dir]
uv run --project client extrasuite sheet diff <folder>
uv run --project client extrasuite sheet push <folder>
uv run --project client extrasuite sheet batchUpdate <url> <requests.json>
```

## Folder Structure

```text
<spreadsheet_id>/
  spreadsheet.json
  theme.json                     # optional, informational
  named_ranges.json              # optional, editable
  developer_metadata.json        # optional, informational
  data_sources.json              # optional, informational
  <sheet_name>/
    data.tsv
    formula.json
    format.json                  # optional
    dimension.json               # optional
    charts.json                  # optional
    pivot-tables.json            # optional
    tables.json                  # optional
    filters.json                 # optional
    banded-ranges.json           # optional
    data-validation.json         # optional
    slicers.json                 # optional
    data-source-tables.json      # optional
    protection.json              # optional, informational
    comments.json                # optional, replies/resolve only
  .raw/
    metadata.json
    data.json
  .pristine/
    spreadsheet.zip
```

## Testing

Use the golden-file workflow in `tests/` and prefer verifying format claims
against `transformer.py`, `diff.py`, `request_generator.py`, and a real pull if
the docs are in question.
