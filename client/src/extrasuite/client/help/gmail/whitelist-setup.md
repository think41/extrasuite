Configure which senders are trusted for email reading.

## Why a Whitelist?

Email bodies may contain prompt injection attacks — content crafted to
manipulate an AI agent reading the email. The whitelist ensures the agent
only reads full email content from known, trusted senders.

For non-whitelisted senders, only metadata (from, date, subject) is shown.
The body and attachments are always redacted.

## Whitelist File

Location: ~/.config/extrasuite/gmail_whitelist.json

This file is managed by you (the human) — no CLI command can modify it.
That's intentional: an agent cannot trick itself into adding new domains.

## Format

```json
{
  "domains": ["yourcompany.com", "trusted-vendor.com"],
  "emails": ["personal@gmail.com", "alerts@pagerduty.com"]
}
```

- **domains**: All email addresses at this domain are trusted.
  Example: `"company.com"` trusts `alice@company.com`, `bob@company.com`, etc.
  Note: Subdomain matching is NOT automatic. Add `"mail.company.com"` separately if needed.

- **emails**: Specific email addresses that are trusted regardless of domain.

Matching is case-insensitive.

## Creating the File

  mkdir -p ~/.config/extrasuite
  cat > ~/.config/extrasuite/gmail_whitelist.json << 'EOF'
  {
    "domains": ["yourcompany.com"],
    "emails": []
  }
  EOF
  chmod 600 ~/.config/extrasuite/gmail_whitelist.json

Or run `extrasuite gmail list` once — if the file doesn't exist, a starter
template is NOT automatically created. You must create it yourself.

## No Wildcard Domains

The whitelist does not support wildcards (`*`). List each domain explicitly.
This is intentional — a broad whitelist defeats the purpose.

## Security Notes

- Subject lines are shown for ALL senders (whitelisted or not). Subjects
  may contain untrusted content. Always verify sender identity before
  acting on a subject line alone.
- Attachment filenames are only shown for whitelisted senders.
- HTML is stripped from email bodies before display to reduce injection risk.
