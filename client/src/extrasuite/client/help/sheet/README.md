Google Sheets - edit spreadsheets via local TSV and JSON files.

## Workflow

  extrasuite sheets pull <url> [output_dir]   Download spreadsheet
  # Edit files in <output_dir>/
  extrasuite sheets diff <folder>             Preview changes (no API calls)
  extrasuite sheets push <folder>             Apply changes to Google Sheets
  extrasuite sheets create <title>            Create a new spreadsheet

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

  extrasuite sheets pull --help        Pull flags, folder layout, and key rules
  extrasuite sheets diff --help        Preview requests and comment ops
  extrasuite sheets push --help        Apply local changes
  extrasuite sheets create --help      Create a new spreadsheet
  extrasuite sheets share --help       Share with trusted contacts
  extrasuite sheets batchUpdate --help Execute raw API requests directly

## Reference Docs

  extrasuite sheets help                    List available reference topics
  extrasuite sheets help formulas           All Google Sheets formulas, grouped by category
  extrasuite sheets help formulas <name>    Syntax, summary, and official docs for one formula
  extrasuite sheets help format-reference    format.json and dimension.json details
  extrasuite sheets help features-reference  charts, filters, pivot tables, tables, named ranges
  extrasuite sheets help comments-reference  comments.json format and limits
