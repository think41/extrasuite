Cancel (delete) a Google Calendar event.

By default, cancellation notification emails are sent to all attendees.

## Usage

  extrasuite calendar delete EVENT_ID [--calendar ID] [--no-notify] [--this-and-following]

## Flags

  EVENT_ID              Event ID to cancel (from `calendar view` or `calendar search`)
  --calendar ID         Calendar ID (default: primary)
  --no-notify           Suppress cancellation emails to attendees
  --this-and-following  For recurring events: cancel this and all future occurrences
                        (default: cancel only this single occurrence)

## Examples

  # Cancel a one-off event
  extrasuite calendar delete abc123xyz

  # Cancel silently (no notification emails)
  extrasuite calendar delete abc123xyz --no-notify

  # Cancel this and all future occurrences of a recurring event
  extrasuite calendar delete abc123xyz --this-and-following

  # Cancel an event on a non-primary calendar
  extrasuite calendar delete abc123xyz --calendar work@example.com

## Workflow

1. Find the Event ID with `calendar view` or `calendar search`
2. Run delete with the Event ID
