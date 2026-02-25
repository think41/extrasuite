Gmail - compose and edit email drafts from local markdown files.

## Workflow

  # 1. Look up recipient email addresses
  extrasuite contacts search "Alice Example" "Bob Corp"

  # 2. Write your email as a markdown file with front matter
  # 3. Save the draft to Gmail (optionally attach files)
  extrasuite gmail compose <file> [--attach report.pdf]

  # To update an existing draft (draft_id is printed by compose)
  extrasuite gmail edit-draft <draft_id> <file> [--attach slides.pdf]

The draft is saved to Gmail. Open Gmail to review and send it.

## Formatting

Write your email body conversationally, the way you'd write a normal email.
Basic formatting is supported: **bold**, *italic*, lists, and
[links](https://example.com). The body is converted to HTML in the draft.

## Attachments

Add --attach to include files with the draft. Repeat for multiple files:

  extrasuite gmail compose email.md --attach report.pdf --attach data.csv

## Commands

  extrasuite gmail compose --help      Compose flags and file format
  extrasuite gmail edit-draft --help   Update an existing draft

## Finding Email Addresses

  extrasuite contacts search "Alice Example" "Bob at Acme"

See `extrasuite contacts --help` for full search and touch usage.
