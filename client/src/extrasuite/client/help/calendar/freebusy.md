Check when a group of people are free and find common open slots.

Uses the Google Calendar freebusy API - works even when you don't have
access to view the other person's actual events.

## Usage

  extrasuite calendar freebusy --attendees EMAIL [EMAIL ...] [--when RANGE]

## Flags

  --reason TEXT  State the user's intent that led to this command (required). Also -r or -m.

  --attendees EMAIL   One or more email addresses (space-separated)
  --when RANGE        Time range to check (default: next-week)

## Time Range Values

  today, tomorrow, this-week, next-week, or YYYY-MM-DD

## Output

Shows busy blocks per person, then computes common free slots across all
attendees within working hours (9 AM – 6 PM, weekdays only). Slots shorter
than 15 minutes are omitted.

If a person's calendar is not accessible, they are listed with an error note
and excluded from the common free slots calculation.

## Examples

  # Find when Alice and Bob are both free next week
  extrasuite calendar freebusy --attendees alice@example.com bob@example.com --reason "state the user's intent that led to this command"

  # Check a larger group for this week
  extrasuite calendar freebusy --attendees a@co.com b@co.com c@co.com --when this-week

  # Check availability on a specific date
  extrasuite calendar freebusy --attendees alice@example.com --when 2026-03-15
