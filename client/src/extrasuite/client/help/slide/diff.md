Offline debugging tool - shows the batchUpdate requests that push would send.

## Usage

  extrasuite slide diff <folder>

## Arguments

  folder    Path to the presentation folder (created by pull)

## Output

Prints the batchUpdate JSON to stdout. "No changes detected" if no edits made.

## Notes

Runs entirely offline - no authentication, no API calls.
Equivalent to push --dry-run.

Only use diff when a push produces unexpected results and you need to
inspect the exact API requests being generated. In normal workflow,
go directly from editing to push.
