Push local changes to Google Docs.

## Usage

  extrasuite doc push <folder>

## Arguments

  folder    Path to the document folder (created by pull or create)

## Flags

  -f, --force    Push despite validation warnings
  --verify       Re-pull after push to verify changes were applied correctly

## Important

Always re-pull before making more changes. The internal snapshot is not
auto-updated, so subsequent pushes without re-pulling generate incorrect diffs.

  extrasuite doc push ./my-doc
  extrasuite doc pull <url> ./my-doc
