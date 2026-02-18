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

Email body goes here. Supports plain text.

Multiple paragraphs are preserved.
```

Required front matter fields: subject, to
Optional front matter fields: cc, bcc

Multiple recipients: comma-separated in a single field value.

## Output

Prints the draft ID on success. Silent otherwise.

## Notes

- The draft is saved to the authenticated user's Gmail account
- Open Gmail to review, edit, and send the draft
- The markdown body is sent as plain text (not rendered HTML)
