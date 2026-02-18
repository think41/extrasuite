Download a Google Sheet to a local folder.

## Usage

  extrasuite sheet pull <url> [output_dir]

## Arguments

  url           Spreadsheet URL or ID
  output_dir    Output directory (default: current directory)

## Flags

  --max-rows N  Max rows per sheet to download (default: 100)
  --no-limit    Download all rows (use for complete data access)
  --no-raw      Skip saving raw API responses (.raw/ folder)

## Output

Creates <output_dir>/<spreadsheet_id>/ with:

  spreadsheet.json        Spreadsheet title, sheet list, data previews (first 5 + last 3 rows)
  <sheet_name>/
    data.tsv              Raw cell values (tab-separated, no header row offset)
    formula.json          Formulas (only present if sheet has formulas)
    format.json           Formatting rules (only present if non-default formatting exists)
    dimension.json        Row heights and column widths (only present if non-default)
    charts.json           Chart definitions (if charts exist)
    data-validation.json  Dropdowns, checkboxes (if present)
    filters.json          Filter views (if present)
    pivot-tables.json     Pivot tables (if present)
  .pristine/              Snapshot for diff/push comparison - do not edit
  .raw/                   Raw API responses for debugging - do not edit

## Notes

- Start by reading spreadsheet.json for the overview
- The preview in spreadsheet.json (first 5 + last 3 rows) is often enough
- Read data.tsv only when you need to see or modify the actual cell data
- When a sheet has more than --max-rows rows, spreadsheet.json shows a truncation warning
- Use --no-limit to download all rows for large sheets that need complete data

## Example

  extrasuite sheet pull https://docs.google.com/spreadsheets/d/abc123
  extrasuite sheet pull https://docs.google.com/spreadsheets/d/abc123 /tmp/sheets
