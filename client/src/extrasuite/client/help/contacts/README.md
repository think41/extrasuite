Google Contacts - sync and search for email addresses.

## Why use contacts

Use `contacts search` to look up email addresses before composing emails.
The local DB is synced from Google Contacts and Gmail-suggested contacts.

## Workflow

  # Search by name or company (auto-syncs if DB is missing or stale)
  extrasuite contacts search "Alice Example" "Bob Corp" --reason "state the user's intent that led to this command"

  # Explicitly sync the contacts DB
  extrasuite contacts sync --reason "state the user's intent that led to this command"

## Commands

  extrasuite contacts sync --help     Sync contacts from Google to local DB
  extrasuite contacts search --help   Search local DB by name or company

## contacts search

  extrasuite contacts search <query> [<query> ...] --reason TEXT

Each query is matched independently. Returns a JSON array of matching contacts
with name, email, and organization. The DB is auto-synced if it is missing or stale.
--reason is required when a sync is triggered.

## contacts sync

  extrasuite contacts sync --reason TEXT

Pulls your Google Contacts and Gmail-suggested contacts into a local SQLite DB.
Run this explicitly if you need fresh data right now.

## Notes

- The contacts DB is stored locally; no contact data is sent to ExtraSuite servers.
- Syncs both Google Contacts (people you've added) and Gmail-suggested contacts
  (people you've emailed).
