Create a Google Calendar event from a JSON file.

## Usage

  extrasuite calendar create --json PATH [--calendar ID]
  extrasuite calendar create --json -    # read from stdin

## Flags

  --reason TEXT  State the user's intent that led to this command (required). Also -r or -m.

  --json PATH         Path to event JSON file, or - to read from stdin
  --calendar ID       Calendar ID (default: primary, or value from JSON)

## JSON Schema

Required fields:
  summary             Event title
  start               Start time (ISO 8601: "2026-03-01T10:00:00")
  end                 End time   (ISO 8601: "2026-03-01T11:00:00")

Optional fields:
  timezone            IANA timezone name (e.g. "Asia/Kolkata", "America/New_York")
  description         Event description or agenda
  location            Location string (room name, address, or URL)
  attendees           List of email strings or objects with "email" and "optional"
  add_meet            true to create a Google Meet link (default: false)
  all_day             true for an all-day event (ignores time portion of start/end)
  recurrence          RRULE string for recurring events
  calendar            Calendar ID (overrides --calendar flag)
  send_notifications  false to suppress invite emails (default: true)
  status              "confirmed" (default), "tentative", or "cancelled"

## Examples

### Simple meeting
```json
{
  "summary": "1:1 with Alice",
  "start": "2026-03-01T10:00:00",
  "end": "2026-03-01T10:30:00",
  "timezone": "Asia/Kolkata",
  "attendees": ["alice@example.com"],
  "add_meet": true
}
```

### Recurring weekly standup
```json
{
  "summary": "Weekly Standup",
  "start": "2026-03-02T09:00:00",
  "end": "2026-03-02T09:15:00",
  "timezone": "Asia/Kolkata",
  "attendees": ["alice@example.com", "bob@example.com"],
  "recurrence": "RRULE:FREQ=WEEKLY;BYDAY=MO",
  "add_meet": true
}
```

### All-day event
```json
{
  "summary": "Company Holiday",
  "start": "2026-03-25",
  "end": "2026-03-26",
  "all_day": true
}
```

### Meeting with optional attendee
```json
{
  "summary": "Design Review",
  "start": "2026-03-01T14:00:00",
  "end": "2026-03-01T15:00:00",
  "timezone": "Asia/Kolkata",
  "attendees": [
    "alice@example.com",
    {"email": "bob@example.com", "optional": true}
  ]
}
```

## Common Recurrence Rules

  Weekly on Monday:         RRULE:FREQ=WEEKLY;BYDAY=MO
  Daily on weekdays:        RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
  Monthly on the 1st:       RRULE:FREQ=MONTHLY;BYMONTHDAY=1
  Weekly, 10 occurrences:   RRULE:FREQ=WEEKLY;COUNT=10
  Weekly until a date:      RRULE:FREQ=WEEKLY;UNTIL=20261231T000000Z
