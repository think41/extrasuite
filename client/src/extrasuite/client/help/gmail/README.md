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

## Commands

  extrasuite gmail compose --help      Compose flags and file format
  extrasuite gmail edit-draft --help   Update an existing draft
