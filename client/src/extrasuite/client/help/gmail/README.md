Gmail - compose, send, and read email drafts from local markdown files.

## Compose Workflow

  # 1. Look up recipient email addresses
  extrasuite contacts search "Alice Example" "Bob Corp"

  # 2. Write your email as a markdown file with front matter
  # 3. Save the draft to Gmail (optionally attach files)
  extrasuite gmail compose <file> [--attach report.pdf]

  # To update an existing draft (draft_id is printed by compose)
  extrasuite gmail edit-draft <draft_id> <file> [--attach slides.pdf]

The draft is saved to Gmail. Open Gmail to review and send it.

## Read Workflow

  # List recent or filtered messages
  extrasuite gmail list "is:unread"

  # Read a message body (sender must be in whitelist)
  extrasuite gmail read <message_id>

  # Reply in an existing thread
  extrasuite gmail reply <message_id> reply.md

## Commands

  extrasuite gmail compose --help        Compose flags and file format
  extrasuite gmail edit-draft --help     Update an existing draft
  extrasuite gmail list --help           Search and list messages
  extrasuite gmail read --help           Read a message (subject to whitelist)
  extrasuite gmail reply --help          Create a reply draft in a thread
  extrasuite gmail help whitelist-setup  Configure trusted senders
