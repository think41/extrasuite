Google Sheets - edit spreadsheets via local TSV and JSON files.

## Workflow

  extrasuite sheet pull <url> [output_dir]   # Downloads to <output_dir>/<spreadsheet_id>/
  # Edit files in <output_dir>/<spreadsheet_id>/
  extrasuite sheet diff <folder>             # Preview changes (no API calls)
  extrasuite sheet push <folder>             # Apply changes

See `extrasuite sheet pull --help` for directory layout, flags, and key rules (self-contained).

## Editable Surface

  spreadsheet.json   Spreadsheet title; sheet title, hidden, right-to-left, tab color, frozen rows/cols
  data.tsv           Cell values, insert/delete rows and columns
  formula.json       Add, modify, or delete formulas
  format.json        Formats, conditional formats, merges, notes, rich text runs
  dimension.json     Row/column sizes and hidden state
  charts.json        Add, update, or delete charts
  pivot-tables.json  Add, update, or delete pivot tables
  tables.json        Add, update, or delete structured tables
  filters.json       Basic filter and filter views
  banded-ranges.json Alternating colors
  data-validation.json Input validation rules
  slicers.json       Add, update, or delete slicers
  named_ranges.json  Spreadsheet named ranges
  comments.json      Add replies or resolve existing comments

Currently informational only on push:

  theme.json, developer_metadata.json, data_sources.json, protection.json
  dimension.json rowGroups/columnGroups/developerMetadata
  spreadsheet.json properties.locale / autoRecalc / timeZone

## Key Rules

  data.tsv stores raw values: write 8000 not $8,000; write 0.72 not 72%
  Formula cells should stay blank in data.tsv and be defined in formula.json
  Cell notes live in format.json; Drive comments live in comments.json
  Re-pull after every push because pristine state is not auto-updated

## Commands

  extrasuite sheet pull --help        Pull flags, folder layout, and key rules
  extrasuite sheet diff --help        Preview requests and comment ops
  extrasuite sheet push --help        Apply local changes
  extrasuite sheet create --help      Create a new spreadsheet
  extrasuite sheet share --help       Share with trusted contacts
  extrasuite sheet batchUpdate --help Execute raw API requests directly

## Reference Docs

  extrasuite sheet help                    List available reference topics
  extrasuite sheet help formulas           All Google Sheets formulas, grouped by category
  extrasuite sheet help formulas <name>    Syntax, summary, and official docs for one formula
  extrasuite sheet help format-reference    format.json and dimension.json details
  extrasuite sheet help features-reference  charts, filters, pivot tables, tables, named ranges
  extrasuite sheet help comments-reference  comments.json format and limits
