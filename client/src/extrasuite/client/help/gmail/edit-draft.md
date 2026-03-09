Update an existing Gmail draft from a markdown file with front matter.


## Flags

  --reason TEXT  State the user's intent that led to this command (required). Also -r or -m.

## Usage

  extrasuite gmail edit-draft <draft_id> <file> [--attach FILE ...]

`draft_id` is printed by `extrasuite gmail compose`.

## File Format

Same as `extrasuite gmail compose`. See `compose --help`.

## Attachments

  extrasuite gmail edit-draft abc123 email.md --attach slides.pdf --attach data.csv

Replaces the entire draft (subject, recipients, body, and attachments).
