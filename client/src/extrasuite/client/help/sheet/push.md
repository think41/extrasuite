Apply local changes to Google Sheets.

## Usage

  extrasuite sheet push <folder>

## Arguments

  folder    Path to the spreadsheet folder created by pull

## Flags

  --reason TEXT  State the user's intent that led to this command (required). Also -r or -m.

  -f, --force   Push despite validation warnings

## How It Works

Push compares the current files against `.pristine/spreadsheet.zip`, validates
structural changes, generates Google Sheets `batchUpdate` requests, applies
those requests, then applies supported `comments.json` operations through the
Drive API.

## Editable Files

Push currently honors edits in:

  spreadsheet.json        Spreadsheet title; sheet title/hidden/RTL/tab color/frozen rows/cols
  data.tsv                Cell values and row/column insert/delete
  formula.json            Formulas
  format.json             Cell formats, conditional formats, merges, notes, rich text
  dimension.json          Row/column size and hidden state
  charts.json             Charts
  pivot-tables.json       Pivot tables
  tables.json             Structured tables
  filters.json            Basic filter + filter views
  banded-ranges.json      Alternating colors
  data-validation.json    Validation rules
  slicers.json            Slicers
  data-source-tables.json Limited support only
  named_ranges.json       Named ranges
  comments.json           New replies and comment resolution

Push currently ignores edits in:

  theme.json
  developer_metadata.json
  data_sources.json
  protection.json
  dimension.json rowGroups / columnGroups / developerMetadata
  spreadsheet.json properties.locale / autoRecalc / timeZone

## Comments

Push supports these `comments.json` operations:

  Add a reply     Add a reply object without an `id`
  Resolve         Set `"resolved": true`

Not supported:

  Create new top-level comments

See `extrasuite sheet help comments-reference` for the file format.

## After Push

Always re-pull before making more changes. `.pristine` is not auto-updated, so
reusing the same folder after a push will generate stale diffs.

## Validation

Push validates structural edits before sending requests:

  BLOCK    Push fails
  WARN     Push requires --force

Typical causes include row/column insertions or deletions that conflict with
formula edits.
