Download a Google Sheet to a local folder.

## Usage

  extrasuite sheet pull <url> [output_dir]

## Arguments

  url           Spreadsheet URL or ID
  output_dir    Output directory (default: current directory)

## Flags

  --max-rows N  Max rows per sheet to download (default: 100)
  --no-limit    Download all rows
  --no-raw      Skip saving raw API responses (.raw/ folder)

## Output

Creates <output_dir>/<spreadsheet_id>/ with:

  spreadsheet.json          Spreadsheet metadata, sheet list, previews, truncation hints
  theme.json                Default format and theme metadata (if present)
  named_ranges.json         Spreadsheet named ranges (if present)
  developer_metadata.json   Spreadsheet developer metadata (if present)
  data_sources.json         Spreadsheet data source metadata (if present)
  <sheet_name>/
    data.tsv                Raw cell values
    formula.json            Formulas (or {} for empty GRID sheets)
    format.json             Formatting, merges, notes, rich text (if present)
    dimension.json          Row/column size + hidden state (if present)
    charts.json             Charts (if present)
    pivot-tables.json       Pivot tables (if present)
    tables.json             Structured tables (if present)
    filters.json            Basic filter + filter views (if present)
    banded-ranges.json      Alternating colors (if present)
    data-validation.json    Validation rules (if present)
    slicers.json            Slicers (if present)
    data-source-tables.json Data source tables (if present)
    protection.json         Protected ranges (if present)
    comments.json           Drive comments for that sheet (if present)
  .pristine/                Snapshot for diff/push comparison - do not edit
  .raw/                     Raw API responses for debugging - do not edit

## Notes

- Start with `spreadsheet.json`
- `preview.firstRows` / `preview.lastRows` are often enough for orientation
- If any sheet was truncated, `spreadsheet.json` includes `_truncationWarning`
  and `sheets[].truncation`
- `comments.json` is separate from cell notes in `format.json`
- Some pulled files are informational only today: `theme.json`,
  `developer_metadata.json`, `data_sources.json`, and `protection.json`

## Example

  extrasuite sheet pull https://docs.google.com/spreadsheets/d/abc123
  extrasuite sheet pull https://docs.google.com/spreadsheets/d/abc123 /tmp/sheets
