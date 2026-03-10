Apply local markdown changes to Google Docs.

## Usage

  extrasuite doc push-md <folder>

## Arguments

  folder    Path to the document folder (created by pull-md)

## Flags

  -f, --force    Push despite validation warnings
  --verify       Re-pull after push to verify changes were applied correctly

## How It Works

Compares current <Tab_Name>.md files against .pristine/ snapshot, generates
batchUpdate requests, and applies them to Google Docs in a single API call.
Comment operations (new replies, resolves) are applied via the Drive API.

## After Push

Always re-pull before making more changes. The .pristine/ snapshot is not
auto-updated, so subsequent pushes would generate incorrect diffs.

  extrasuite doc push-md ./abc123
  extrasuite doc pull-md https://docs.google.com/document/d/abc123 .

## Notes

- push-md and push are interchangeable: both auto-detect format from index.xml
- If push fails, use diff to inspect the generated batchUpdate requests
- Table changes are the most common source of push failures (see troubleshooting.md)
