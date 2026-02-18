Lint JavaScript files in an Apps Script project (offline, no push).

## Usage

  extrasuite script lint <folder>

## Arguments

  folder    Path to the script project folder (created by pull)

## Output

Prints lint diagnostics. Exits with code 1 if there are errors.
Silent if no issues found.

## Notes

Runs entirely offline - no authentication, no API calls.
The same lint check runs automatically before push (bypass with --skip-lint).
