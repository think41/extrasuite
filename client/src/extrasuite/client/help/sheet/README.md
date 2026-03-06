Google Sheets - edit spreadsheets via local TSV and JSON files.

## Workflow

  extrasuite sheet pull <url> [output_dir]
  # Edit files in <output_dir>/<spreadsheet_id>/
  extrasuite sheet diff <folder>
  extrasuite sheet push <folder>

After push, always re-pull before making more changes.

## Start Here

  spreadsheet.json   Overview of the spreadsheet, sheet list, previews, and any truncation hints

If a pull was row-limited, `spreadsheet.json` may contain:

  sheets[].truncation     Per-sheet details about totalRows vs fetchedRows
  _truncationWarning      Top-level warning that one or more sheets are partial

## Directory Structure

  <spreadsheet_id>/
    spreadsheet.json        Required
    theme.json              Optional, informational only
    named_ranges.json       Optional, editable
    developer_metadata.json Optional, informational only
    data_sources.json       Optional, informational only
    <sheet_name>/
      data.tsv              Cell values
      formula.json          Formulas
      format.json           Cell formatting, merges, notes, rich text
      dimension.json        Row/column size + hidden state
      charts.json           Charts
      pivot-tables.json     Pivot tables
      tables.json           Structured tables
      filters.json          Basic filter + filter views
      banded-ranges.json    Alternating colors
      data-validation.json  Dropdowns, checkboxes, validation rules
      slicers.json          Interactive slicers
      data-source-tables.json Data source tables
      protection.json       Optional, informational only
      comments.json         Optional, replies/resolve only
    .pristine/              Internal state - do not edit
    .raw/                   Raw API responses - do not edit

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

  extrasuite sheet pull --help        Pull flags and folder layout details
  extrasuite sheet diff --help        Preview requests and comment ops
  extrasuite sheet push --help        Apply local changes
  extrasuite sheet create --help      Create a new spreadsheet
  extrasuite sheet batchUpdate --help Execute raw API requests directly

## Reference Docs

  extrasuite sheet help format-reference    format.json and dimension.json details
  extrasuite sheet help features-reference  charts, filters, pivot tables, tables, named ranges
  extrasuite sheet help comments-reference  comments.json format and limits
