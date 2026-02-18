Apply local XML changes to Google Docs.

## Usage

  extrasuite doc push <folder>

## Arguments

  folder    Path to the document folder (created by pull)

## Flags

  -f, --force    Push despite validation warnings
  --verify       Re-pull after push to verify changes were applied correctly

## How It Works

Compares current document.xml against .pristine/ snapshot, generates
batchUpdate requests, and applies them to Google Docs in a single API call.
Comment operations (new replies, resolves) are applied via the Drive API.

## After Push

Always re-pull before making more changes. The .pristine/ snapshot is not
auto-updated, so subsequent pushes would generate incorrect diffs.

  extrasuite doc push ./abc123
  extrasuite doc pull https://docs.google.com/document/d/abc123 .

## Notes

- If push fails with an XML validation error, fix document.xml first
- If push produces unexpected results, use diff to inspect the generated requests
- Table changes are the most common source of push failures (see troubleshooting.md)
