Update an existing Gmail draft from a markdown file with front matter.

## Usage

  extrasuite gmail edit-draft <draft_id> <file>

## Arguments

  draft_id    Draft ID to update (printed by `extrasuite gmail compose`)
  file        Markdown file with YAML front matter

## File Format

Same format as `extrasuite gmail compose`:

```
---
subject: Updated subject
to: alice@example.com
---

Updated body in **markdown**.
```

## Notes

- Replaces the entire draft content (subject, recipients, body)
- The draft ID is printed by `extrasuite gmail compose` on success
- Markdown is converted to HTML; a plain-text fallback is also included
- Open Gmail to review, edit, and send the draft
