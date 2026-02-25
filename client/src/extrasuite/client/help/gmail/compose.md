Save an email as a Gmail draft from a markdown file with front matter.

## Usage

  extrasuite gmail compose <file> [--attach FILE ...]

## Arguments

  file    Path to the markdown file with YAML front matter

## Options

  --attach FILE    Attach a file to the draft (repeat for multiple files)

## File Format

```
---
subject: Meeting notes for Q4 planning
to: alice@example.com, bob@example.com
cc: charlie@example.com
bcc: dave@example.com
---

Hi team,

Here are the notes from today's meeting. A few highlights:

- **Launch date** moved to March 15
- We're dropping the legacy integration (see the *updated* proposal)
- Next sync is Friday at 2pm

Let me know if I missed anything.

Best,
Alice
```

Required front matter fields: subject, to
Optional front matter fields: cc, bcc

Multiple recipients: comma-separated in a single field value.

## Formatting

Write your email body the way you'd write a normal email - keep it
conversational with minimal structure. Basic formatting is supported:

- **bold** and *italic* for emphasis
- Bulleted and numbered lists
- [Links](https://example.com)
- Simple tables
- Line breaks are preserved

You generally don't need headings or heavy formatting in emails.

## Attachments

Use --attach to include files with the draft:

  extrasuite gmail compose email.md --attach report.pdf
  extrasuite gmail compose email.md --attach report.pdf --attach data.csv

Any file type is supported. The MIME type is detected automatically from
the file extension. Repeat --attach for multiple files.

## Output

Prints the draft ID on success. Save it to update the draft later with edit-draft.

## Notes

- The draft is saved to the authenticated user's Gmail account
- The body is converted to HTML - the draft will appear formatted in Gmail
- A plain-text fallback is also included for email clients that don't render HTML
- Open Gmail to review, edit, and send the draft
- Use `extrasuite gmail edit-draft <draft_id> <file>` to update the draft
