Google Calendar - view, search, and manage events.

## Commands

  extrasuite calendar list              List all calendars you have access to
  extrasuite calendar view --help       View events for a time range
  extrasuite calendar search --help     Search events by title or attendee
  extrasuite calendar freebusy --help   Check when people are free
  extrasuite calendar create --help     Create an event from a JSON file
  extrasuite calendar update --help     Update an existing event
  extrasuite calendar delete --help     Cancel/delete an event
  extrasuite calendar rsvp --help       Accept or decline an invite

## Workflow

1. Run `calendar list` to discover calendar IDs (needed for non-primary calendars)
2. Run `calendar view` or `calendar search` to find events and their Event IDs
3. Use Event IDs with `update`, `delete`, or `rsvp`

## Finding a Time to Meet

  extrasuite calendar freebusy --attendees alice@example.com bob@example.com --when next-week
