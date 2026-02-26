Create a Gmail draft that replies in an existing thread.

## Usage

  extrasuite gmail reply <message_id> <file>

Unlike `gmail compose`, this command threads the draft correctly in Gmail by
setting In-Reply-To, References, and threadId on the message.

Get the message_id from `extrasuite gmail list` or `extrasuite gmail read`.

## Default Recipients

If the markdown file has no `to:` or `cc:` front matter, recipients are
inferred from the original message:

  - To  → original sender (From)
  - Cc  → original To + Cc (Gmail will exclude your own address)

Override by adding `to:` and/or `cc:` to the file front matter.

## File Format

```
---
# to: and cc: are optional — inferred from the original if omitted
---

Hi,

Thanks for your message. Here are my details...

Best,
Alice
```

## Attachments

  extrasuite gmail reply <message_id> reply.md --attach report.pdf

## Examples

  # Reply with auto-inferred recipients
  extrasuite gmail reply 19c8a19dbda1d3f7 reply.md

  # Reply with explicit recipients
  extrasuite gmail reply 19c8a19dbda1d3f7 reply.md
  # (set to:/cc: in reply.md front matter to override)

  # Reply with attachment
  extrasuite gmail reply 19c8a19dbda1d3f7 reply.md --attach file.pdf
