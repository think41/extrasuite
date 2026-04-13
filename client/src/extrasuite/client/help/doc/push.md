Push local changes to Google Docs.

## Usage

  extrasuite docs push <folder>

## Arguments

  folder    Path to the document folder (created by pull or create)

## Flags

  -f, --force    Push despite validation warnings
  --verify       Re-pull after push and confirm changes were applied correctly

## Important

Always re-pull before making more changes. Push compares current files against
.extrasuite/pristine.zip — this snapshot is not updated after push, so a second
push without re-pulling will generate an incorrect diff.

  extrasuite docs push ./my-doc
  extrasuite docs pull <url> ./my-doc   # always re-pull before editing further
