Apply local changes to Google Forms.

## Usage

  extrasuite form push <folder>

## Arguments

  folder    Path to the form folder (created by pull)

## Flags

  --reason TEXT  State the user's intent that led to this command (required). Also -r or -m.

  -f, --force   Push despite validation warnings

## How It Works

Compares current form.json against .pristine/ snapshot, generates the
minimal set of API operations (create/update/delete/move), and applies them.

After applying changes, push rewrites form.json with the API response (which
includes API-assigned itemIds and questionIds) and updates .pristine/ to match.
The folder is immediately ready for another round of edits without re-pulling.

## Notes

- New questions (no itemId/questionId) are created by the API with assigned IDs
- After push, form.json is updated with the real API IDs — no need to re-pull
- Deleted questions are removed permanently (responses for those questions are lost)
- Reordering is handled in a single push
