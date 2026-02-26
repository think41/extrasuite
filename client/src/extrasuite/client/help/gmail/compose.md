Save an email as a Gmail draft from a markdown file with front matter.

## Usage

  extrasuite gmail compose <file> [--attach FILE ...]

## File Format

```
---
subject: Meeting notes for Q4 planning
to: alice@example.com, bob@example.com
cc: charlie@example.com
bcc: dave@example.com
---

Hi team,

Here are the notes from today's meeting:

- **Launch date** moved to March 15
- Next sync Friday at 2pm

Best, Alice
```

Required: `subject`, `to`. Optional: `cc`, `bcc`. Multiple recipients: comma-separated.

Write the body conversationally. **bold**, *italic*, lists, and [links](https://example.com) are supported.

## Attachments

  extrasuite gmail compose email.md --attach report.pdf --attach data.csv

Repeat `--attach` for multiple files. MIME type is detected from the extension.

## Output

Prints the draft ID on success. Pass it to `edit-draft` to update the draft later.
