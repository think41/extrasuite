Google Sheets - edit spreadsheets via local TSV and JSON files.

## Workflow

  extrasuite sheets pull <url> [output_dir]   Download spreadsheet
  # Edit files in <output_dir>/
  extrasuite sheets push <folder>             Apply changes to Google Sheets
  extrasuite sheets create <title>            Create a new spreadsheet

After push, always re-pull before making more changes.

## Directory Structure

  <spreadsheet_id>/
    spreadsheet.json        START HERE - title, sheet list, data previews
    <sheet_name>/
      data.tsv              Cell values (raw, unformatted, 100 rows max by default)
      formula.json          Formulas only (omitted if no formulas)
      format.json           Colors, fonts, number formats (omitted if all default)
      dimension.json        Row heights and column widths
    .pristine/              Internal state - do not edit
    .raw/                   Raw API responses - do not edit

## Files and When to Edit

  spreadsheet.json   Title, sheet names, frozen rows/cols, tab colors, add/delete sheets
  data.tsv           Cell values, insert/delete rows and columns
  formula.json       Add, modify, or delete formulas (range compression supported)
  format.json        Backgrounds, text format, number format, conditional formats, merges
  dimension.json     Column widths and row heights

Optional files (only created when content exists):
  charts.json, data-validation.json, filters.json, pivot-tables.json,
  banded-ranges.json, tables.json, slicers.json, named_ranges.json,
  comments.json

## Key Rules

  data.tsv has raw values: write 8000 not $8,000; write 0.72 not 72%
  Formula cells: leave blank in data.tsv, define in formula.json
  Re-pull after every push (pristine state is not auto-updated)

## Commands

  extrasuite sheets pull --help        Pull flags and folder layout details
  extrasuite sheets push --help        Push flags
  extrasuite sheets diff --help        Offline debugging tool (no auth needed)
  extrasuite sheets create --help      Create a new spreadsheet
  extrasuite sheets batchUpdate --help Execute raw API requests (sort, move, etc.)

## Reference Docs (detailed)

  extrasuite sheets help                    List available reference topics
  extrasuite sheets help format-reference   Colors, borders, conditional formats, merges, rich text
  extrasuite sheets help features-reference Charts, data validation, pivot tables, named ranges
  extrasuite sheets help comments-reference Comments: add replies, resolve
