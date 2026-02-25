Update an existing Gmail draft from a markdown file with front matter.

## Usage

  extrasuite gmail edit-draft <draft_id> <file> [--attach FILE ...]

## Arguments

  draft_id    Draft ID to update (printed by `extrasuite gmail compose`)
  file        Markdown file with YAML front matter

## Options

  --attach FILE    Attach a file to the draft (repeat for multiple files)

## File Format

Same format as `extrasuite gmail compose`:

```
---
subject: Updated subject
to: alice@example.com
---

Updated body with **bold** and *italic* for emphasis.
```

## Attachments

Use --attach to include files with the updated draft:

  extrasuite gmail edit-draft abc123 email.md --attach slides.pdf

Repeat --attach for multiple files. Any file type is supported.

## Notes

- Replaces the entire draft content (subject, recipients, body, attachments)
- The draft ID is printed by `extrasuite gmail compose` on success
- The body is converted to HTML; a plain-text fallback is also included
- Open Gmail to review, edit, and send the draft
