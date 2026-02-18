Apply local SML changes to Google Slides.

## Usage

  extrasuite slide push <folder>

## Arguments

  folder    Path to the presentation folder (created by pull)

## How It Works

Compares current content.sml files against .pristine/ snapshot, generates
batchUpdate requests, and applies them to Google Slides in a single API call.

## After Push

Always re-pull before making more changes. The .pristine/ snapshot is not
auto-updated, so subsequent pushes would generate incorrect diffs.

  extrasuite slide push ./abc123
  extrasuite slide pull https://docs.google.com/presentation/d/abc123 .

## Notes

- Only changes to content.sml files are pushed (not presentation.json or styles.json)
- If push fails partway through, re-pull to see the current state
