Show which script files have changed since the last pull.

## Usage

  extrasuite script diff <folder>

## Arguments

  folder    Path to the script project folder (created by pull)

## Output

Lists added, removed, and modified files. "No changes detected" if no edits made.

## Notes

Runs entirely offline - no authentication, no API calls.
Shows file-level changes only (not line diffs).

Only use diff when you want to verify which files were modified before pushing.
In normal workflow, go directly from editing to push.
