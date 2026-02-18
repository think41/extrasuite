Advanced: execute raw Google Sheets batchUpdate API requests directly.

Not needed for most tasks. Use only for operations that the declarative
pull-edit-push workflow cannot express.

## Usage

  extrasuite sheet batchUpdate <url> <requests_file>

## Arguments

  url             Spreadsheet URL or ID
  requests_file   JSON file containing the API requests

## Flags

  -v, --verbose   Print the full API response

## Operations Only Possible via batchUpdate

  sortRange         Sort rows by column value (sort order can't be stored in files)
  moveDimension     Move rows or columns to a new position
  autoResizeDimensions  Auto-fit column widths to content
  findReplace       Find and replace across the spreadsheet
  trimWhitespace    Strip leading/trailing whitespace from all cells
  deleteDuplicates  Remove duplicate rows from a range

Everything else (cell values, formulas, formatting, charts, pivot tables,
named ranges, adding/deleting sheets) is better done via the declarative workflow.

## Request File Format

  [{"sortRange": {...}}, {"moveDimension": {...}}]

Or with a wrapper object:
  {"requests": [{"sortRange": {...}}]}

## After batchUpdate

Always re-pull - the local state is now stale:

  extrasuite sheet batchUpdate <url> requests.json
  extrasuite sheet pull <url>

## Examples

Sort rows 2-100 by column C descending (sheetId from spreadsheet.json):
  {"sortRange": {
    "range": {"sheetId": 0, "startRowIndex": 1, "endRowIndex": 100,
              "startColumnIndex": 0, "endColumnIndex": 5},
    "sortSpecs": [{"dimensionIndex": 2, "sortOrder": "DESCENDING"}]
  }}

Move rows 11-15 to before row 3:
  {"moveDimension": {
    "source": {"sheetId": 0, "dimension": "ROWS", "startIndex": 10, "endIndex": 15},
    "destinationIndex": 2
  }}

GridRange format (all indices 0-based, endIndex exclusive):
  {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 10,
   "startColumnIndex": 0, "endColumnIndex": 5}
