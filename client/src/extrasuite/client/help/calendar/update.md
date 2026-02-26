Update an existing Google Calendar event.

Only fields present in the JSON are changed. Omitted fields are left as-is.

## Usage

  extrasuite calendar update EVENT_ID --json PATH [--calendar ID] [--no-notify]
  extrasuite calendar update EVENT_ID --json -     # read from stdin

## Flags

  EVENT_ID            Event ID (from `calendar view` or `calendar search` output)
  --json PATH         Path to patch JSON file, or - to read from stdin
  --calendar ID       Calendar ID (default: primary)
  --no-notify         Suppress update notification emails to attendees

## JSON Schema (all fields optional)

  summary             New event title
  start               New start time (ISO 8601)
  end                 New end time (ISO 8601)
  timezone            IANA timezone name
  description         New description
  location            New location
  status              "confirmed", "tentative", or "cancelled"
  recurrence          New RRULE string (replaces existing recurrence)
  add_attendees       List of email strings to add
  remove_attendees    List of email strings to remove
  add_meet            true to add a Google Meet link
  calendar            Calendar ID (overrides --calendar flag)

## Examples

### Reschedule to a new time
```json
{
  "start": "2026-03-01T14:00:00",
  "end": "2026-03-01T15:00:00",
  "timezone": "Asia/Kolkata"
}
```

### Add a person and update the description
```json
{
  "add_attendees": ["charlie@example.com"],
  "description": "Updated agenda: Q1 review, roadmap discussion"
}
```

### Remove someone and change the location
```json
{
  "remove_attendees": ["bob@example.com"],
  "location": "Conference Room B"
}
```

### Add a Meet link to an existing event
```json
{
  "add_meet": true
}
```

## Workflow

1. Find the Event ID with `calendar view` or `calendar search`
2. Create a JSON patch file with only the fields to change
3. Run update with the Event ID and JSON file
