Save an email as a Gmail draft from a markdown file with front matter.

## Usage

  extrasuite gmail compose <file>

## Arguments

  file    Path to the markdown file with YAML front matter

## File Format

```
---
subject: Meeting notes for Q4 planning
to: alice@example.com, bob@example.com
cc: charlie@example.com
bcc: dave@example.com
---

# Heading

Email body in **markdown**. Supports:

- Bold, italic, lists
- Tables
- Headings

Multiple paragraphs are preserved.
```

Required front matter fields: subject, to
Optional front matter fields: cc, bcc

Multiple recipients: comma-separated in a single field value.

## Output

Prints the draft ID on success. Save it to update the draft later with edit-draft.

## Notes

- The draft is saved to the authenticated user's Gmail account
- Markdown in the body is converted to HTML - the draft will be formatted
- A plain-text fallback is also included for email clients that don't render HTML
- Open Gmail to review, edit, and send the draft
- Use `extrasuite gmail edit-draft <draft_id> <file>` to update the draft
