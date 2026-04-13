Google Sheets - edit spreadsheets via local TSV and JSON files.

  extrasuite sheets pull <url> [output_dir]   Download spreadsheet
  # Edit files in <output_dir>/
  extrasuite sheets push <folder>             Apply changes to Google Sheets
  extrasuite sheets create <title>            Create a new spreadsheet
  extrasuite sheets share <url> <emails>      Share with contacts

Open spreadsheet.json first — it lists every sheet with its row count and any
truncation status. Data lives in <sheet_name>/data.tsv (raw values,
tab-separated). Formula cells must stay blank in data.tsv — define them in
formula.json instead. Write raw values: 8000 not $8,000; 0.72 not 72%. Other
editable files per sheet: format.json (cell formats, merges, notes),
dimension.json (row/column sizes), charts.json, pivot-tables.json, tables.json,
filters.json, banded-ranges.json, data-validation.json, slicers.json,
comments.json (replies and resolve only). Spreadsheet-level: spreadsheet.json
(title, sheet tabs), named_ranges.json. Sheets with more than 1000 rows are
truncated by default — spreadsheet.json includes a re-pull hint with the exact
command. Always re-pull after push.

For formula syntax: extrasuite sheets help formulas [<name>]
For format.json and feature file formats: extrasuite sheets help format-reference
