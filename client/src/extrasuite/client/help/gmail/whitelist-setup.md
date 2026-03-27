Configure which senders are trusted for email reading.

## Why a Whitelist?

Email bodies may contain prompt injection attacks — content crafted to
manipulate an AI agent reading the email. The whitelist ensures the agent
only reads full email content from known, trusted senders.

For non-whitelisted senders, only metadata (from, date, subject) is shown.
The body and attachments are always redacted.

## Settings File

Location: ~/.config/extrasuite/settings.toml

This file is managed by you (the human) — no CLI command can modify it.
That's intentional: an agent cannot trick itself into adding new domains.

## Format

```toml
[trusted_contacts]
domains = ["yourcompany.com", "trusted-vendor.com"]
emails  = ["personal@gmail.com", "alerts@pagerduty.com"]
```

- **domains**: All email addresses at this domain are trusted.
  Example: `"company.com"` trusts `alice@company.com`, `bob@company.com`, etc.
  Note: Subdomain matching is NOT automatic. Add `"mail.company.com"` separately if needed.

- **emails**: Specific email addresses that are trusted regardless of domain.

Matching is case-insensitive.

## Trusting All Senders (Power Users)

If you want the agent to read email from any sender, add `trust_all = true`:

```toml
[trusted_contacts]
trust_all = true
```

**Security warning**: With `trust_all = true`, the agent will read email bodies
from any sender — including potential attackers. Only use this if you understand
the prompt injection risk and have other mitigations in place (e.g. a sandboxed
agent with limited ability to act on instructions).

## Creating the File

  mkdir -p ~/.config/extrasuite
  cat > ~/.config/extrasuite/settings.toml << 'EOF'
  [trusted_contacts]
  domains = ["yourcompany.com"]
  emails  = []
  EOF
  chmod 600 ~/.config/extrasuite/settings.toml

## Security Notes

- Subject lines are shown for ALL senders (whitelisted or not). Subjects
  may contain untrusted content. Always verify sender identity before
  acting on a subject line alone.
- Attachment filenames are only shown for whitelisted senders.
- HTML is stripped from email bodies before display to reduce injection risk.
