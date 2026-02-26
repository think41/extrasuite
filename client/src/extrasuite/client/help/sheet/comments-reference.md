# comments.json Reference

Cell comments for a sheet. Only created by pull if the sheet has at least one comment.

## Format

```json
{
  "fileId": "spreadsheet_id",
  "comments": [
    {
      "id": "AAABzqZTYuo",
      "author": "Alice <alice@example.com>",
      "time": "2024-01-15T10:30:00.000Z",
      "resolved": false,
      "content": "Please double-check this formula",
      "quotedContent": "=SUM(B2:B10)",
      "replies": [
        {
          "id": "AAABzqZTYus",
          "author": "Bob <bob@example.com>",
          "time": "2024-01-15T11:00:00.000Z",
          "content": "Verified — looks correct"
        }
      ]
    }
  ]
}
```

**`quotedContent`** — the cell text that was selected when the comment was created. Shown as context since the exact cell position is not available.

## Supported Operations

**Add a reply** — add an entry to `replies` without an `id`:

```json
{
  "id": "AAABzqZTYuo",
  "content": "Please double-check this formula",
  "resolved": false,
  "replies": [
    {"content": "Fixed — updated the range"}
  ]
}
```

**Resolve a comment** — set `"resolved": true`:

```json
{
  "id": "AAABzqZTYuo",
  "content": "Please double-check this formula",
  "resolved": true
}
```

Both operations can be combined: resolve a comment and add a reply in the same push.

## Limitations

- **Cannot create new comments** — Google Sheets uses an internal opaque anchor format that cannot be constructed from A1 notation.
- **Read-only fields** — do not modify `id`, `author`, or `time` on existing comments or replies; they are ignored on push.
