Read a Gmail message by its message ID.

## Usage

  extrasuite gmail read <message_id>

Get a message ID from `extrasuite gmail list`.

## Security: Sender Whitelist

Email bodies and attachments are only returned if the sender is in your
trusted whitelist (~/.config/extrasuite/gmail_whitelist.json). Your own
company's email domain is always trusted automatically.

If the sender is NOT whitelisted, body and attachments show as:

  [REDACTED]

This is a security measure to prevent prompt injection attacks — malicious
emails cannot manipulate the agent by embedding instructions in their body.

To allow reading a sender's emails, add their domain or address to:
  ~/.config/extrasuite/gmail_whitelist.json

See `extrasuite gmail help whitelist-setup` for details.

## Output (trusted sender)

  From:    Alice Smith <alice@company.com>
  To:      me@company.com
  CC:      team@company.com
  Date:    Mon, 15 Jan 2025 14:30:00 +0000
  Subject: Q4 Planning
  Labels:  INBOX, UNREAD

  Hi team,

  Let's meet on Friday to discuss Q4 plans...

  Attachments:
    - budget.pdf (245 KB, application/pdf)
    - timeline.xlsx (18 KB, application/vnd.openxmlformats...)

## Options

  --json    Output as JSON

## Whitelist Setup

See `extrasuite gmail help whitelist-setup` for configuration instructions.

## Examples

  # Read a message
  extrasuite gmail read msg_abc123

  # Read in JSON format
  extrasuite gmail read msg_abc123 --json
