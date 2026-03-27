Search Google Calendar events by title, description, or attendee email.

## Usage

  extrasuite calendar search --query TEXT [options]
  extrasuite calendar search --attendee EMAIL [options]
  extrasuite calendar search --query TEXT --attendee EMAIL [options]

## Flags

  --reason TEXT  State the user's intent that led to this command (required). Also -r or -m.

  --query TEXT        Search text matched against title and description
  --attendee EMAIL    Filter to events that include this attendee's email
  --from DATE         Start of search range (default: today)
  --to DATE           End of search range (default: 30 days after --from)
  --calendar ID       Calendar ID to search (default: primary)

## Date Format

  today, tomorrow, yesterday, this-week, next-week, or YYYY-MM-DD

## Output

Same format as `calendar view`: events grouped by date with Event IDs,
attendees, and conferencing links.

## Examples

  # Find all meetings mentioning "Acme"
  extrasuite calendar search --query "Acme" --reason "state the user's intent that led to this command"

  # Find all meetings with a specific colleague
  extrasuite calendar search --attendee alice@example.com

  # Find meetings with Alice in the next 2 weeks
  extrasuite calendar search --attendee alice@example.com --from today --to 2026-03-15

  # Find "1:1" meetings this month
  extrasuite calendar search --query "1:1" --from today --to 2026-03-31
