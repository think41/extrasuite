Apply local changes to Google Sheets.

## Usage

  extrasuite sheet push <folder>

## Arguments

  folder    Path to the spreadsheet folder (created by pull)

## Flags

  -f, --force   Push despite validation warnings

## How It Works

Compares current files against .pristine/ snapshot, generates batchUpdate
requests, and applies them to Google Sheets in a single API call.

## After Push

Always re-pull before making more changes. The .pristine/ snapshot is not
auto-updated, so subsequent pushes would generate incorrect diffs.

  extrasuite sheet push ./abc123
  extrasuite sheet pull https://docs.google.com/spreadsheets/d/abc123 .

## Validation

Push validates changes before sending them. Blocked operations will print
an error and exit. Warnings can be bypassed with --force if you're certain
the change is correct.

## Notes

- All edits to data.tsv, formula.json, format.json, etc. are applied in one push
- Adding/deleting sheets and changing cell values all happen in one operation
- If push fails partway through, re-pull to see the current state
