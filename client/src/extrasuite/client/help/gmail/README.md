Gmail - compose and edit email drafts from local markdown files.

## Workflow

  # 1. Write your email as a markdown file with front matter
  # 2. Save the draft to Gmail
  extrasuite gmail compose <file>

  # To update an existing draft (draft_id is printed by compose)
  extrasuite gmail edit-draft <draft_id> <file>

The draft is saved to Gmail. Open Gmail to review and send it.
Markdown in the body is rendered as HTML in the draft.

## Commands

  extrasuite gmail compose --help      Compose flags and file format
  extrasuite gmail edit-draft --help   Update an existing draft
